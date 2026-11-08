"""C-34 History Query — filtro, visibilità e resa dello storico (spec 09).

Regole applicate qui, mai delegate al modello:

- l'admin vede tutte le esecuzioni, un utente ``accepted`` solo quelle dei compiti
  a cui è iscritto (BR-12); la visibilità è già nel filtro ``user_id`` di C-11 e
  nella lista compiti di C-15;
- il periodo è interpretato in codice per un insieme chiuso di espressioni
  italiane; il modello (C-05) interviene solo per le frasi non riconosciute e la
  sua finestra è ri-validata qui (D2);
- la finestra è clampata alla retention di 30 giorni: una richiesta più ampia
  viene tagliata e dichiarata, non restituita incompleta in silenzio;
- ogni riga dell'elenco mostra compito, istante, esito e un riassunto breve
  (D1); il testo resta una sola riga.

Il parsing è **puro** (solo clock, nessun accesso a SQLite) così C-14 può
eseguirlo in un thread quando deve chiamare il modello; la risoluzione del
compito e la lettura dello storico restano sul thread dell'event loop.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from datetime import tzinfo
from typing import Any, Callable

from .errors import AgenteError
from .history import HistoryService
from .role_guard import Role
from .storage.repositories import Execution, Task
from .task_manager import TaskManager

logger = logging.getLogger("agente.history_query")

MAX_HISTORY_ROWS = 20
SUMMARY_CHARS = 120

PERIOD_USAGE = (
    "Uso: /history [periodo] [compito]. Periodi: oggi, ieri, questa settimana, "
    "settimana scorsa, questo mese, mese scorso, ultimi N giorni (Ng), GG/MM, "
    "GG/MM/AAAA. Alias: settimana, mese."
)
EMPTY_HISTORY = "Nessuna esecuzione nel periodo."
EMPTY_RETENTION = (
    "Nessuna esecuzione conservata: il periodo precede la retention di "
    "{} giorni."
)
EXPIRED_LABEL = "periodo precedente alla conservazione"

_PREFIXES = (
    "dell'",
    "dello",
    "della",
    "delle",
    "degli",
    "dei",
    "del",
    "con",
    "nel",
    "nella",
    "nelle",
    "sull'",
    "sul",
    "sulla",
    "sulle",
    "nell'",
    "dall'",
    "all'",
    "per",
    "gli",
    "lo",
    "la",
    "le",
    "il",
    "di",
    "su",
    "i",
    "l'",
)
_GENERIC = frozenset({"compiti", "compito", "esecuzioni", "esecuzione", "storico"})

_LLM_PROMPT = (
    "Estrai l'intervallo temporale richiesto dall'utente. Rispondi SOLO con un "
    "oggetto JSON, senza testo aggiuntivo, con questa forma:\n"
    '{"since": "2026-10-31T00:00:00+01:00", '
    '"until": "2026-10-31T23:59:59+01:00", "label": "ieri"}\n'
    "Regole: usa date ISO 8601 con fuso orario; `until` non può essere nel "
    "futuro; `label` è un'etichetta breve in italiano. Non inventare date."
)


@dataclass(frozen=True)
class Period:
    """Finestra temporale proposta dal parser, nel fuso delle query."""

    since: datetime
    until: datetime
    label: str


@dataclass(frozen=True)
class ParsedFilter:
    """Esito del parsing: periodo ed eventuale nome di compito ancora da risolvere."""

    period: Period
    task_name: str | None = None
    period_found: bool = False


@dataclass(frozen=True)
class AmbiguousPeriod:
    """Richiesta di precisazione: nessuna finestra assunta."""

    question: str


@dataclass(frozen=True)
class HistoryFilter:
    """Filtro pronto per C-11, con etichetta e stato di clamp."""

    since: str
    until: str
    task_id: int | None = None
    label: str = "ultime 24 ore"
    degenerate: bool = False


class HistoryQuery:
    def __init__(
        self,
        history: HistoryService,
        tasks: TaskManager,
        *,
        retention_days: int,
        llm: Any = None,
        clock: Callable[[], datetime] | None = None,
        tz: tzinfo | None = None,
        max_rows: int = MAX_HISTORY_ROWS,
        summary_chars: int = SUMMARY_CHARS,
    ) -> None:
        self._history = history
        self._tasks = tasks
        self._retention_days = max(1, int(retention_days))
        self._llm = llm
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._tz = tz or datetime.now().astimezone().tzinfo or timezone.utc
        self._max_rows = max(1, int(max_rows))
        self._summary_chars = max(1, int(summary_chars))

    # --- parsing (puro) -----------------------------------------------------

    def parse_filter(self, text: str) -> ParsedFilter | AmbiguousPeriod:
        cleaned = _prefixless(text)
        if not cleaned:
            return ParsedFilter(self._default_period(), None, False)

        now = self._now()
        for pattern, builder in _PERIOD_PATTERNS:
            match = pattern.match(cleaned)
            if match is None:
                continue
            built = builder(self, match, now)
            if isinstance(built, AmbiguousPeriod):
                return built
            period, rest = built
            return ParsedFilter(period, _task_text(rest), True)

        if cleaned[:1].isdigit():
            return AmbiguousPeriod(PERIOD_USAGE)
        return ParsedFilter(self._default_period(), _task_text(cleaned), False)

    def parse_window_with_llm(self, text: str) -> Period | AmbiguousPeriod:
        """Chiede a C-05 solo la finestra; il risultato è ri-validato qui."""
        if self._llm is None:
            return AmbiguousPeriod(PERIOD_USAGE)
        try:
            response = self._llm.chat(
                [
                    {"role": "system", "content": _LLM_PROMPT},
                    {"role": "user", "content": text},
                ]
            )
            payload = json.loads(_strip_fence(response.text))
            since = _aware(payload["since"], self._tz)
            until = _aware(payload["until"], self._tz)
            label = str(payload.get("label") or "").strip()
        except (AgenteError, ValueError, TypeError, KeyError, AttributeError):
            logger.warning("finestra temporale non interpretata dal modello")
            return AmbiguousPeriod(PERIOD_USAGE)

        now = self._now()
        if since > until or until > now + timedelta(seconds=60):
            logger.warning("finestra temporale del modello non valida")
            return AmbiguousPeriod(PERIOD_USAGE)
        if not label or len(label) > 40:
            return AmbiguousPeriod(PERIOD_USAGE)
        return Period(since, until, label)

    # --- risoluzione e lettura ---------------------------------------------

    def resolve_task(self, name: str, *, role: Role, user_id: int) -> Task | None:
        cleaned = (name or "").strip()
        if not cleaned:
            return None
        task = self._tasks.find(cleaned)
        if task is None:
            return None
        if role is Role.ADMIN:
            return task
        if role is Role.AUTHORIZED:
            visible = {
                view.task.id for view in self._tasks.list(role, user_id)
            }
            return task if task.id in visible else None
        return None

    def build_filter(
        self, parsed: ParsedFilter, task: Task | None
    ) -> HistoryFilter:
        if parsed.task_name and task is None:
            raise ValueError("compito non risolto")
        now = self._now()
        cutoff = now - timedelta(days=self._retention_days)
        since = parsed.period.since
        until = parsed.period.until
        label = parsed.period.label
        degenerate = False
        if until <= cutoff:
            since = cutoff
            until = cutoff - timedelta(seconds=1)
            label = EXPIRED_LABEL
            degenerate = True
        elif since < cutoff:
            since = cutoff
            label = (
                f"{label} (limitato agli ultimi {self._retention_days} giorni)"
            )
        return HistoryFilter(
            since=since.astimezone(timezone.utc).isoformat(timespec="seconds"),
            until=until.astimezone(timezone.utc).isoformat(timespec="seconds"),
            task_id=task.id if task is not None else None,
            label=label,
            degenerate=degenerate,
        )

    def query(
        self, role: Role, user_id: int, filter: HistoryFilter
    ) -> list[Execution]:
        if role is Role.UNKNOWN:
            logger.info(
                "storico non interrogato",
                extra={"role": role.value, "user_id": user_id},
            )
            return []
        executions = self._history.query(
            user_id=None if role is Role.ADMIN else user_id,
            since=filter.since,
            until=filter.until,
            task_id=filter.task_id,
            limit=self._max_rows + 1,
        )
        truncated = len(executions) > self._max_rows
        logger.info(
            "storico consultato",
            extra={
                "role": role.value,
                "user_id": user_id,
                "since": filter.since,
                "until": filter.until,
                "task_id": filter.task_id,
                "rows": min(len(executions), self._max_rows),
                "truncated": truncated,
            },
        )
        return executions

    def render(
        self,
        executions: list[Execution],
        *,
        label: str,
        degenerate: bool = False,
    ) -> str:
        if degenerate:
            return EMPTY_RETENTION.format(self._retention_days)
        if not executions:
            return EMPTY_HISTORY
        truncated = len(executions) > self._max_rows
        lines = [f"Storico — {label}"]
        lines.extend(
            self._line(execution) for execution in executions[: self._max_rows]
        )
        if truncated:
            lines.append(
                f"… (mostrate le {self._max_rows} esecuzioni più recenti)"
            )
        return "\n".join(lines)

    # --- interni ------------------------------------------------------------

    def _line(self, execution: Execution) -> str:
        task = self._tasks.get(execution.task_id)
        name = _one_line(task.name if task is not None else f"compito #{execution.task_id}")
        moment = _parse(execution.started_at)
        when = (
            moment.astimezone(self._tz).strftime("%d/%m %H:%M")
            if moment is not None
            else "??/?? ??:??"
        )
        outcome = execution.outcome or "—"
        summary = _one_line(execution.summary or "—")
        if len(summary) > self._summary_chars:
            summary = summary[: self._summary_chars] + "…"
        return f"• {when} — {name} — {outcome} — {summary}"

    def _default_period(self) -> Period:
        now = self._now()
        return Period(now - timedelta(hours=24), now, "ultime 24 ore")

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return now.astimezone(self._tz)

    def _today(self) -> datetime:
        now = self._now()
        return datetime(now.year, now.month, now.day, tzinfo=self._tz)


# --- costruzione del periodo -------------------------------------------------


def _day(now: datetime, *, days: int = 0, tz: tzinfo) -> datetime:
    moment = now.astimezone(tz) - timedelta(days=days)
    return datetime(moment.year, moment.month, moment.day, tzinfo=tz)


def _week_start(now: datetime, *, weeks: int = 0, tz: tzinfo) -> datetime:
    day = _day(now, tz=tz) - timedelta(days=weeks * 7)
    return day - timedelta(days=day.weekday())


def _month_start(now: datetime, *, months: int = 0, tz: tzinfo) -> datetime:
    year, month = now.year, now.month - months
    while month <= 0:
        month += 12
        year -= 1
    return datetime(year, month, 1, tzinfo=tz)


def _build_oggi(
    query: HistoryQuery, match: re.Match[str], now: datetime
) -> tuple[Period, str]:
    start = _day(now, tz=query._tz)
    return Period(start, now, f"oggi ({start:%d/%m})"), match.string[match.end():]


def _build_ieri(
    query: HistoryQuery, match: re.Match[str], now: datetime
) -> tuple[Period, str]:
    start = _day(now, days=1, tz=query._tz)
    end = start + timedelta(days=1) - timedelta(seconds=1)
    return Period(start, end, f"ieri ({start:%d/%m})"), match.string[match.end():]


def _build_this_week(
    query: HistoryQuery, match: re.Match[str], now: datetime
) -> tuple[Period, str]:
    return Period(_week_start(now, tz=query._tz), now, "questa settimana"), match.string[match.end():]


def _build_last_week(
    query: HistoryQuery, match: re.Match[str], now: datetime
) -> tuple[Period, str]:
    start = _week_start(now, weeks=1, tz=query._tz)
    end = _week_start(now, tz=query._tz) - timedelta(seconds=1)
    return Period(start, end, "settimana scorsa"), match.string[match.end():]


def _build_this_month(
    query: HistoryQuery, match: re.Match[str], now: datetime
) -> tuple[Period, str]:
    return Period(_month_start(now, tz=query._tz), now, "questo mese"), match.string[match.end():]


def _build_last_month(
    query: HistoryQuery, match: re.Match[str], now: datetime
) -> tuple[Period, str]:
    start = _month_start(now, months=1, tz=query._tz)
    end = _month_start(now, tz=query._tz) - timedelta(seconds=1)
    return Period(start, end, "mese scorso"), match.string[match.end():]


def _build_days(
    query: HistoryQuery, match: re.Match[str], now: datetime
) -> tuple[Period, str] | AmbiguousPeriod:
    days = int(match.group(1))
    if days < 1:
        return AmbiguousPeriod(PERIOD_USAGE)
    return (
        Period(now - timedelta(days=days), now, f"ultimi {days} giorni"),
        match.string[match.end():],
    )


def _build_date(
    query: HistoryQuery, match: re.Match[str], now: datetime
) -> tuple[Period, str] | AmbiguousPeriod:
    day, month = int(match.group(1)), int(match.group(2))
    year = int(match.group(3)) if match.group(3) else now.year
    try:
        start = datetime(year, month, day, tzinfo=query._tz)
    except ValueError:
        return AmbiguousPeriod(PERIOD_USAGE)
    if match.group(3) is None and start > now + timedelta(days=1):
        try:
            start = datetime(year - 1, month, day, tzinfo=query._tz)
        except ValueError:
            return AmbiguousPeriod(PERIOD_USAGE)
    end = start + timedelta(days=1) - timedelta(seconds=1)
    return Period(start, end, f"{day:02d}/{month:02d}"), match.string[match.end():]


_PERIOD_PATTERNS: tuple[
    tuple[re.Pattern[str], Callable[..., Any]], ...
] = (
    (re.compile(r"^settimana\s+scorsa\b", re.IGNORECASE), _build_last_week),
    (re.compile(r"^questa\s+settimana\b", re.IGNORECASE), _build_this_week),
    (re.compile(r"^settimana(?:\s+|$)", re.IGNORECASE), _build_this_week),
    (re.compile(r"^mese\s+scorso\b", re.IGNORECASE), _build_last_month),
    (re.compile(r"^questo\s+mese\b", re.IGNORECASE), _build_this_month),
    (re.compile(r"^mese(?:\s+|$)", re.IGNORECASE), _build_this_month),
    (re.compile(r"^ultimi\s+(\d{1,3})\s+giorn[oi]\b", re.IGNORECASE), _build_days),
    (re.compile(r"^(\d{1,3})\s*g\b", re.IGNORECASE), _build_days),
    (re.compile(r"^oggi\b", re.IGNORECASE), _build_oggi),
    (re.compile(r"^ieri\b", re.IGNORECASE), _build_ieri),
    (
        re.compile(r"^(\d{1,2})/(\d{1,2})(?:/(\d{4}))?\b", re.IGNORECASE),
        _build_date,
    ),
)


# --- normalizzazione del testo ----------------------------------------------


def _clean(text: str) -> str:
    return (text or "").strip().strip("?!.,;: ").strip()


def _prefixless(text: str) -> str:
    """Rimuove spazi, punteggiatura finale e prefissi iniziali (P-A-21)."""
    cleaned = _clean(text)
    while cleaned:
        lowered = cleaned.casefold()
        for prefix in _PREFIXES:
            if not lowered.startswith(prefix):
                continue
            rest = cleaned[len(prefix):]
            if prefix.endswith("'"):
                if rest[:1].isalpha():
                    cleaned = rest.strip()
                    break
            elif not rest or rest[:1].isspace():
                cleaned = rest.strip()
                break
        else:
            break
    return cleaned


def _task_text(text: str) -> str | None:
    """Rimuove prefissi, articoli e nomi generici dal resto della richiesta."""
    words = _prefixless(text).split()
    while words and words[-1].casefold() in _GENERIC:
        words.pop()
    result = " ".join(words).strip()
    return result or None


def _one_line(text: str) -> str:
    return " ".join(str(text).split())


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


def _aware(value: Any, tz: tzinfo) -> datetime:
    moment = datetime.fromisoformat(str(value))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=tz)
    return moment.astimezone(tz)


def _strip_fence(text: str) -> str:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if "\n" in cleaned:
            cleaned = cleaned.split("\n", 1)[1]
    return cleaned.strip()


__all__ = [
    "AmbiguousPeriod",
    "EMPTY_HISTORY",
    "EMPTY_RETENTION",
    "HistoryFilter",
    "HistoryQuery",
    "MAX_HISTORY_ROWS",
    "PERIOD_USAGE",
    "ParsedFilter",
    "Period",
    "SUMMARY_CHARS",
]
