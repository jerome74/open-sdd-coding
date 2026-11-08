"""AC-04: 3 tentativi a 1 minuto prima del fallimento."""

from __future__ import annotations

import asyncio

import pytest

from agente.retry import async_retry_call, retry_call


def test_retries_three_times_with_one_minute_delay() -> None:
    sleeps: list[float] = []
    calls: list[int] = []

    def failing() -> None:
        calls.append(1)
        raise ConnectionError("rete")

    with pytest.raises(ConnectionError):
        retry_call(failing, attempts=3, delay_s=60, sleep=sleeps.append)

    assert len(calls) == 3
    assert sleeps == [60, 60]


def test_success_on_third_attempt() -> None:
    sleeps: list[float] = []
    calls: list[int] = []

    def flaky() -> str:
        calls.append(1)
        if len(calls) < 3:
            raise TimeoutError("lento")
        return "ok"

    assert retry_call(flaky, attempts=3, delay_s=60, sleep=sleeps.append) == "ok"
    assert len(calls) == 3
    assert sleeps == [60, 60]


def test_non_retryable_error_is_raised_immediately() -> None:
    calls: list[int] = []

    def boom() -> None:
        calls.append(1)
        raise ValueError("permanente")

    with pytest.raises(ValueError):
        retry_call(boom, attempts=3, retry_on=(ConnectionError,), sleep=lambda _s: None)
    assert len(calls) == 1


def test_async_retry_has_same_semantics() -> None:
    sleeps: list[float] = []
    calls: list[int] = []

    async def failing() -> None:
        calls.append(1)
        raise ConnectionError("rete")

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    with pytest.raises(ConnectionError):
        asyncio.run(
            async_retry_call(
                failing, attempts=3, delay_s=60, sleep=fake_sleep
            )
        )
    assert len(calls) == 3
    assert sleeps == [60, 60]
