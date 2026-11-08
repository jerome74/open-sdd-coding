"""C-12 Supervisor — watchdog di processo.

Il processo aggiorna un heartbeat; se resta fermo oltre la soglia, il watchdog
invoca il callback di riavvio (il loop esterno del boot script rilancia il
processo). Decisione D1 del piano 01.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from typing import Callable

logger = logging.getLogger("agente.supervisor")


def _default_on_stall() -> None:
    logger.critical("watchdog: processo in stallo, termino per riavvio")
    os._exit(1)


class Supervisor:
    def __init__(
        self,
        timeout_s: float,
        *,
        on_stall: Callable[[], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._timeout_s = timeout_s
        self._on_stall = on_stall or _default_on_stall
        self._clock = clock
        self._last_heartbeat = clock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def heartbeat(self) -> None:
        self._last_heartbeat = self._clock()

    def stalled(self) -> bool:
        return (self._clock() - self._last_heartbeat) > self._timeout_s

    def check(self) -> bool:
        if self.stalled():
            logger.warning("watchdog: stallo rilevato")
            self._on_stall()
            return True
        return False

    def start_thread(self, interval_s: float = 5.0) -> None:
        """Avvia il watchdog in un thread separato: rileva lo stallo dell'event loop."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._watch, args=(interval_s,), name="agente-watchdog", daemon=True
        )
        self._thread.start()
        logger.info("watchdog avviato", extra={"timeout_s": self._timeout_s})

    def stop_thread(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.info("watchdog fermato")

    def _watch(self, interval_s: float) -> None:
        while not self._stop_event.wait(interval_s):
            self.check()

    async def run(self, interval_s: float = 5.0) -> None:
        while True:
            self.check()
            await asyncio.sleep(interval_s)
