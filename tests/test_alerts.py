"""C-36: composizione, deduplicazione e ponte thread degli avvisi (spec 10)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import pytest

from agente.alerts import (
    BATTERY_MARKER,
    CREDENTIAL_MARKER,
    AlertService,
)
from agente.errors import TelegramError
from agente.storage.db import Database
from agente.storage.repositories import repositories

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)


class FakeNotifications:
    def __init__(self, *, fail: bool = False, delay: float = 0.0) -> None:
        self.texts: list[str] = []
        self.fail = fail
        self.delay = delay
        self.delay_once = False
        self.calls = 0

    async def alert_admin(self, text: str) -> None:
        self.calls += 1
        if self.delay and (not self.delay_once or self.calls == 1):
            await asyncio.sleep(self.delay)
        if self.fail:
            raise TelegramError("telegram non raggiungibile")
        self.texts.append(text)


@pytest.fixture
def env(tmp_path):
    db = Database(tmp_path / "alerts.db")
    db.migrate()
    repos = repositories(db.connection)
    notifications = FakeNotifications()
    clock = {"now": NOW}
    service = AlertService(
        notifications,
        repos.settings,
        clock=lambda: clock["now"],
    )
    yield service, notifications, repos.settings, clock
    db.close()


def _send(service, kind, detail):
    return asyncio.run(service.alert(kind, detail))


def test_alert_texts(env) -> None:
    service, notifications, _settings, _clock = env

    _send(service, "task_failed", {"task": "news", "reason": "LLMError"})
    _send(service, "task_timeout", {"task": "news", "timeout_s": 600})
    _send(service, "battery_low", {"level": 14, "threshold": 15})
    _send(
        service,
        "offline_resumed",
        {
            "since": "2026-11-03T08:00:00+00:00",
            "until": "2026-11-03T10:00:00+00:00",
            "offline_s": 7200,
        },
    )
    _send(service, "credential", {"status": 402})

    assert notifications.texts[0] == "⚠️ Compito «news» fallito: LLMError"
    assert notifications.texts[1] == (
        "⏱️ Compito «news» interrotto: timeout dopo 10 minuti"
    )
    assert notifications.texts[2] == "🔋 Batteria al 14% (soglia 15%)"
    assert "2 h" in notifications.texts[3]
    assert "offline dalle" in notifications.texts[3]
    assert notifications.texts[4] == (
        "🔑 DeepSeek: credito esaurito (HTTP 402). "
        "Controlla la chiave o il credito."
    )


def test_alerts_go_only_to_admin(env) -> None:
    service, notifications, _settings, _clock = env

    _send(service, "task_failed", {"task": "news", "reason": "Errore"})

    assert notifications.texts  # C-10 alert_admin è l'unico canale


def test_task_failure_is_not_deduplicated(env) -> None:
    service, notifications, _settings, _clock = env

    _send(service, "task_failed", {"task": "news", "reason": "Errore"})
    _send(service, "task_failed", {"task": "news", "reason": "Errore"})

    assert len(notifications.texts) == 2


def test_battery_escalates_every_five_points(env) -> None:
    service, notifications, _settings, _clock = env

    _send(service, "battery_low", {"level": 14, "threshold": 15})
    _send(service, "battery_low", {"level": 10, "threshold": 15})
    _send(service, "battery_low", {"level": 9, "threshold": 15})
    _send(service, "battery_low", {"level": 5, "threshold": 15})
    _send(service, "battery_low", {"level": 4, "threshold": 15})

    assert len(notifications.texts) == 3
    assert "14%" in notifications.texts[0]
    assert "9%" in notifications.texts[1]
    assert "4%" in notifications.texts[2]


def test_battery_marker_resets_above_threshold(env) -> None:
    service, notifications, settings, _clock = env

    _send(service, "battery_low", {"level": 14, "threshold": 15})
    assert settings.get(BATTERY_MARKER) is not None

    _send(service, "battery_low", {"level": 15, "threshold": 15})
    assert settings.get(BATTERY_MARKER) is None
    assert len(notifications.texts) == 1

    _send(service, "battery_low", {"level": 14, "threshold": 15})
    assert len(notifications.texts) == 2


def test_corrupted_battery_marker_is_ignored(env) -> None:
    service, notifications, settings, _clock = env
    settings.set(BATTERY_MARKER, "{non-json")

    _send(service, "battery_low", {"level": 14, "threshold": 15})

    assert len(notifications.texts) == 1
    assert settings.get(BATTERY_MARKER) is not None


def test_battery_uses_the_threshold_from_detail(env) -> None:
    service, notifications, _settings, _clock = env

    _send(service, "battery_low", {"level": 30, "threshold": 50})
    _send(service, "battery_low", {"level": 30, "threshold": 20})

    assert len(notifications.texts) == 1
    assert "soglia 50%" in notifications.texts[0]


def test_credential_is_deduplicated_within_one_hour(env) -> None:
    service, notifications, _settings, clock = env

    _send(service, "credential", {"status": 402})
    _send(service, "credential", {"status": 402})
    assert len(notifications.texts) == 1

    clock["now"] = NOW + timedelta(seconds=3600)
    _send(service, "credential", {"status": 401})
    assert len(notifications.texts) == 2


def test_credential_dedup_survives_a_new_service(env, tmp_path) -> None:
    service, notifications, settings, _clock = env
    _send(service, "credential", {"status": 402})

    other = AlertService(
        notifications,
        settings,
        clock=lambda: NOW + timedelta(minutes=30),
    )
    _send(other, "credential", {"status": 402})

    assert len(notifications.texts) == 1


def test_corrupted_credential_marker_is_ignored(env) -> None:
    service, notifications, settings, _clock = env
    settings.set(CREDENTIAL_MARKER, "non-una-data")

    _send(service, "credential", {"status": 402})

    assert len(notifications.texts) == 1


def test_failed_send_does_not_mark_dedup(env) -> None:
    service, notifications, _settings, _clock = env
    notifications.fail = True

    assert _send(service, "credential", {"status": 402}) is False
    notifications.fail = False
    assert _send(service, "credential", {"status": 402}) is True

    assert len(notifications.texts) == 1


def test_send_happens_outside_the_lock(env) -> None:
    service, notifications, _settings, _clock = env
    notifications.delay = 0.3
    notifications.delay_once = True

    async def scenario() -> None:
        first = asyncio.create_task(
            service.alert("credential", {"status": 402})
        )
        await asyncio.sleep(0.05)
        # battery_low usa lo stesso lock della deduplicazione: se il lock
        # fosse tenuto durante l'invio, questo avviso resterebbe in attesa.
        second = asyncio.create_task(
            service.alert("battery_low", {"level": 14, "threshold": 15})
        )
        await asyncio.gather(first, second)

    asyncio.run(scenario())

    assert notifications.texts[0].startswith("🔋")
    assert notifications.texts[1].startswith("🔑")


def test_unknown_kind_is_discarded(env) -> None:
    service, notifications, _settings, _clock = env

    assert _send(service, "sconosciuto", {}) is False
    assert notifications.texts == []


def test_missing_detail_is_discarded(env) -> None:
    service, notifications, _settings, _clock = env

    assert _send(service, "task_failed", {"task": "news"}) is False
    assert notifications.texts == []


def test_timeout_minutes_are_integers(env) -> None:
    service, notifications, _settings, _clock = env

    _send(service, "task_timeout", {"task": "news", "timeout_s": 30})

    assert "1 minuti" in notifications.texts[0]
    assert "." not in notifications.texts[0]


def test_alert_threadsafe_requires_a_bound_loop(env) -> None:
    service, notifications, _settings, _clock = env

    assert service.alert_threadsafe("credential", {"status": 402}) is None
    assert notifications.texts == []


def test_alert_threadsafe_schedules_on_loop(env) -> None:
    service, notifications, _settings, _clock = env

    async def scenario() -> None:
        service.bind_loop(asyncio.get_running_loop())
        await asyncio.to_thread(
            service.alert_threadsafe, "credential", {"status": 402}
        )
        await asyncio.sleep(0.05)

    asyncio.run(scenario())

    assert len(notifications.texts) == 1


def test_unbind_stops_scheduling(env) -> None:
    service, notifications, _settings, _clock = env

    async def scenario() -> None:
        service.bind_loop(asyncio.get_running_loop())
        service.unbind_loop()
        assert service.alert_threadsafe("credential", {"status": 402}) is None

    asyncio.run(scenario())

    assert notifications.texts == []


def test_close_waits_for_inflight_alerts(env) -> None:
    service, notifications, _settings, _clock = env
    notifications.delay = 0.1

    async def scenario() -> None:
        service.bind_loop(asyncio.get_running_loop())
        service.alert_threadsafe("credential", {"status": 402})
        await asyncio.sleep(0)
        await service.close()

    asyncio.run(scenario())

    assert len(notifications.texts) == 1


def test_close_times_out_pending_alerts(env, monkeypatch, caplog) -> None:
    service, notifications, _settings, _clock = env
    notifications.delay = 0.5
    monkeypatch.setattr("agente.alerts.CLOSE_TIMEOUT_S", 0.01)

    async def scenario() -> None:
        service.bind_loop(asyncio.get_running_loop())
        service.alert_threadsafe("credential", {"status": 402})
        await asyncio.sleep(0)
        with caplog.at_level(logging.WARNING, logger="agente.alerts"):
            await service.close()

    asyncio.run(scenario())

    assert any(
        record.message == "avvisi in volo non attesi" for record in caplog.records
    )


def test_logs_sent_and_deduplicated(env, caplog) -> None:
    service, notifications, _settings, _clock = env

    with caplog.at_level(logging.INFO, logger="agente.alerts"):
        _send(service, "battery_low", {"level": 14, "threshold": 15})
        _send(service, "battery_low", {"level": 14, "threshold": 15})

    messages = [record.message for record in caplog.records]
    assert "avviso inviato" in messages
    assert "avviso batteria deduplicato" in messages


def test_task_timeout_text(env) -> None:
    service, notifications, _settings, _clock = env

    _send(service, "task_timeout", {"task": "news", "timeout_s": 600})

    assert notifications.texts == [
        "⏱️ Compito «news» interrotto: timeout dopo 10 minuti"
    ]


def test_logs_marker_reset_and_unplanned(env, caplog) -> None:
    service, _notifications, _settings, _clock = env

    with caplog.at_level(logging.INFO, logger="agente.alerts"):
        _send(service, "battery_low", {"level": 14, "threshold": 15})
        _send(service, "battery_low", {"level": 15, "threshold": 15})
        service.alert_threadsafe("credential", {"status": 402})

    messages = [record.message for record in caplog.records]
    assert "marcatore batteria azzerato" in messages
    assert "avviso non pianificato: loop assente" in messages


def test_logs_discarded_alerts(env, caplog) -> None:
    service, _notifications, _settings, _clock = env

    with caplog.at_level(logging.WARNING, logger="agente.alerts"):
        _send(service, "sconosciuto", {})
        _send(service, "task_failed", {"task": "news"})

    messages = [record.message for record in caplog.records]
    assert "avviso scartato: tipo sconosciuto" in messages
    assert "avviso scartato: dettaglio incompleto" in messages


def test_human_duration_is_public() -> None:
    from agente.alerts import human_duration

    assert human_duration(0) == "0 min"
    assert human_duration(1800) == "30 min"
    assert human_duration(3600) == "1 h"
    assert human_duration(7200) == "2 h"
    assert human_duration(5400) == "1 h 30 min"
