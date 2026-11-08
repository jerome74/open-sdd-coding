"""C-16 Schedule Interpreter — interpreta orario e intervallo (spec 02).

Le forme italiane riconosciute sono tradotte in un'espressione canonica e
validate in codice: le ambiguità non si assumono mai (FR-001, BR-14, AC-02).
Il LLM (C-05) interviene solo per normalizzare frasi non riconosciute e la sua
proposta viene comunque ri-validata qui: nessuna assunzione, nessun orario
inventato.

Espressioni canoniche (persistite in ``tasks.schedule_expr``):

- ``orario``: ``HH:MM`` (giornaliero) oppure ``HH:MM@LUN,MAR`` (giorni ISO
  abbreviati in italiano, nell'ordine LUN…DOM).
- ``intervallo``: ``<N>m`` oppure ``<N>h`` (minuti o ore).

La traduzione in trigger APScheduler è di C-06 (``scheduler.py``): qui non si
importa ``apscheduler``.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Literal

from .errors import AgenteError
from .llm import LLMClient

logger = logging.getLogger("agente.schedule")

ORARIO = "orario"
INTERVALLO = "intervallo"
ScheduleType = Literal["orario", "intervallo"]

DAYS = ("LUN", "MAR", "MER", "GIO", "VEN", "SAB", "DOM")

_DAY_ALIASES = {
    "lun": "LUN",
    "lunedì": "LUN",
    "lunedi": "LUN",
    "mar": "MAR",
    "martedì": "MAR",
    "martedi": "MAR",
    "mer": "MER",
    "mercoledì": "MER",
    "mercoledi": "MER",
    "gio": "GIO",
    "giovedì": "GIO",
    "giovedi": "GIO",
    "ven": "VEN",
    "venerdì": "VEN",
    "venerdi": "VEN",
    "sab": "SAB",
    "sabato": "SAB",
    "dom": "DOM",
    "domenica": "DOM",
}

# Parole che indicano una fascia, non un istante: si chiede di precisare invece
# di dedurre un orario (AC-02).
_VAGUE = (
    "mattina",
    "mattino",
    "pomeriggio",
    "sera",
    "serata",
    "notte",
    "presto",
    "tardi",
    "spesso",
    "ogni tanto",
    "a volte",
    "quando capita",
    "più volte",
    "piu volte",
)

_TIME = r"(?P<hour>2[0-3]|1\d|0?\d)(?::(?P<minute>[0-5]\d))?"
_DAY_TOKEN = re.compile(r"\b(?:" + "|".join(_DAY_ALIASES) + r")\b", re.IGNORECASE)

_DAILY = re.compile(
    r"\b(?:ogni\s+giorno|tutti\s+i\s+giorni|quotidianamente)\b[^0-9]*"
    r"(?:alle|ore)\s*" + _TIME,
    re.IGNORECASE,
)
_DAY_AT_TIME = re.compile(
    r"\b(?:ogni|il|la|tutti\s+i)\s+(?P<day>" + "|".join(_DAY_ALIASES) + r")\b"
    r"[^0-9]*(?:alle|ore)\s*" + _TIME,
    re.IGNORECASE,
)
_INTERVAL = re.compile(
    r"\bogni\s+(?:(?P<one>ora|minuto)\b|(?P<value>\d+)\s*(?P<unit>or[ae]|minut[oi]|h|m|min)\b)",
    re.IGNORECASE,
)

_EXPR_ORARIO = re.compile(r"^(?P<time>(?:[01]\d|2[0-3]):[0-5]\d)(?:@(?P<days>[A-Z]{3}(?:,[A-Z]{3})*))?$")
_EXPR_INTERVALLO = re.compile(r"^(?P<value>[1-9]\d*)(?P<unit>[mh])$")

_LLM_SYSTEM_PROMPT = (
    "Sei un normalizzatore di schedulazioni per un agente personale. "
    "Rispondi SOLO con un oggetto JSON, senza testo aggiuntivo, con questa forma:\n"
    '{"type": "orario", "expr": "HH:MM"} oppure '
    '{"type": "orario", "expr": "HH:MM@LUN,MAR"} oppure '
    '{"type": "intervallo", "expr": "<N>m"|"<N>h"} oppure '
    '{"type": "ambiguo", "domanda": "<richiesta di precisazione in italiano>"}\n'
    "Regole: usa i giorni abbreviati LUN,MAR,MER,GIO,VEN,SAB,DOM. "
    "Se il testo non indica un orario preciso o un intervallo numerico "
    "(per esempio «la mattina», «spesso», «ogni tanto»), rispondi "
    '"ambiguo": non dedurre mai un orario. Non inventare valori.'
)


class ScheduleError(AgenteError):
    """Errore di interpretazione o di espressione di schedulazione."""


@dataclass(frozen=True)
class Schedule:
    """Schedulazione canonica: tipo, espressione, fuso del telefono."""

    type: ScheduleType
    expr: str
    tz: str = ""


@dataclass(frozen=True)
class Ambiguous:
    """Richiesta di precisazione: nessuna schedulazione assunta."""

    question: str


def local_timezone(clock: Callable[[], datetime]) -> str:
    """Nome del fuso orario del telefono, letto a runtime (BR-14)."""
    return str(clock().astimezone().tzinfo)


def validate_expr(schedule_type: str, expr: str) -> Schedule:
    """Valida un'espressione canonica e la restituisce normalizzata."""
    if schedule_type == ORARIO:
        match = _EXPR_ORARIO.match(expr.strip())
        if match is None:
            raise ScheduleError(f"espressione oraria non valida: {expr}")
        days = match.group("days")
        if days is not None:
            tokens = days.split(",")
            if any(token not in DAYS for token in tokens) or len(set(tokens)) != len(tokens):
                raise ScheduleError(f"giorni non validi: {days}")
            ordered = [day for day in DAYS if day in tokens]
            return Schedule(ORARIO, f"{match.group('time')}@{','.join(ordered)}")
        return Schedule(ORARIO, match.group("time"))
    if schedule_type == INTERVALLO:
        match = _EXPR_INTERVALLO.match(expr.strip().lower())
        if match is None:
            raise ScheduleError(f"espressione di intervallo non valida: {expr}")
        return Schedule(INTERVALLO, f"{int(match.group('value'))}{match.group('unit')}")
    raise ScheduleError(f"tipo di schedulazione non ammesso: {schedule_type}")


def interval_minutes(schedule: Schedule) -> int | None:
    """Minuti dell'intervallo, ``None`` per una schedulazione a orario."""
    if schedule.type != INTERVALLO:
        return None
    value = int(schedule.expr[:-1])
    return value * 60 if schedule.expr.endswith("h") else value


def weekdays(schedule: Schedule) -> tuple[str, ...]:
    """Giorni dichiarati (``LUN``…``DOM``); vuoto = tutti i giorni."""
    if schedule.type != ORARIO or "@" not in schedule.expr:
        return ()
    return tuple(schedule.expr.split("@", 1)[1].split(","))


_DAY_LABELS = {
    "LUN": "lunedì",
    "MAR": "martedì",
    "MER": "mercoledì",
    "GIO": "giovedì",
    "VEN": "venerdì",
    "SAB": "sabato",
    "DOM": "domenica",
}


def describe(schedule: Schedule) -> str:
    """Descrizione in italiano della schedulazione, per il riepilogo (C-17)."""
    if schedule.type == ORARIO:
        hour, minute = hour_minute(schedule)
        days = weekdays(schedule)
        if days:
            labels = ", ".join(_DAY_LABELS[day] for day in days)
            return f"ogni {labels} alle {hour:02d}:{minute:02d}"
        return f"ogni giorno alle {hour:02d}:{minute:02d}"
    minutes = interval_minutes(schedule) or 0
    if minutes % 60 == 0:
        hours = minutes // 60
        return f"ogni {hours} ora" if hours == 1 else f"ogni {hours} ore"
    return f"ogni {minutes} minuti"


def hour_minute(schedule: Schedule) -> tuple[int, int]:
    """Ora e minuto di una schedulazione a orario."""
    if schedule.type != ORARIO:
        raise ScheduleError("la schedulazione non è a orario")
    hour, minute = schedule.expr.split("@", 1)[0].split(":")
    return int(hour), int(minute)


class ScheduleInterpreter:
    """C-16: ``parse(text) -> Schedule | Ambiguous``."""

    def __init__(
        self,
        llm: LLMClient | None,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._llm = llm
        self._clock = clock or (lambda: datetime.now().astimezone())

    def parse(self, text: str) -> Schedule | Ambiguous:
        cleaned = text.strip()
        if not cleaned:
            return Ambiguous("Indica quando eseguire il compito (es. «ogni giorno alle 8»).")

        deterministic = self._deterministic(cleaned)
        if isinstance(deterministic, Ambiguous):
            logger.info("schedulazione ambigua", extra={"reason": "espressione_incompleta"})
            return deterministic
        if deterministic is not None:
            logger.info(
                "schedulazione interpretata",
                extra={"source": "deterministico", "type": deterministic.type,
                       "expr": deterministic.expr},
            )
            return deterministic

        if _is_vague(cleaned):
            logger.info("schedulazione ambigua", extra={"reason": "fascia_oraria"})
            return Ambiguous(
                "A che ora esattamente? Indica un orario preciso "
                "(es. «ogni giorno alle 8») oppure un intervallo (es. «ogni 2 ore»)."
            )

        proposed = self._llm_normalize(cleaned)
        if isinstance(proposed, Ambiguous):
            return proposed
        if proposed is None:
            return Ambiguous(
                "Non ho capito la schedulazione. Indica un orario preciso "
                "(es. «ogni giorno alle 8») oppure un intervallo (es. «ogni 2 ore»)."
            )
        logger.info(
            "schedulazione interpretata",
            extra={"source": "llm", "type": proposed.type, "expr": proposed.expr},
        )
        return proposed

    def _deterministic(self, text: str) -> Schedule | Ambiguous | None:
        daily = _DAILY.search(text)
        if daily is not None:
            return _orario(daily.group("hour"), daily.group("minute"), (), self._tz())

        day = _DAY_AT_TIME.search(text)
        if day is not None:
            tokens = (_DAY_ALIASES[day.group("day").lower()],)
            return _orario(day.group("hour"), day.group("minute"), tokens, self._tz())

        interval = _INTERVAL.search(text)
        if interval is not None:
            if interval.group("one"):
                unit = "h" if interval.group("one").lower() == "ora" else "m"
                return Schedule(INTERVALLO, f"1{unit}", self._tz())
            value = int(interval.group("value"))
            raw_unit = interval.group("unit").lower()
            unit = "h" if raw_unit in ("h", "ora", "ore") else "m"
            return Schedule(INTERVALLO, f"{value}{unit}", self._tz())

        if _DAY_TOKEN.search(text):
            return Ambiguous(
                "A che ora? Indica l'orario preciso del giorno scelto "
                "(es. «ogni lunedì alle 9»)."
            )
        return None

    def _llm_normalize(self, text: str) -> Schedule | Ambiguous | None:
        if self._llm is None:
            return None
        try:
            response = self._llm.chat(
                [
                    {"role": "system", "content": _LLM_SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ]
            )
            payload = json.loads(_strip_fence(response.text))
        except (AgenteError, ValueError, TypeError):
            logger.warning("normalizzazione LLM non disponibile")
            return None

        if not isinstance(payload, dict):
            return None
        kind = payload.get("type")
        if kind == "ambiguo":
            question = payload.get("domanda")
            if isinstance(question, str) and question.strip():
                return Ambiguous(question.strip())
            return None
        if kind not in (ORARIO, INTERVALLO):
            return None
        expr = payload.get("expr")
        if not isinstance(expr, str):
            return None
        try:
            schedule = validate_expr(str(kind), expr)
        except ScheduleError:
            logger.warning("espressione LLM scartata dalla validazione")
            return None
        return Schedule(schedule.type, schedule.expr, self._tz())

    def _tz(self) -> str:
        return local_timezone(self._clock)


def _orario(
    hour: str, minute: str | None, days: tuple[str, ...], tz: str
) -> Schedule:
    value = f"{int(hour):02d}:{int(minute or 0):02d}"
    if days:
        ordered = [day for day in DAYS if day in days]
        value = f"{value}@{','.join(ordered)}"
    return Schedule(ORARIO, value, tz)


def _is_vague(text: str) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in _VAGUE)


def _strip_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 2:
            body = lines[1:]
            if body and body[-1].strip().startswith("```"):
                body = body[:-1]
            return "\n".join(body).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end > start:
        return stripped[start : end + 1]
    return stripped
