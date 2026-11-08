"""C-37 Device Monitor — batteria, connettività e periodo offline (spec 10).

Il monitor è l'unico scrittore di ``offline_since`` e di ``last_online_at``.
C-19 delega qui il tracciamento del rientro e conserva solo il recupero delle
occorrenze. Le letture di C-07 (subprocess) sono offloadate in
``asyncio.to_thread``; i marcatori in ``settings`` sono toccati solo sul thread
dell'event loop, perché la connessione SQLite non è condivisibile fra thread.

Un ``DeviceError`` non è mai un avviso: la batteria illeggibile non deve
simulare una batteria scarica e la rete illeggibile non deve aprire un falso
periodo offline.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from .alerts import AlertService
from .device import DeviceAdapter
from .errors import DeviceError
from .storage.repositories import SettingsRepository

logger = logging.getLogger("agente.device_monitor")

OFFLINE_SINCE = "offline_since"
LAST_ONLINE_AT = "last_online_at"


@dataclass(frozen=True)
class OnlineStatus:
    online: bool | None
    resumed: bool = False
    offline_s: int | None = None


class DeviceMonitor:
    def __init__(
        self,
        device: DeviceAdapter,
        settings: SettingsRepository,
        alerts: AlertService,
        *,
        battery_threshold_pct: int,
        offline_threshold_s: int,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._device = device
        self._settings = settings
        self._alerts = alerts
        self._battery_threshold = max(0, int(battery_threshold_pct))
        self._offline_threshold_s = max(0, int(offline_threshold_s))
        self._clock = clock or (lambda: datetime.now().astimezone())

    # --- batteria ---------------------------------------------------------

    async def check_battery(self) -> int | None:
        try:
            level = await asyncio.to_thread(self._device.battery_level)
        except DeviceError as exc:
            logger.warning("batteria non leggibile", extra={"error": str(exc)})
            return None
        logger.info(
            "batteria letta",
            extra={"level": level, "threshold": self._battery_threshold},
        )
        await self._alerts.alert(
            "battery_low",
            {"level": level, "threshold": self._battery_threshold},
        )
        return level

    # --- connettività -----------------------------------------------------

    async def check_online(self) -> OnlineStatus:
        online = await self.is_online()
        if online is None:
            return OnlineStatus(online=None)
        now = self._now()
        if not online:
            existed, moment = self._read_offline_since()
            if not existed or moment is None:
                # Nessun periodo in corso, o marcatore invalido appena
                # cancellato: il periodo riparte da adesso.
                self._settings.set(
                    OFFLINE_SINCE, now.isoformat(timespec="seconds")
                )
                logger.info(
                    "periodo offline iniziato",
                    extra={"since": now.isoformat(timespec="seconds")},
                )
            return OnlineStatus(online=False)

        self._device.record_last_contact(self._settings, now)
        self._settings.set(LAST_ONLINE_AT, now.isoformat(timespec="seconds"))
        existed, since = self._read_offline_since()
        if not existed:
            return OnlineStatus(online=True)

        duration: int | None = None
        if since is not None:
            duration = max(0, int((self._now() - since).total_seconds()))
        self._settings.delete(OFFLINE_SINCE)
        offline_s = duration
        if duration is not None and duration > self._offline_threshold_s:
            logger.info(
                "rientro online dopo un periodo prolungato",
                extra={"offline_s": duration, "threshold_s": self._offline_threshold_s},
            )
            await self._alerts.alert(
                "offline_resumed",
                {
                    "since": since.isoformat(timespec="seconds"),
                    "until": self._now().isoformat(timespec="seconds"),
                    "offline_s": duration,
                },
            )
        else:
            logger.info(
                "rientro online",
                extra={"offline_s": offline_s, "threshold_s": self._offline_threshold_s},
            )
        return OnlineStatus(online=True, resumed=True, offline_s=offline_s)

    async def is_online(self) -> bool | None:
        """Lettura pura per C-19: nessun marcatore, nessun avviso."""
        try:
            return bool(await asyncio.to_thread(self._device.is_online))
        except DeviceError as exc:
            logger.warning("stato di rete non leggibile", extra={"error": str(exc)})
            return None

    def offline_since(self) -> datetime | None:
        _existed, moment = self._read_offline_since()
        return moment

    # --- interni ----------------------------------------------------------

    def _read_offline_since(self) -> tuple[bool, datetime | None]:
        raw = self._settings.get(OFFLINE_SINCE)
        if raw is None:
            return False, None
        moment = _parse(raw)
        if moment is None or moment > self._now():
            logger.warning(
                "marcatore offline non valido", extra={"value": raw}
            )
            self._settings.delete(OFFLINE_SINCE)
            return True, None
        return True, moment

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return now.astimezone(timezone.utc)


def _parse(value: str) -> datetime | None:
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


__all__ = ["DeviceMonitor", "LAST_ONLINE_AT", "OFFLINE_SINCE", "OnlineStatus"]
