"""C-22 Task Lock — una sola esecuzione per compito alla volta (spec 04).

Il lock è in memoria (decisione D1 del piano 04): il Tech Stack dichiara un solo
processo e un riavvio termina l'esecuzione in corso, quindi non esiste stato da
serializzare in SQLite. L'acquisizione è non bloccante: chi trova il compito già
occupato riceve ``False`` e il chiamante traduce il fatto in un rifiuto (AC-03).

Il lock è unico per tutti gli inneschi (``scheduled``, ``manual``, ``recovery``):
C-09 lo acquisisce prima di registrare l'esecuzione e lo rilascia sempre, anche
in caso di errore o timeout.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("agente.task_lock")


class TaskLock:
    def __init__(self) -> None:
        self._held: set[int] = set()

    def acquire(self, task_id: int) -> bool:
        """Acquisisce il lock; ``False`` se il compito è già in esecuzione."""
        if task_id in self._held:
            logger.info("lock già detenuto", extra={"task_id": task_id})
            return False
        # Nessun await tra controllo e inserimento: l'operazione è atomica
        # nell'event loop singolo.
        self._held.add(task_id)
        logger.info("lock acquisito", extra={"task_id": task_id})
        return True

    def release(self, task_id: int) -> None:
        """Rilascia il lock; idempotente anche su compiti mai acquisiti."""
        if task_id not in self._held:
            return
        self._held.discard(task_id)
        logger.info("lock rilasciato", extra={"task_id": task_id})

    def held(self, task_id: int) -> bool:
        """``True`` se un'esecuzione del compito è in corso."""
        return task_id in self._held
