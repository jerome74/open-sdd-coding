"""C-16: interpretazione deterministica e ambiguità mai assunte (AC-02)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from agente.errors import LLMError
from agente.llm import LLMResponse
from agente.schedule_interpreter import (
    Ambiguous,
    Schedule,
    ScheduleError,
    ScheduleInterpreter,
    describe,
    interval_minutes,
    validate_expr,
    weekdays,
)


class FakeLLM:
    def __init__(self, payload: object = None, *, error: bool = False) -> None:
        self.payload = payload
        self.error = error
        self.calls = 0

    def chat(self, messages, tools=None):
        self.calls += 1
        if self.error:
            raise LLMError("modello non disponibile")
        text = self.payload if isinstance(self.payload, str) else json.dumps(self.payload)
        return LLMResponse(text=text)


def clock():
    return datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("text", "expr"),
    [
        ("ogni giorno alle 8", "08:00"),
        ("ogni giorno alle 8:30", "08:30"),
        ("tutti i giorni alle 23", "23:00"),
        ("quotidianamente alle 18:05", "18:05"),
    ],
)
def test_daily_times_are_deterministic(text: str, expr: str) -> None:
    llm = FakeLLM()
    result = ScheduleInterpreter(llm, clock=clock).parse(text)
    assert isinstance(result, Schedule)
    assert (result.type, result.expr) == ("orario", expr)
    assert llm.calls == 0


def test_day_specific_time() -> None:
    llm = FakeLLM()
    result = ScheduleInterpreter(llm, clock=clock).parse("ogni lunedì alle 9:30")
    assert isinstance(result, Schedule)
    assert result.expr == "09:30@LUN"
    assert llm.calls == 0


def test_intervals_are_deterministic() -> None:
    interpreter = ScheduleInterpreter(FakeLLM(), clock=clock)
    for text, expr in (("ogni 2 ore", "2h"), ("ogni 15 minuti", "15m"), ("ogni ora", "1h")):
        result = interpreter.parse(text)
        assert isinstance(result, Schedule)
        assert (result.type, result.expr) == ("intervallo", expr)


def test_vague_time_is_never_assumed() -> None:
    llm = FakeLLM({"type": "orario", "expr": "08:00"})
    result = ScheduleInterpreter(llm, clock=clock).parse("la mattina")
    assert isinstance(result, Ambiguous)
    assert llm.calls == 0


def test_day_without_time_is_ambiguous() -> None:
    result = ScheduleInterpreter(FakeLLM(), clock=clock).parse("ogni lunedì")
    assert isinstance(result, Ambiguous)


def test_llm_normalises_unknown_phrases_and_result_is_validated() -> None:
    llm = FakeLLM({"type": "orario", "expr": "20:00"})
    result = ScheduleInterpreter(llm, clock=clock).parse("dopo il telegiornale")
    assert isinstance(result, Schedule)
    assert result.expr == "20:00"
    assert llm.calls == 1


def test_llm_proposal_with_invalid_expr_is_rejected() -> None:
    llm = FakeLLM({"type": "orario", "expr": "25:99"})
    result = ScheduleInterpreter(llm, clock=clock).parse("dopo il telegiornale")
    assert isinstance(result, Ambiguous)


def test_llm_ambiguity_is_relayed() -> None:
    llm = FakeLLM({"type": "ambiguo", "domanda": "A che ora?"})
    result = ScheduleInterpreter(llm, clock=clock).parse("dopo il telegiornale")
    assert isinstance(result, Ambiguous)
    assert result.question == "A che ora?"


def test_llm_failure_is_fail_safe() -> None:
    result = ScheduleInterpreter(FakeLLM(error=True), clock=clock).parse("dopo il telegiornale")
    assert isinstance(result, Ambiguous)


def test_empty_text_is_ambiguous() -> None:
    assert isinstance(ScheduleInterpreter(None, clock=clock).parse("  "), Ambiguous)


def test_validate_expr_normalises_days() -> None:
    schedule = validate_expr("orario", "08:00@DOM,LUN")
    assert schedule.expr == "08:00@LUN,DOM"
    assert weekdays(schedule) == ("LUN", "DOM")


@pytest.mark.parametrize("expr", ["25:00", "08:60", "8", "08:00@XYZ", "08:00@LUN,LUN"])
def test_invalid_orario_rejected(expr: str) -> None:
    with pytest.raises(ScheduleError):
        validate_expr("orario", expr)


@pytest.mark.parametrize("expr", ["0m", "abc", "2d", "-5m"])
def test_invalid_interval_rejected(expr: str) -> None:
    with pytest.raises(ScheduleError):
        validate_expr("intervallo", expr)


def test_helpers() -> None:
    assert interval_minutes(Schedule("intervallo", "2h")) == 120
    assert interval_minutes(Schedule("intervallo", "15m")) == 15
    assert interval_minutes(Schedule("orario", "08:00")) is None
    assert describe(Schedule("orario", "08:00")) == "ogni giorno alle 08:00"
    assert describe(Schedule("orario", "09:30@LUN,MER")) == "ogni lunedì, mercoledì alle 09:30"
    assert describe(Schedule("intervallo", "2h")) == "ogni 2 ore"
    assert describe(Schedule("intervallo", "45m")) == "ogni 45 minuti"
