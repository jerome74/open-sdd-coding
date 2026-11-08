"""Errori applicativi espliciti (spec 01, principi 5 e 8).

Nessun errore silenzioso: ogni fallimento previsto ha un tipo dedicato, così i
consumer possono distinguere configurazione, storage, integrazioni e gate.
"""

from __future__ import annotations


class AgenteError(Exception):
    """Base di tutti gli errori applicativi."""


class ConfigError(AgenteError):
    """Configurazione mancante, illeggibile o con permessi non ammessi."""


class StorageError(AgenteError):
    """Errore di accesso o transazione SQLite."""


class LLMError(AgenteError):
    """Errore generico della chiamata al modello."""


class LLMCredentialsError(LLMError):
    """Chiave API assente, invalida o senza credito (avviso: spec 10)."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class TelegramError(AgenteError):
    """Errore di invio o ricezione via Telegram."""


class DeviceError(AgenteError):
    """Termux:API assente o comando di lettura fallito."""


class GateError(AgenteError):
    """Azione modificante senza approvazione esplicita dell'amministratore."""


class LockHeldError(AgenteError):
    """Esecuzione già in corso per lo stesso compito (una sola alla volta)."""


class ToolPolicyError(AgenteError):
    """Strumento registrato con policy non valida."""


class ToolExecutionError(AgenteError):
    """Strumento non eseguibile senza il gate di approvazione (spec 06)."""


class SearchError(AgenteError):
    """Ricerca web non configurata o provider in errore (spec 06, C-26)."""


class UserAccessError(AgenteError):
    """Operazione sugli utenti rifiutata (spec 08, BR-12/BR-16/BR-18).

    ``reason`` è il codice stabile che C-14 traduce nel messaggio da mostrare:
    ``forbidden`` (attore non admin), ``not_found`` (utente o compito
    inesistente), ``invalid_state`` (stato non ammesso), ``invalid_target``
    (amministratore o attore sbagliato), ``limit`` (tetto BR-16).
    """

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


class LogAccessError(AgenteError):
    """Percorso di log fuori dall'allowlist del compito (spec 07, BR-13).

    ``refused`` elenca i percorsi non autorizzati, ``rendered`` è il contenuto
    parziale già preparato da C-29: C-09 lo restituisce al modello e avvisa
    l'admin con i soli percorsi.
    """

    def __init__(
        self,
        message: str,
        *,
        refused: tuple[str, ...] = (),
        rendered: str = "",
    ) -> None:
        super().__init__(message)
        self.refused = refused
        self.rendered = rendered or message


class DeliveryError(AgenteError):
    """Consegna fallita ad almeno un destinatario dopo i retry (BR-8)."""

    def __init__(self, message: str, *, failed: tuple[int, ...] = ()) -> None:
        super().__init__(message)
        self.failed = failed


class RunRefused(AgenteError):
    """Lancio manuale rifiutato prima dell'esecuzione (spec 04, C-21).

    ``reason`` è il codice stabile del rifiuto (``missing_name``, ``not_found``,
    ``forbidden``, ``paused``, ``busy``); il testo dell'eccezione è il messaggio
    da mostrare al richiedente.
    """

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason = reason
