"""C-41: messaggio di ripartenza e segnale mancato (spec 11)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import pytest

from agente.boot import OfflinePeriod, RecoverySummary
from agente.errors import TelegramError
from agente.restart import RestartNotifier

NOW = datetime(2026, 11, 4, 9, 0, tzinfo=timezone.utc)


class FakeNotifications:
    def __init__(self, *, fail: bool = False) -> None:
        self.texts: list[str] = []
        self.fail = fail
        self.calls = 0

    async def alert_admin(self, text: str) -> None:
        self.calls += 1
        if self.fail:
            raise TelegramError("telegram non raggiungibile")
        self.texts.append(text)


@pytest.fixture
def env():
    notifications = FakeNotifications()
    notifier = RestartNotifier(
        notifications, at="08:00", clock=lambda: NOW  # type: ignore[arg-type]
    )
    return notifier, notifications


def _summary(recovered: int = 2, missed: int = 3) -> RecoverySummary:
    return RecoverySummary(
        missed_count=missed,
        recovered=recovered,
        offline_period=None,
        liveness_missed=False,
    )


def _period(hours: int = 11) -> OfflinePeriod:
    since = NOW - timedelta(hours=hours)
    return OfflinePeriod(since=since, until=NOW, seconds=hours * 3600)


def test_restart_text_with_period_and_count(env) -> None:
    notifier, notifications = env

    assert asyncio.run(
        notifier.notify_restart(_summary(), _period(), False)
    ) is True

    text = notifications.texts[0]
    assert "Sono di nuovo attivo" in text
    assert "offline dalle" in text
    assert "11 h" in text
    assert "recuperati 2 compiti" in text
    assert "Segnale" not in text


def test_restart_singular_task(env) -> None:
    notifier, notifications = env

    asyncio.run(notifier.notify_restart(_summary(recovered=1), _period(), False))

    assert "recuperato 1 compito" in notifications.texts[0]


def test_restart_text_includes_missed_liveness(env) -> None:
    notifier, notifications = env

    asyncio.run(notifier.notify_restart(_summary(), _period(), True))

    text = notifications.texts[0]
    assert "Segnale delle 08:00 non inviato" in text
    assert "offline dalle" in text.splitlines()[1]


def test_missed_line_omits_window_when_not_in_period(env) -> None:
    notifier, notifications = env
    period = OfflinePeriod(
        since=NOW - timedelta(minutes=30), until=NOW, seconds=1800
    )

    asyncio.run(notifier.notify_restart(_summary(), period, True))

    line = notifications.texts[0].splitlines()[1]
    assert line == "⏰ Segnale delle 08:00 non inviato."


def test_missed_window_is_inclusive(env) -> None:
    notifier, notifications = env
    due = NOW.replace(hour=8, minute=0)
    period = OfflinePeriod(since=due, until=due, seconds=0)

    asyncio.run(notifier.notify_restart(_summary(), period, True))

    assert "— offline dalle" in notifications.texts[0].splitlines()[1]


def test_no_message_without_period(env) -> None:
    notifier, notifications = env

    assert asyncio.run(
        notifier.notify_restart(_summary(), None, False)
    ) is False
    assert notifications.texts == []


def test_explicit_parameters_win_over_summary(env) -> None:
    notifier, notifications = env
    summary = RecoverySummary(
        missed_count=0,
        recovered=0,
        offline_period=None,
        liveness_missed=False,
    )

    assert asyncio.run(
        notifier.notify_restart(summary, _period(), True)
    ) is True
    assert "Segnale delle 08:00 non inviato" in notifications.texts[0]


def test_failed_send_is_logged(env, caplog) -> None:
    notifier, notifications = env
    notifications.fail = True

    with caplog.at_level(logging.ERROR, logger="agente.restart"):
        assert asyncio.run(
            notifier.notify_restart(_summary(), _period(), False)
        ) is False

    assert any(r.message == "ripartenza non inviata" for r in caplog.records)


def test_restart_logs_successful_send(env, caplog) -> None:
    notifier, _notifications = env

    with caplog.at_level(logging.INFO, logger="agente.restart"):
        asyncio.run(notifier.notify_restart(_summary(), _period(), False))

    record = [r for r in caplog.records if r.message == "ripartenza inviata"][0]
    assert record.offline_s == 39600
    assert record.recovered == 2
    assert record.missed == 3


def test_restart_goes_only_to_admin(env) -> None:
    notifier, notifications = env

    asyncio.run(notifier.notify_restart(_summary(), _period(), False))

    assert notifications.calls == 1
    assert notifications.texts
