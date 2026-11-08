"""C-31 User Manager — utenti, stati e iscrizioni (spec 08).

Regole applicate in codice, mai delegate al modello:

- solo l'amministratore autorizza, revoca e iscrive (BR-12); il controllo è
  qui **e** in C-14 (difesa in profondità, V-07);
- l'amministratore non è un record ``users``: non è un target valido e non
  conta nel tetto BR-16;
- un'iscrizione richiede un utente ``accepted``, come i destinatari di C-15;
- una revoca conserva record e iscrizioni (D3): la riattivazione è esplicita.

Le transizioni di stato sono quelle del piano 08: nessun altro passaggio è
ammesso, e ``consent_at`` viene azzerato solo quando un revocato torna
``pending`` (deve accettare di nuovo).
"""

from __future__ import annotations

import logging

from .consent import ConsentFlow
from .errors import UserAccessError
from .role_guard import Role, RoleGuard
from .storage.repositories import (
    SubscriptionRepository,
    TaskRepository,
    User,
    UserRepository,
)
from .user_state import MAX_AUTHORIZED_USERS, UserResult, UserView

logger = logging.getLogger("agente.users")


class UserManager:
    def __init__(
        self,
        users: UserRepository,
        subscriptions: SubscriptionRepository,
        tasks: TaskRepository,
        consent: ConsentFlow,
        roles: RoleGuard,
    ) -> None:
        self._users = users
        self._subscriptions = subscriptions
        self._tasks = tasks
        self._consent = consent
        self._roles = roles

    async def authorize(
        self,
        actor_id: int,
        telegram_id: int,
        *,
        username: str | None = None,
    ) -> UserResult:
        """Crea o riapre un utente ``pending`` e invia l'informativa."""
        self._require_admin(actor_id, telegram_id)
        user = self._users.get(telegram_id)

        if user is not None and user.state == "accepted":
            logger.info("autorizzazione già presente", extra={"user_id": telegram_id})
            return UserResult(
                user=user,
                changed=False,
                note=f"Utente {telegram_id} già autorizzato.",
            )

        if user is None or user.state == "revoked":
            if self._accepted_count() >= MAX_AUTHORIZED_USERS:
                raise UserAccessError(
                    f"limite di {MAX_AUTHORIZED_USERS} utenti autorizzati raggiunto",
                    reason="limit",
                )

        if user is None:
            stored = self._users.upsert(
                User(
                    telegram_id=telegram_id,
                    username=username,
                    state="pending",
                    consent_at=None,
                )
            )
            note = f"Utente {telegram_id} in attesa"
        elif user.state == "revoked":
            stored = self._users.upsert(
                User(
                    telegram_id=telegram_id,
                    username=username or user.username,
                    state="pending",
                    consent_at=None,
                )
            )
            note = f"Utente {telegram_id} riautorizzato"
        else:
            # pending: reinvio senza cambiare lo stato (P-A-08/P-A-23).
            stored = self._users.upsert(
                User(
                    telegram_id=telegram_id,
                    username=username or user.username,
                    state="pending",
                    consent_at=user.consent_at,
                )
            )
            note = f"Utente {telegram_id} in attesa"

        sent = await self._consent.send_consent(telegram_id)
        if sent:
            note += ": informativa inviata."
        else:
            note += ", informativa non inviata."
        logger.info(
            "utente autorizzato",
            extra={"user_id": telegram_id, "state": stored.state, "notice": sent},
        )
        return UserResult(
            user=stored,
            changed=user is None or user.state == "revoked",
            note=note,
            notice_sent=sent,
        )

    def revoke(self, actor_id: int, telegram_id: int) -> UserResult:
        """Porta l'utente a ``revoked`` senza toccare dati e iscrizioni."""
        self._require_admin(actor_id, telegram_id)
        user = self._require_user(telegram_id)
        if user.state == "revoked":
            return UserResult(
                user=user,
                changed=False,
                note=f"Utente {telegram_id} era già revocato.",
            )
        self._users.set_state(telegram_id, "revoked")
        updated = self._require_user(telegram_id)
        logger.info("utente revocato", extra={"user_id": telegram_id})
        return UserResult(
            user=updated,
            changed=True,
            note=f"Utente {telegram_id} revocato.",
        )

    def subscribe(self, actor_id: int, user_id: int, task_id: int) -> UserResult:
        """Iscrive un utente autorizzato a un compito."""
        self._require_admin(actor_id, user_id)
        user = self._require_user(user_id)
        task = self._require_task(task_id)
        if user.state != "accepted":
            raise UserAccessError(
                f"utente {user_id} non autorizzato: stato {user.state}",
                reason="invalid_state",
            )
        if task_id in self._subscriptions.tasks_for_user(user_id):
            return UserResult(
                user=user,
                changed=False,
                note=f"Utente {user_id} è già iscritto al compito «{task.name}».",
            )
        self._subscriptions.add(user_id, task_id)
        logger.info(
            "utente iscritto",
            extra={"user_id": user_id, "task_id": task_id},
        )
        return UserResult(
            user=user,
            changed=True,
            note=f"Utente {user_id} iscritto al compito «{task.name}».",
        )

    def unsubscribe(self, actor_id: int, user_id: int, task_id: int) -> UserResult:
        """Rimuove un'iscrizione; ammesso anche per un utente revocato."""
        self._require_admin(actor_id, user_id)
        user = self._require_user(user_id)
        task = self._require_task(task_id)
        if task_id not in self._subscriptions.tasks_for_user(user_id):
            return UserResult(
                user=user,
                changed=False,
                note=f"Utente {user_id} non è iscritto al compito «{task.name}».",
            )
        self._subscriptions.remove(user_id, task_id)
        logger.info(
            "utente disiscritto",
            extra={"user_id": user_id, "task_id": task_id},
        )
        return UserResult(
            user=user,
            changed=True,
            note=f"Utente {user_id} disiscritto dal compito «{task.name}».",
        )

    def list_users(self, actor_id: int) -> tuple[UserView, ...]:
        """Tutti gli utenti con stato e compiti (solo admin)."""
        self._require_admin(actor_id)
        views: list[UserView] = []
        for user in self._users.list():
            names = tuple(
                task.name
                for task_id in self._subscriptions.tasks_for_user(user.telegram_id)
                if (task := self._tasks.get(task_id)) is not None
            )
            views.append(UserView(user=user, task_names=names))
        return tuple(views)

    # --- interni ----------------------------------------------------------

    def _require_admin(self, actor_id: int, target: int | None = None) -> None:
        if self._roles.resolve_role(actor_id) is not Role.ADMIN:
            logger.warning("operazione utenti rifiutata: attore non admin")
            raise UserAccessError(
                "solo l'amministratore gestisce gli utenti", reason="forbidden"
            )
        if target is not None and self._roles.resolve_role(target) is Role.ADMIN:
            raise UserAccessError(
                "l'amministratore non è un utente gestibile", reason="invalid_target"
            )

    def _require_user(self, telegram_id: int) -> User:
        user = self._users.get(telegram_id)
        if user is None:
            raise UserAccessError(
                f"utente non trovato: {telegram_id}", reason="not_found"
            )
        return user

    def _require_task(self, task_id: int):
        task = self._tasks.get(task_id)
        if task is None:
            raise UserAccessError(f"compito non trovato: {task_id}", reason="not_found")
        return task

    def _accepted_count(self) -> int:
        return len(self._users.list("accepted"))
