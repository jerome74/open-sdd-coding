"""C-34: filtro temporale, visibilità per ruolo e resa dello storico (spec 09)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from agente.errors import LLMError
from agente.history import HistoryService
from agente.history_query import (
    EMPTY_HISTORY,
    EMPTY_RETENTION,
    AmbiguousPeriod,
    HistoryQuery,
    ParsedFilter,
    Period,
)
from agente.llm import LLMResponse
from agente.role_guard import Role, RoleGuard
from agente.storage.db import Database
from agente.storage.repositories import Task, User, repositories
from agente.task_manager import TaskManager

ADMIN = 1
USER = 2
NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


class FakeRegistrar:
    def register(self, task):
        return f"task:{task.id}"

    def update(self, task):
        return f"task:{task.id}"

    def unregister(self, task_id: int) -> None:
        return None

    def refresh(self, task_id: int):
        return None

    def next_run(self, task_id: int):
        return None


class FakeLLM:
    def __init__(self, text: str = "", *, error: bool = False) -> None:
        self.text = text
        self.error = error

    def chat(self, messages, tools=None):
        if self.error:
            raise LLMError("boom")
        return LLMResponse(text=self.text)


@pytest.fixture
def env(tmp_path, make_config):
    db = Database(tmp_path / "history.db")
    db.migrate()
    repos = repositories(db.connection)
    repos.users.upsert(User(telegram_id=USER, username="utente", state="accepted"))
    config = make_config(admin_id=ADMIN)
    roles = RoleGuard(config, repos.users)
    manager = TaskManager(
        repos.tasks,
        repos.subscriptions,
        repos.users,
        FakeRegistrar(),
        admin_id=ADMIN,
        min_interval_minutes=1,
    )
    service = HistoryService(
        repos.executions,
        repos.conversations,
        retention_days=30,
        chat_memory_hours=24,
        clock=lambda: NOW,
    )
    query = HistoryQuery(
        service,
        manager,
        retention_days=30,
        clock=lambda: NOW,
        tz=ZoneInfo("Europe/Rome"),
    )
    yield query, manager, repos, service
    db.close()


def _task(repos, name: str = "news") -> Task:
    return repos.tasks.create(
        Task(
            name=name,
            instructions="riassumi",
            schedule_type="orario",
            schedule_expr="08:00",
            created_by=ADMIN,
        )
    )


def _execution(service, task, *, at: str, outcome: str = "ok", summary="fatto"):
    execution = service.record(
        task_id=task.id, trigger="scheduled", requested_by=None, started_at=at
    )
    service.finish(execution.id, outcome=outcome, summary=summary)
    return execution


def test_period_vocabulary(env) -> None:
    query, *_ = env

    labels = {
        "oggi": "oggi (01/11)",
        "ieri": "ieri (31/10)",
        "questa settimana": "questa settimana",
        "settimana scorsa": "settimana scorsa",
        "questo mese": "questo mese",
        "mese scorso": "mese scorso",
        "7g": "ultimi 7 giorni",
        "ultimi 3 giorni": "ultimi 3 giorni",
        "31/10": "31/10",
        "31/10/2026": "31/10",
    }
    for text, label in labels.items():
        parsed = query.parse_filter(text)
        assert isinstance(parsed, ParsedFilter), text
        assert parsed.period.label == label, text
        assert parsed.period_found is True


def test_default_period_is_last_24_hours(env) -> None:
    query, *_ = env

    parsed = query.parse_filter("")

    assert isinstance(parsed, ParsedFilter)
    assert parsed.period_found is False
    assert parsed.period.until == NOW
    assert parsed.period.until - parsed.period.since == timedelta(hours=24)
    assert parsed.period.label == "ultime 24 ore"


def test_explicit_day_and_week(env) -> None:
    query, *_ = env

    parsed = query.parse_filter("ieri")
    assert isinstance(parsed, ParsedFilter)
    assert parsed.period.since.strftime("%Y-%m-%d %H:%M") == "2026-10-31 00:00"
    assert parsed.period.until.strftime("%Y-%m-%d %H:%M:%S") == "2026-10-31 23:59:59"

    week = query.parse_filter("settimana scorsa")
    assert isinstance(week, ParsedFilter)
    assert week.period.since.strftime("%Y-%m-%d") == "2026-10-19"
    assert week.period.until.strftime("%Y-%m-%d %H:%M:%S") == "2026-10-25 23:59:59"


def test_n_days(env) -> None:
    query, *_ = env

    parsed = query.parse_filter("ultimi 7 giorni")

    assert isinstance(parsed, ParsedFilter)
    assert parsed.period.until == NOW
    assert parsed.period.until - parsed.period.since == timedelta(days=7)


def test_day_without_year_in_the_future_uses_the_previous_year(env) -> None:
    query, *_ = env

    parsed = query.parse_filter("31/12")

    assert isinstance(parsed, ParsedFilter)
    assert parsed.period.since.year == 2025


def test_trailing_punctuation_is_ignored(env) -> None:
    query, *_ = env

    parsed = query.parse_filter("ieri?")

    assert isinstance(parsed, ParsedFilter)
    assert parsed.period.label == "ieri (31/10)"


def test_leading_preposition_is_ignored(env) -> None:
    query, *_ = env

    parsed = query.parse_filter("della settimana scorsa")

    assert isinstance(parsed, ParsedFilter)
    assert parsed.period.label == "settimana scorsa"


def test_strip_uses_the_longest_prefix(env) -> None:
    query, *_ = env

    parsed = query.parse_filter("dell'ultima ora")

    assert isinstance(parsed, ParsedFilter)
    assert parsed.task_name == "ultima ora"


def test_generic_names_are_removed(env) -> None:
    query, *_ = env

    parsed = query.parse_filter("dei compiti")

    assert isinstance(parsed, ParsedFilter)
    assert parsed.task_name is None


def test_ambiguous_period_is_not_guessed(env) -> None:
    query, *_ = env

    assert isinstance(query.parse_filter("31/13"), AmbiguousPeriod)
    assert isinstance(query.parse_filter("0g"), AmbiguousPeriod)


def test_llm_fallback_is_validated(env) -> None:
    query, manager, repos, _service = env
    llm = FakeLLM(
        '{"since": "2026-10-31T00:00:00+01:00",'
        ' "until": "2026-10-31T23:59:59+01:00", "label": "ieri"}'
    )
    query._llm = llm

    window = query.parse_window_with_llm("il giorno prima")

    assert isinstance(window, Period)
    assert window.label == "ieri"


def test_invalid_llm_answer_asks_for_precision(env) -> None:
    query, *_ = env
    query._llm = FakeLLM("non json")

    assert isinstance(query.parse_window_with_llm("boh"), AmbiguousPeriod)

    query._llm = FakeLLM(error=True)
    assert isinstance(query.parse_window_with_llm("boh"), AmbiguousPeriod)

    query._llm = None
    assert isinstance(query.parse_window_with_llm("boh"), AmbiguousPeriod)


def test_period_is_clamped_to_retention(env) -> None:
    query, *_ = env
    parsed = query.parse_filter("ultimi 400 giorni")

    history_filter = query.build_filter(parsed, None)

    assert history_filter.since == "2026-10-02T11:00:00+00:00"
    assert "(limitato agli ultimi 30 giorni)" in history_filter.label
    assert history_filter.degenerate is False


def test_llm_window_is_clamped_to_retention(env) -> None:
    query, *_ = env
    query._llm = FakeLLM(
        '{"since": "2020-01-01T00:00:00+00:00",'
        ' "until": "2020-01-02T00:00:00+00:00", "label": "vecchio"}'
    )
    window = query.parse_window_with_llm("vecchissimo")
    parsed = ParsedFilter(window, None, True)

    history_filter = query.build_filter(parsed, None)

    assert history_filter.degenerate is True
    assert history_filter.label == "periodo precedente alla conservazione"


def test_window_before_retention_is_empty(env) -> None:
    query, *_ = env
    query._llm = FakeLLM(
        '{"since": "2020-01-01T00:00:00+00:00",'
        ' "until": "2020-01-02T00:00:00+00:00", "label": "vecchio"}'
    )
    window = query.parse_window_with_llm("vecchissimo")
    history_filter = query.build_filter(ParsedFilter(window, None, True), None)

    assert query.query(Role.ADMIN, ADMIN, history_filter) == []
    assert "precede la retention di 30 giorni" in query.render(
        [], label=history_filter.label, degenerate=history_filter.degenerate
    )


def test_build_filter_rejects_unresolved_name(env) -> None:
    query, *_ = env
    parsed = query.parse_filter("news")

    with pytest.raises(ValueError):
        query.build_filter(parsed, None)


def test_admin_sees_every_execution(env) -> None:
    query, manager, repos, service = env
    first = _task(repos, "news")
    second = _task(repos, "log")
    _execution(service, first, at="2026-10-31T08:00:00+00:00")
    _execution(service, second, at="2026-10-31T09:00:00+00:00")

    parsed = query.parse_filter("ieri")
    fetched = query.query(Role.ADMIN, ADMIN, query.build_filter(parsed, None))

    assert [row.task_id for row in fetched] == [second.id, first.id]


def test_authorized_user_sees_only_visible_tasks(env) -> None:
    query, manager, repos, service = env
    news = _task(repos, "news")
    log = _task(repos, "log")
    repos.subscriptions.add(USER, news.id)
    _execution(service, news, at="2026-10-31T08:00:00+00:00")
    _execution(service, log, at="2026-10-31T09:00:00+00:00")

    parsed = query.parse_filter("ieri")
    fetched = query.query(Role.AUTHORIZED, USER, query.build_filter(parsed, None))

    assert [row.task_id for row in fetched] == [news.id]
    assert query.resolve_task("log", role=Role.AUTHORIZED, user_id=USER) is None
    assert query.resolve_task("news", role=Role.AUTHORIZED, user_id=USER) is not None


def test_unknown_role_gets_no_rows(env) -> None:
    query, *_ = env
    parsed = query.parse_filter("ieri")

    assert query.query(Role.UNKNOWN, 999, query.build_filter(parsed, None)) == []


def test_render_format(env) -> None:
    query, _manager, repos, service = env
    task = _task(repos, "news")
    _execution(service, task, at="2026-10-31T07:00:00+00:00", outcome="ok", summary="fatto")
    parsed = query.parse_filter("ieri")
    fetched = query.query(Role.ADMIN, ADMIN, query.build_filter(parsed, None))

    text = query.render(fetched, label="ieri (31/10)")

    assert text.splitlines()[0] == "Storico — ieri (31/10)"
    assert text.splitlines()[1] == "• 31/10 08:00 — news — ok — fatto"


def test_render_truncates_summary_and_rows(env) -> None:
    query, _manager, repos, service = env
    task = _task(repos, "news")
    for index in range(25):
        _execution(
            service,
            task,
            at=f"2026-10-31T{index % 24:02d}:{index:02d}:00+00:00",
            summary="x" * 200,
        )
    parsed = query.parse_filter("ieri")
    fetched = query.query(Role.ADMIN, ADMIN, query.build_filter(parsed, None))

    text = query.render(fetched, label="ieri (31/10)")

    assert "… (mostrate le 20 esecuzioni più recenti)" in text
    assert len(text.splitlines()) == 22
    assert all("— x" in line for line in text.splitlines()[1:21])
    assert all(len(line.split(" — ")[-1]) <= 121 for line in text.splitlines()[1:21])


def test_render_empty(env) -> None:
    query, *_ = env

    assert query.render([], label="ieri (31/10)") == EMPTY_HISTORY


def test_saltata_is_visible(env) -> None:
    query, _manager, repos, service = env
    task = _task(repos, "news")
    service.record_skipped(task_id=task.id, occurred_at="2026-10-31T08:00:00+02:00")
    parsed = query.parse_filter("ieri")
    fetched = query.query(Role.ADMIN, ADMIN, query.build_filter(parsed, None))

    assert "— saltata —" in query.render(fetched, label="ieri (31/10)")


def test_null_outcome_is_rendered_as_dash(env) -> None:
    query, _manager, repos, service = env
    task = _task(repos, "news")
    service.record(
        task_id=task.id, trigger="scheduled", requested_by=None,
        started_at="2026-10-31T08:00:00+00:00",
    )
    parsed = query.parse_filter("ieri")
    fetched = query.query(Role.ADMIN, ADMIN, query.build_filter(parsed, None))

    assert "— — —" in query.render(fetched, label="ieri (31/10)")


def test_unknown_task_falls_back_to_id(env) -> None:
    query, _manager, repos, service = env
    task = _task(repos, "news")
    _execution(service, task, at="2026-10-31T08:00:00+00:00")
    parsed = query.parse_filter("ieri")
    fetched = query.query(Role.ADMIN, ADMIN, query.build_filter(parsed, None))
    repos.tasks.delete(task.id)

    assert f"compito #{task.id}" in query.render(fetched, label="ieri (31/10)")


def test_render_sanitizes_newlines(env) -> None:
    query, _manager, repos, service = env
    task = _task(repos, "news")
    _execution(
        service, task, at="2026-10-31T08:00:00+00:00",
        summary="prima\nseconda\nterza",
    )
    parsed = query.parse_filter("ieri")
    fetched = query.query(Role.ADMIN, ADMIN, query.build_filter(parsed, None))

    text = query.render(fetched, label="ieri (31/10)")
    assert len(text.splitlines()) == 2
    assert "prima seconda terza" in text


def test_render_tolerates_unparsable_started_at(env) -> None:
    query, _manager, repos, service = env
    task = _task(repos, "news")
    _execution(service, task, at="2026-10-31T08:00:00+00:00")
    parsed = query.parse_filter("ieri")
    fetched = query.query(Role.ADMIN, ADMIN, query.build_filter(parsed, None))
    fetched[0].started_at = "non-una-data"

    assert "??/?? ??:??" in query.render(fetched, label="ieri (31/10)")


def test_query_logs_the_result_count(env, caplog) -> None:
    query, _manager, repos, service = env
    task = _task(repos, "news")
    _execution(service, task, at="2026-10-31T08:00:00+00:00")
    parsed = query.parse_filter("ieri")

    with caplog.at_level(logging.INFO, logger="agente.history_query"):
        query.query(Role.ADMIN, ADMIN, query.build_filter(parsed, None))

    record = [item for item in caplog.records if item.message == "storico consultato"][0]
    assert record.role == "admin"
    assert record.rows == 1
    assert record.truncated is False


def test_unknown_role_is_logged_without_query(env, caplog) -> None:
    query, *_ = env
    parsed = query.parse_filter("ieri")

    with caplog.at_level(logging.INFO, logger="agente.history_query"):
        query.query(Role.UNKNOWN, 999, query.build_filter(parsed, None))

    assert any(record.message == "storico non interrogato" for record in caplog.records)


def test_dst_boundary_uses_wall_clock(env) -> None:
    query, *_ = env
    query._clock = lambda: datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)

    parsed = query.parse_filter("oggi")
    history_filter = query.build_filter(parsed, None)

    # 25/10/2026: l'ora legale finisce alle 03:00 locali (CEST -> CET).
    assert history_filter.since == "2026-10-24T22:00:00+00:00"


@pytest.mark.parametrize("prefix", ["sull'", "nell'", "dall'", "all'"])
def test_apostrophe_prefixes_are_removed(env, prefix) -> None:
    query, *_ = env

    parsed = query.parse_filter(f"{prefix}ultima ora")

    assert isinstance(parsed, ParsedFilter)
    assert parsed.task_name == "ultima ora"


def test_plural_prefixes_are_removed(env) -> None:
    query, *_ = env

    parsed = query.parse_filter("degli ultimi 3 giorni")

    assert isinstance(parsed, ParsedFilter)
    assert parsed.period.label == "ultimi 3 giorni"


@pytest.mark.parametrize("text", ["3 news", "3D printer"])
def test_digit_start_is_ambiguous(env, text) -> None:
    query, *_ = env

    assert isinstance(query.parse_filter(text), AmbiguousPeriod)
