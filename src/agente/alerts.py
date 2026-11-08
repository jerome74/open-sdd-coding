"""C-36 Alert Service — composizione, deduplicazione e invio avvisi (spec 10).

Gli avvisi vanno **solo** all'amministratore tramite C-10. La deduplicazione
distingue i casi per cui la spec la chiede (batteria e credenziali) dai
fallimenti dei compiti, che sono eventi distinti. Il servizio non parla mai
direttamente con Telegram e non solleva errori di invio: un gateway
irraggiungibile è loggato e coperto dalla liveness di spec 11.

Il ponte ``alert_threadsafe`` esiste perché C-05 è sincrona e può essere
chiamata da un worker: C-38 classifica l'errore e pianifica l'avviso sul loop
senza bloccare il thread chiamante.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping

from .errors import AgenteError
from .notifications import NotificationService
from .storage.repositories import SettingsRepository

logger = logging.getLogger("agente.alerts")

BATTERY_MARKER = "battery_last_alert"
CREDENTIAL_MARKER = "credential_last_alert"
BATTERY_ESCALATION_STEP = 5
CREDENTIAL_ALERT_WINDOW_S = 3600
CLOSE_TIMEOUT_S = 5

ALERT_KINDS = frozenset(
    {"task_failed", "task_timeout", "battery_low", "offline_resumed", "credential"}
)

_CREDENTIAL_REASONS = {
    401: "chiave non valida",
    402: "credito esaurito",
    403: "accesso negato",
}


@dataclass(frozen=True)
class Alert:
    """Evento composto e inviato: non viene persistito."""

    kind: str
    detail: Mapping[str, Any]
    sent_at: datetime | None = None


class AlertService:
    def __init__(
        self,
        notifications: NotificationService,
        settings: SettingsRepository,
        *,
        clock: Callable[[], datetime] | None = None,
        battery_escalation_step: int = BATTERY_ESCALATION_STEP,
        credential_window_s: int = CREDENTIAL_ALERT_WINDOW_S,
    ) -> None:
        self._notifications = notifications
        self._settings = settings
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._battery_step = max(1, int(battery_escalation_step))
        self._credential_window_s = max(1, int(credential_window_s))
        self._loop: asyncio.AbstractEventLoop | None = None
        self._closed = False
        self._closing = False
        self._lock: asyncio.Lock | None = None
        self._lock_loop: asyncio.AbstractEventLoop | None = None
        self._reserved: set[str] = set()
        self._inflight: set[concurrent.futures.Future[bool]] = set()

    # --- ingresso ---------------------------------------------------------

    async def alert(self, kind: str, detail: Mapping[str, Any]) -> bool:
        """Compone, deduplica e invia un avviso; ``False`` se non inviato."""
        if self._closed:
            logger.info("avviso scartato: servizio chiuso", extra={"kind": kind})
            return False
        if kind not in ALERT_KINDS:
            logger.warning("avviso scartato: tipo sconosciuto", extra={"kind": kind})
            return False
        text = self._compose(kind, detail)
        if text is None:
            logger.warning("avviso scartato: dettaglio incompleto", extra={"kind": kind})
            return False

        reservation = await self._reserve(kind, detail)
        if reservation is False:
            return False
        if reservation is None:
            # Tipi senza deduplicazione (fallimenti e timeout dei compiti).
            return await self._send(kind, detail, text, marker=None)

        try:
            sent = await self._send(kind, detail, text, marker=reservation)
        finally:
            await self._release(reservation)
        return sent

    def alert_threadsafe(
        self, kind: str, detail: Mapping[str, Any]
    ) -> concurrent.futures.Future[bool] | None:
        """Pianifica ``alert`` sul loop; usato da C-38 dal thread di C-05."""
        loop = self._loop
        if self._closed or self._closing or loop is None:
            logger.warning(
                "avviso non pianificato: loop assente",
                extra={"kind": kind},
            )
            return None
        future = asyncio.run_coroutine_threadsafe(self.alert(kind, detail), loop)
        self._inflight.add(future)
        future.add_done_callback(self._forget)
        return future

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._closed = False
        self._closing = False

    def unbind_loop(self) -> None:
        self._loop = None

    async def close(self) -> None:
        """Chiude il servizio e attende gli avvisi già pianificati."""
        self._closing = True
        self._loop = None
        pending = [future for future in self._inflight if not future.done()]
        if pending:
            wrapped = [asyncio.wrap_future(future) for future in pending]
            try:
                await asyncio.wait_for(
                    asyncio.gather(*wrapped, return_exceptions=True),
                    timeout=CLOSE_TIMEOUT_S,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "avvisi in volo non attesi", extra={"pending": len(pending)}
                )
                for future in pending:
                    future.cancel()
        self._closed = True
        self._closing = False

    # --- deduplicazione ---------------------------------------------------

    async def _reserve(
        self, kind: str, detail: Mapping[str, Any]
    ) -> str | None | bool:
        """Decide se inviare; ``False`` = soppresso, ``None`` = nessuna dedup."""
        if kind not in ("battery_low", "credential"):
            return None
        async with self._lock_for_use():
            if kind == "battery_low":
                level = int(detail["level"])
                threshold = int(detail["threshold"])
                if level >= threshold:
                    if self._settings.get(BATTERY_MARKER) is not None:
                        self._settings.delete(BATTERY_MARKER)
                        logger.info(
                            "marcatore batteria azzerato",
                            extra={"level": level, "threshold": threshold},
                        )
                    return False
                if "battery" in self._reserved:
                    logger.info("avviso batteria deduplicato: invio in corso")
                    return False
                last = self._battery_marker()
                if last is not None and level > last["level"] - self._battery_step:
                    logger.info(
                        "avviso batteria deduplicato",
                        extra={
                            "level": level,
                            "last_level": last["level"],
                            "step": self._battery_step,
                        },
                    )
                    return False
                self._reserved.add("battery")
                return "battery"

            if "credential" in self._reserved:
                logger.info("avviso credenziale deduplicato: invio in corso")
                return False
            last_at = self._credential_marker()
            now = self._now()
            if last_at is not None and now - last_at < timedelta(
                seconds=self._credential_window_s
            ):
                logger.info(
                    "avviso credenziale deduplicato",
                    extra={"window_s": self._credential_window_s},
                )
                return False
            self._reserved.add("credential")
            return "credential"

    async def _release(self, reservation: str) -> None:
        async with self._lock_for_use():
            self._reserved.discard(reservation)

    # --- invio ------------------------------------------------------------

    async def _send(
        self,
        kind: str,
        detail: Mapping[str, Any],
        text: str,
        *,
        marker: str | None,
    ) -> bool:
        try:
            await self._notifications.alert_admin(text)
        except AgenteError as exc:
            logger.error(
                "avviso non inviato",
                extra={"kind": kind, "error": type(exc).__name__},
            )
            return False

        if marker == "battery":
            self._settings.set(
                BATTERY_MARKER,
                json.dumps(
                    {"at": self._now().isoformat(timespec="seconds"),
                     "level": int(detail["level"])}
                ),
            )
        elif marker == "credential":
            self._settings.set(
                CREDENTIAL_MARKER, self._now().isoformat(timespec="seconds")
            )
        event = Alert(kind=kind, detail=detail, sent_at=self._now())
        logger.info(
            "avviso inviato",
            extra={
                "kind": event.kind,
                "sent_at": event.sent_at.isoformat(timespec="seconds")
                if event.sent_at is not None
                else None,
            },
        )
        return True

    # --- composizione -----------------------------------------------------

    def _compose(self, kind: str, detail: Mapping[str, Any]) -> str | None:
        try:
            if kind == "task_failed":
                return f"⚠️ Compito «{detail['task']}» fallito: {detail['reason']}"
            if kind == "task_timeout":
                minutes = max(1, round(float(detail["timeout_s"]) / 60))
                return (
                    f"⏱️ Compito «{detail['task']}» interrotto: "
                    f"timeout dopo {minutes} minuti"
                )
            if kind == "battery_low":
                return (
                    f"🔋 Batteria al {int(detail['level'])}% "
                    f"(soglia {int(detail['threshold'])}%)"
                )
            if kind == "offline_resumed":
                since = _parse(detail["since"])
                until = _parse(detail["until"])
                if since is None or until is None:
                    return None
                local_since = since.astimezone()
                local_until = until.astimezone()
                duration = human_duration(int(detail["offline_s"]))
                return (
                    f"📡 Telefono di nuovo online dopo {duration}: "
                    f"offline dalle {local_since:%d/%m %H:%M} "
                    f"alle {local_until:%d/%m %H:%M}."
                )
            if kind == "credential":
                status = int(detail["status"])
                reason = _CREDENTIAL_REASONS.get(status, "credenziale non valida")
                return (
                    f"🔑 DeepSeek: {reason} (HTTP {status}). "
                    "Controlla la chiave o il credito."
                )
        except (KeyError, TypeError, ValueError):
            return None
        return None

    # --- marcatori --------------------------------------------------------

    def _battery_marker(self) -> dict[str, Any] | None:
        raw = self._settings.get(BATTERY_MARKER)
        if raw is None:
            return None
        try:
            payload = json.loads(raw)
            level = int(payload["level"])
        except (ValueError, TypeError, KeyError):
            logger.warning("marcatore batteria non valido")
            self._settings.delete(BATTERY_MARKER)
            return None
        return {"level": level}

    def _credential_marker(self) -> datetime | None:
        raw = self._settings.get(CREDENTIAL_MARKER)
        if raw is None:
            return None
        moment = _parse(raw)
        if moment is None:
            logger.warning("marcatore credenziale non valido")
            self._settings.delete(CREDENTIAL_MARKER)
        return moment

    # --- utilità ----------------------------------------------------------

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return now.astimezone(timezone.utc)

    def _lock_for_use(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        if self._lock is None or self._lock_loop is not loop:
            self._lock = asyncio.Lock()
            self._lock_loop = loop
        return self._lock

    def _forget(self, future: concurrent.futures.Future[bool]) -> None:
        self._inflight.discard(future)


def _parse(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def human_duration(seconds: int) -> str:
    seconds = max(0, seconds)
    minutes = seconds // 60
    hours, minutes = divmod(minutes, 60)
    if hours and minutes:
        return f"{hours} h {minutes} min"
    if hours:
        return f"{hours} h"
    return f"{minutes} min"


__all__ = [
    "ALERT_KINDS",
    "BATTERY_MARKER",
    "CLOSE_TIMEOUT_S",
    "CREDENTIAL_MARKER",
    "Alert",
    "AlertService",
    "human_duration",
]
