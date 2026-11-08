"""C-38 Credential Monitor — errori di autenticazione/credito DeepSeek (spec 10).

C-05 è sincrona e può girare su un worker: qui l'errore viene solo
classificato e inoltrato a C-36 tramite il ponte thread-safe. Il corpo della
risposta non viene usato né loggato; l'avviso riporta il solo status.
"""

from __future__ import annotations

import logging

from .alerts import AlertService

logger = logging.getLogger("agente.credential_monitor")

_CREDENTIAL_STATUSES = frozenset({401, 402, 403})


class CredentialMonitor:
    def __init__(self, alerts: AlertService) -> None:
        self._alerts = alerts

    def on_llm_error(self, http_status: int, body: str = "") -> bool:
        """Classifica l'errore e inoltra l'avviso; ``body`` non è usato.

        Restituisce ``True`` se lo status è di credenziale e l'avviso è stato
        inoltrato (anche se la deduplicazione o l'assenza di loop lo
        sopprimono), ``False`` per gli altri status.
        """
        try:
            status = int(http_status)
        except (TypeError, ValueError):
            logger.warning("status HTTP non valido", extra={"status": http_status})
            return False
        if status not in _CREDENTIAL_STATUSES:
            logger.info("errore LLM non di credenziale", extra={"status": status})
            return False
        logger.warning("credenziale DeepSeek non valida", extra={"status": status})
        self._alerts.alert_threadsafe("credential", {"status": status})
        return True


__all__ = ["CredentialMonitor"]
