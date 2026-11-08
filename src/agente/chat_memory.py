"""C-24 Conversation Memory — contesto, reset e purge della chat (spec 05).

La memoria è per utente e vive nelle tabelle ``conversations``/``messages``
(spec 01). La finestra è ``limits.chat_memory_hours`` (BR-6) e si applica su due
criteri coerenti:

- **silenzio:** la conversazione è attiva solo se l'ultimo messaggio dell'utente
  è dentro la finestra (assunzione di spec 05);
- **età del messaggio:** i singoli turni più vecchi della finestra non entrano
  nel contesto, come già fa la retention di C-11.

``reset`` è la semantica di AC-03: cancella **tutto** ciò che appartiene
all'utente, non solo i messaggi scaduti. ``purge_idle`` azzera le conversazioni
silenti ed è richiamata dal job di manutenzione (flusso 3).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from .storage.repositories import ConversationRepository, Message

logger = logging.getLogger("agente.chat_memory")

# Stima grezza identica a C-05: ~4 caratteri per token.
_CHARS_PER_TOKEN = 4
ROLES = ("user", "assistant", "tool")


@dataclass(frozen=True)
class PurgeStats:
    messages_deleted: int
    conversations_deleted: int


class ConversationMemory:
    def __init__(
        self,
        conversations: ConversationRepository,
        *,
        memory_hours: int,
        context_tokens: int,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._conversations = conversations
        self._memory_hours = memory_hours
        self._context_tokens = context_tokens
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    # --- contesto ---------------------------------------------------------

    def get_context(self, user_id: int) -> list[Message]:
        """Ultimi turni entro la finestra, troncati al budget di contesto."""
        now = self._clock()
        if not self._active(user_id, now):
            return []
        cutoff = self._cutoff(now)
        messages = self._conversations.messages_for_user(user_id, since=cutoff)
        return _truncate(messages, self._context_tokens)

    def messages(self, user_id: int, limit: int = 50) -> list[Message]:
        """Messaggi leggibili dall'admin: solo quelli ancora in memoria."""
        now = self._clock()
        if not self._active(user_id, now):
            return []
        return self._conversations.messages_for_user(
            user_id, since=self._cutoff(now), limit=limit
        )

    # --- scrittura --------------------------------------------------------

    def append(self, user_id: int, message: Message) -> Message:
        """Registra un turno; il silenzio si misura sul turno dell'utente."""
        if message.role not in ROLES:
            raise ValueError(f"ruolo non ammesso: {message.role}")
        if not message.content.strip():
            raise ValueError("messaggio vuoto: nessuna registrazione")
        message.user_id = user_id
        if not message.created_at:
            message.created_at = self._now()
        self._conversations.add_message(message)
        if message.role == "user":
            self._conversations.touch(user_id, message.created_at)
        logger.info(
            "turno registrato",
            extra={"user_id": user_id, "role": message.role, "chars": len(message.content)},
        )
        return message

    def reset(self, user_id: int) -> int:
        """Cancella l'intera conversazione (AC-03); restituisce le righe rimosse."""
        messages, conversations = self._conversations.delete_all_for_user(user_id)
        logger.info(
            "conversazione azzerata",
            extra={
                "user_id": user_id,
                "messages_deleted": messages,
                "conversations_deleted": conversations,
            },
        )
        return messages + conversations

    def purge_idle(self) -> PurgeStats:
        """Azzera le conversazioni silenti da più della finestra (flusso 3)."""
        cutoff = self._cutoff(self._clock())
        messages, conversations = self._conversations.delete_idle(cutoff)
        if messages or conversations:
            logger.info(
                "conversazioni inattive rimosse",
                extra={
                    "messages_deleted": messages,
                    "conversations_deleted": conversations,
                },
            )
        return PurgeStats(messages_deleted=messages, conversations_deleted=conversations)

    # --- supporto ---------------------------------------------------------

    def _active(self, user_id: int, now: datetime) -> bool:
        updated = self._conversations.updated_at(user_id)
        if updated is None:
            return False
        moment = _parse(updated)
        if moment is None:
            # Timestamp illeggibile: comportamento conservativo, nessun contesto.
            logger.warning("updated_at illeggibile", extra={"user_id": user_id})
            return False
        return now - moment < timedelta(hours=self._memory_hours)

    def _cutoff(self, now: datetime) -> str:
        return (now - timedelta(hours=self._memory_hours)).isoformat(
            timespec="seconds"
        )

    def _now(self) -> str:
        return self._clock().isoformat(timespec="seconds")


def _parse(value: str) -> datetime | None:
    try:
        moment = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _truncate(messages: list[Message], budget: int) -> list[Message]:
    """Tiene i turni più recenti entro il budget (almeno l'ultimo)."""
    kept: list[Message] = []
    total = 0
    for message in reversed(messages):
        cost = _estimate_tokens(message.content)
        if kept and total + cost > budget:
            break
        kept.append(message)
        total += cost
    kept.reverse()
    return kept


def _estimate_tokens(content: str) -> int:
    return max(1, len(content) // _CHARS_PER_TOKEN)
