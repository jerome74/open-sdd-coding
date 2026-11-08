"""C-04 Role Guard — identità e autorizzazione per ruolo (BR-12/BR-18).

L'amministratore esiste solo nella configurazione: nessun percorso lo promuove
da chat. Un utente ``pending`` o ``revoked`` vale ``UNKNOWN``.
"""

from __future__ import annotations

import functools
import logging
from enum import Enum
from typing import Any, Callable, TypeVar

from .config import Config
from .storage.repositories import UserRepository

logger = logging.getLogger("agente.role_guard")

F = TypeVar("F", bound=Callable[..., Any])


class Role(str, Enum):
    ADMIN = "admin"
    AUTHORIZED = "authorized"
    UNKNOWN = "unknown"


class RoleGuard:
    def __init__(self, config: Config, users: UserRepository) -> None:
        self._admin_id = config.admin_telegram_id
        self._users = users

    def resolve_role(self, telegram_id: int) -> Role:
        if telegram_id == self._admin_id:
            logger.info("ruolo risolto", extra={"telegram_id": telegram_id, "role": "admin"})
            return Role.ADMIN
        user = self._users.get(telegram_id)
        if user is not None and user.state == "accepted":
            logger.info(
                "ruolo risolto", extra={"telegram_id": telegram_id, "role": "authorized"}
            )
            return Role.AUTHORIZED
        logger.info(
            "ruolo risolto", extra={"telegram_id": telegram_id, "role": "unknown"}
        )
        return Role.UNKNOWN


def admin_only(guard: RoleGuard) -> Callable[[F], F]:
    """Consente l'esecuzione solo all'amministratore (primo argomento id)."""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(telegram_id: int, *args: Any, **kwargs: Any) -> Any:
            if guard.resolve_role(telegram_id) is not Role.ADMIN:
                return None
            return func(telegram_id, *args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def authorized_or_admin(guard: RoleGuard) -> Callable[[F], F]:
    """Consente admin e utenti ``accepted``; ignora ``pending``/``revoked``."""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(telegram_id: int, *args: Any, **kwargs: Any) -> Any:
            if guard.resolve_role(telegram_id) is Role.UNKNOWN:
                return None
            return func(telegram_id, *args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator
