"""C-12: heartbeat, rilevamento stallo, thread watchdog."""

from __future__ import annotations

import time

from agente.supervisor import Supervisor


def test_stall_triggers_callback() -> None:
    now = [100.0]
    stalls: list[int] = []
    supervisor = Supervisor(
        timeout_s=10,
        on_stall=lambda: stalls.append(1),
        clock=lambda: now[0],
    )

    now[0] = 105
    assert supervisor.check() is False
    supervisor.heartbeat()
    now[0] = 114
    assert supervisor.check() is False
    now[0] = 116
    assert supervisor.check() is True
    assert stalls == [1]


def test_heartbeat_resets_the_timer() -> None:
    now = [0.0]
    stalls: list[int] = []
    supervisor = Supervisor(
        timeout_s=10, on_stall=lambda: stalls.append(1), clock=lambda: now[0]
    )
    now[0] = 9
    supervisor.heartbeat()
    now[0] = 18
    assert supervisor.check() is False
    assert stalls == []


def test_thread_watchdog_detects_stall() -> None:
    stalls: list[int] = []
    supervisor = Supervisor(timeout_s=0.0, on_stall=lambda: stalls.append(1))
    supervisor.start_thread(interval_s=0.01)
    try:
        deadline = time.monotonic() + 1.0
        while not stalls and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        supervisor.stop_thread()

    assert stalls
