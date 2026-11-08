"""C-37: batteria, connettività e marcatori offline (spec 10)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from agente.alerts import AlertService
from agente.device_monitor import LAST_ONLINE_AT, OFFLINE_SINCE, DeviceMonitor
from agente.errors import DeviceError
from agente.storage.db import Database
from agente.storage.repositories import repositories

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)


class FakeNotifications:
    def __init__(self) -> None:
        self.texts: list[str] = []

    async def alert_admin(self, text: str) -> None:
        self.texts.append(text)


class FakeDevice:
    def __init__(
        self,
        *,
        battery: int = 50,
        online: bool = True,
        battery_error: bool = False,
        online_error: bool = False,
    ) -> None:
        self.battery = battery
        self.online = online
        self.battery_error = battery_error
        self.online_error = online_error
        self.contacts: list[object] = []

    def battery_level(self) -> int:
        if self.battery_error:
            raise DeviceError("termux-battery-status assente")
        return self.battery

    def is_online(self) -> bool:
        if self.online_error:
            raise DeviceError("termux-wifi-connectioninfo assente")
        return self.online

    def record_last_contact(self, settings, when=None) -> str:
        self.contacts.append(when)
        moment = (when or NOW).isoformat(timespec="seconds")
        settings.set("last_contact_at", moment)
        return moment


@pytest.fixture
def env(tmp_path):
    db = Database(tmp_path / "monitor.db")
    db.migrate()
    repos = repositories(db.connection)
    notifications = FakeNotifications()
    clock = {"now": NOW}
    alerts = AlertService(
        notifications, repos.settings, clock=lambda: clock["now"]
    )
    device = FakeDevice()
    monitor = DeviceMonitor(
        device,
        repos.settings,
        alerts,
        battery_threshold_pct=15,
        offline_threshold_s=3600,
        clock=lambda: clock["now"],
    )
    yield monitor, device, repos.settings, notifications, clock
    db.close()


def test_battery_reading_is_returned(env) -> None:
    monitor, device, _settings, notifications, _clock = env
    device.battery = 42

    assert asyncio.run(monitor.check_battery()) == 42
    assert notifications.texts == []


def test_battery_below_threshold_alerts(env) -> None:
    monitor, device, _settings, notifications, _clock = env
    device.battery = 14

    assert asyncio.run(monitor.check_battery()) == 14

    assert notifications.texts == ["🔋 Batteria al 14% (soglia 15%)"]


def test_battery_at_threshold_does_not_alert(env) -> None:
    monitor, device, _settings, notifications, _clock = env
    device.battery = 15

    assert asyncio.run(monitor.check_battery()) == 15

    assert notifications.texts == []


def test_battery_at_threshold_resets_marker(env) -> None:
    monitor, device, _settings, notifications, _clock = env
    device.battery = 14
    asyncio.run(monitor.check_battery())
    device.battery = 15
    asyncio.run(monitor.check_battery())

    assert len(notifications.texts) == 1
    device.battery = 14
    asyncio.run(monitor.check_battery())
    assert len(notifications.texts) == 2


def test_battery_unreadable_is_silent(env) -> None:
    monitor, device, _settings, notifications, _clock = env
    device.battery_error = True

    assert asyncio.run(monitor.check_battery()) is None
    assert notifications.texts == []


def test_offline_marker_is_written(env) -> None:
    monitor, device, settings, notifications, _clock = env
    device.online = False

    status = asyncio.run(monitor.check_online())

    assert status.online is False
    assert settings.get(OFFLINE_SINCE) is not None
    assert notifications.texts == []


def test_long_offline_alerts_on_return(env) -> None:
    monitor, device, settings, notifications, clock = env
    settings.set(OFFLINE_SINCE, "2026-11-03T09:00:00+00:00")
    device.online = True

    status = asyncio.run(monitor.check_online())

    assert status.online is True
    assert status.resumed is True
    assert status.offline_s == 10800
    assert settings.get(OFFLINE_SINCE) is None
    assert len(notifications.texts) == 1
    assert "3 h" in notifications.texts[0]


def test_short_offline_does_not_alert(env) -> None:
    monitor, device, settings, notifications, clock = env
    settings.set(OFFLINE_SINCE, "2026-11-03T11:30:00+00:00")
    device.online = True

    status = asyncio.run(monitor.check_online())

    assert status.resumed is True
    assert status.offline_s == 1800
    assert settings.get(OFFLINE_SINCE) is None
    assert notifications.texts == []


def test_one_alert_per_offline_period(env) -> None:
    monitor, device, settings, notifications, _clock = env
    settings.set(OFFLINE_SINCE, "2026-11-03T09:00:00+00:00")
    device.online = True
    asyncio.run(monitor.check_online())
    asyncio.run(monitor.check_online())

    assert len(notifications.texts) == 1


def test_offline_marker_is_cleared_after_a_failed_alert(env) -> None:
    monitor, device, settings, notifications, _clock = env
    settings.set(OFFLINE_SINCE, "2026-11-03T09:00:00+00:00")
    device.online = True

    async def failing_alert(kind, detail):
        return False

    monitor._alerts.alert = failing_alert  # type: ignore[method-assign]

    status = asyncio.run(monitor.check_online())

    assert status.resumed is True
    assert settings.get(OFFLINE_SINCE) is None


def test_unknown_state_does_not_touch_markers(env) -> None:
    monitor, device, settings, notifications, _clock = env
    device.online_error = True
    settings.set(OFFLINE_SINCE, "2026-11-03T09:00:00+00:00")

    status = asyncio.run(monitor.check_online())

    assert status.online is None
    assert settings.get(OFFLINE_SINCE) == "2026-11-03T09:00:00+00:00"
    assert notifications.texts == []


def test_invalid_marker_is_cleared_and_recovers(env) -> None:
    monitor, device, settings, notifications, _clock = env
    settings.set(OFFLINE_SINCE, "non-una-data")
    device.online = True

    status = asyncio.run(monitor.check_online())

    assert status.online is True
    assert status.resumed is True
    assert status.offline_s is None
    assert settings.get(OFFLINE_SINCE) is None
    assert notifications.texts == []


def test_future_marker_is_cleared_and_recovers(env) -> None:
    monitor, device, settings, notifications, _clock = env
    settings.set(OFFLINE_SINCE, "2026-11-04T09:00:00+00:00")
    device.online = True

    status = asyncio.run(monitor.check_online())

    assert status.resumed is True
    assert status.offline_s is None
    assert settings.get(OFFLINE_SINCE) is None
    assert notifications.texts == []


def test_offline_since_getter(env) -> None:
    monitor, _device, settings, _notifications, _clock = env
    settings.set(OFFLINE_SINCE, "2026-11-03T09:00:00+00:00")

    assert monitor.offline_since() == datetime(
        2026, 11, 3, 9, 0, tzinfo=timezone.utc
    )


def test_last_online_and_last_contact_are_written(env) -> None:
    monitor, device, settings, _notifications, _clock = env

    asyncio.run(monitor.check_online())

    assert settings.get(LAST_ONLINE_AT) is not None
    assert settings.get("last_contact_at") is not None
    assert device.contacts


def test_is_online_does_not_write_markers(env) -> None:
    monitor, device, settings, notifications, _clock = env
    device.online_error = False

    assert asyncio.run(monitor.is_online()) is True

    assert settings.get(OFFLINE_SINCE) is None
    assert settings.get(LAST_ONLINE_AT) is None
    assert notifications.texts == []


def test_is_online_unreadable_returns_none(env) -> None:
    monitor, device, _settings, _notifications, _clock = env
    device.online_error = True

    assert asyncio.run(monitor.is_online()) is None


def test_logs_level_and_threshold(env, caplog) -> None:
    import logging

    monitor, device, _settings, _notifications, _clock = env
    device.battery = 14

    with caplog.at_level(logging.INFO, logger="agente.device_monitor"):
        asyncio.run(monitor.check_battery())

    record = [r for r in caplog.records if r.message == "batteria letta"][0]
    assert record.level == 14
    assert record.threshold == 15


def test_logs_network_state(env, caplog) -> None:
    import logging

    monitor, _device, settings, _notifications, _clock = env
    settings.set(OFFLINE_SINCE, "2026-11-03T09:00:00+00:00")

    with caplog.at_level(logging.INFO, logger="agente.device_monitor"):
        asyncio.run(monitor.check_online())

    assert any(
        record.message == "rientro online dopo un periodo prolungato"
        for record in caplog.records
    )


def test_offline_marker_is_written_and_cleared(env) -> None:
    monitor, device, settings, _notifications, _clock = env
    device.online = False
    asyncio.run(monitor.check_online())
    assert settings.get(OFFLINE_SINCE) is not None

    device.online = True
    asyncio.run(monitor.check_online())
    assert settings.get(OFFLINE_SINCE) is None


def test_logs_unreadable_and_invalid_marker(env, caplog) -> None:
    import logging

    monitor, device, settings, _notifications, _clock = env
    device.battery_error = True
    with caplog.at_level(logging.WARNING, logger="agente.device_monitor"):
        asyncio.run(monitor.check_battery())

    device.battery_error = False
    device.online_error = True
    with caplog.at_level(logging.WARNING, logger="agente.device_monitor"):
        asyncio.run(monitor.check_online())

    device.online_error = False
    settings.set(OFFLINE_SINCE, "non-una-data")
    with caplog.at_level(logging.WARNING, logger="agente.device_monitor"):
        asyncio.run(monitor.check_online())

    messages = [record.message for record in caplog.records]
    assert "batteria non leggibile" in messages
    assert "stato di rete non leggibile" in messages
    assert "marcatore offline non valido" in messages
