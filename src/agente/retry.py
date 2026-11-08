"""Retry deterministico BR-8: 3 tentativi a 1 minuto.

``attempts`` è il numero totale di tentativi (3), con ``delay_s`` secondi tra un
tentativo e il successivo. Il sonno è iniettabile per i test.
"""

from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")


def retry_call(
    func: Callable[[], T],
    *,
    attempts: int = 3,
    delay_s: float = 60.0,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Esegue ``func`` fino a ``attempts`` volte, poi rilancia l'ultimo errore."""
    if attempts < 1:
        raise ValueError("attempts deve essere >= 1")
    last_error: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return func()
        except retry_on as exc:  # noqa: PERF203 - retry esplicito e voluto
            last_error = exc
            if attempt == attempts:
                raise
            sleep(delay_s)
    raise AssertionError("irraggiungibile") from last_error


async def async_retry_call(
    func: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    delay_s: float = 60.0,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    """Versione asincrona di :func:`retry_call` con la stessa semantica."""
    if attempts < 1:
        raise ValueError("attempts deve essere >= 1")
    last_error: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await func()
        except retry_on as exc:  # noqa: PERF203 - retry esplicito e voluto
            last_error = exc
            if attempt == attempts:
                raise
            await sleep(delay_s)
    raise AssertionError("irraggiungibile") from last_error
