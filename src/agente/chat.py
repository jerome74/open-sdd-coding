"""C-23 Chat Handler — domande libere, contesto e rilettura (spec 05).

Riceve i messaggi in linguaggio naturale che C-14 non riconosce come comando,
costruisce il contesto con C-24, interroga C-05 entro la finestra di memoria,
espone gli strumenti di C-08 e li esegue tramite il gate C-27 (read-only senza
conferma, modificanti solo dopo approvazione dell'admin), mostra l'indicatore
C-25 durante l'attesa e invia la risposta con C-03.

Regole applicate in codice, non delegate al modello:

- solo admin e utenti ``accepted`` usano la chat (BR-12); lo stato è ri-verificato
  da C-04 a ogni richiesta;
- un turno entra in memoria solo dopo una risposta riuscita (P-A-15);
- le azioni modificanti passano dal gate C-27/C-28 di spec 06 (BR-2): sono
  eseguite solo dopo approvazione dell'admin, altrimenti producono un esito di
  tool negativo;
- le richieste dello stesso utente sono serializzate (P-A-16), così due messaggi
  ravvicinati non intrecciano il contesto.

La risposta è inviata **solo** da qui: C-14 riceve l'esito e non invia nulla.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

from .chat_memory import ConversationMemory
from .errors import AgenteError, LLMError, TelegramError
from .gate import ActionGate, ToolAction
from .llm import LLMClient, assistant_message
from .progress import ProgressIndicator
from .role_guard import Role, RoleGuard
from .storage.repositories import Message, User, UserRepository
from .tools import Tool, ToolRegistry

logger = logging.getLogger("agente.chat")

# P-A-17: limite proprio della chat, più stretto dei 5 cicli di C-09.
MAX_CHAT_TOOL_ROUNDS = 3
MAX_TOOL_OUTPUT_CHARS = 20_000

ERROR_TEXT = "Non riesco a rispondere in questo momento: riprova tra poco."
RESET_TEXT = "Conversazione azzerata."
NOTHING_TO_RESET = "Nessuna conversazione da azzerare."
ADMIN_READ_REFUSAL = "Solo l'amministratore può rileggere le chat."
UNKNOWN_TARGET = "Utente non autorizzato o sconosciuto."
EMPTY_TRANSCRIPT = "Nessun messaggio nelle ultime 24 ore."
TOO_MANY_ROUNDS = "troppi cicli di tool calling"

_CHAT_SYSTEM_PROMPT = (
    "Sei l'assistente personale del proprietario, su Telegram. Rispondi in italiano, "
    "oppure nella lingua dell'utente se è diversa. Sii conciso e concreto. Usa gli "
    "strumenti di sola lettura quando servono dati reali; non inventare fatti: se non "
    "sai qualcosa, dillo. Puoi proporre azioni che modificano il telefono: saranno "
    "eseguite solo dopo l'approvazione dell'amministratore, altrimenti riceverai un rifiuto."
)


@dataclass(frozen=True)
class ChatReply:
    """Esito della chat: ``answered``, ``reset``, ``transcript``, ``rejected``, ``error``."""

    kind: str
    text: str = ""


@dataclass(frozen=True)
class ChatToolContext:
    """Contesto passato agli handler di C-08: in chat non esiste un compito.

    ``log_allowlist`` è vuota (P-A-08): ``read_logs`` resta sempre rifiutato da
    C-07 finché spec 07 non definirà un'autorizzazione per la chat.
    """

    user_id: int
    log_allowlist: tuple[str, ...] = ()


class ChatHandler:
    def __init__(
        self,
        *,
        roles: RoleGuard,
        memory: ConversationMemory,
        llm: LLMClient,
        progress: ProgressIndicator,
        gateway: Any,
        users: UserRepository,
        tools: ToolRegistry | None = None,
        admin_id: int,
        gate: ActionGate | None = None,
    ) -> None:
        self._roles = roles
        self._memory = memory
        self._llm = llm
        self._progress = progress
        self._gateway = gateway
        self._users = users
        self._tools = tools
        self._admin_id = admin_id
        self._gate = gate
        self._locks: dict[int, asyncio.Lock] = {}
        # Generazione della conversazione: un /reset durante una risposta
        # impedisce ai turni in volo di rientrare in memoria (AC-03).
        self._epochs: dict[int, int] = {}

    # --- ingresso ---------------------------------------------------------

    async def handle(self, user_id: int, chat_id: int, text: str) -> ChatReply:
        """Risponde a una domanda libera dell'utente."""
        if self._roles.resolve_role(user_id) is Role.UNKNOWN:
            logger.info("chat ignorata: utente non riconosciuto")
            return ChatReply("ignored")
        question = (text or "").strip()
        if not question:
            return ChatReply("ignored")
        lock = self._locks.setdefault(user_id, asyncio.Lock())
        async with lock:
            return await self._answer(user_id, chat_id, question)

    async def reset(self, user_id: int, chat_id: int) -> ChatReply:
        """Azzera la conversazione dell'utente (AC-03)."""
        if self._roles.resolve_role(user_id) is Role.UNKNOWN:
            return ChatReply("ignored")
        self._epochs[user_id] = self._epochs.get(user_id, 0) + 1
        removed = self._memory.reset(user_id)
        text = RESET_TEXT if removed else NOTHING_TO_RESET
        await self._send(chat_id, text)
        return ChatReply("reset", text)

    async def transcript(
        self, requester_id: int, chat_id: int, target_id: int
    ) -> ChatReply:
        """Rilettura admin degli ultimi messaggi di un utente autorizzato (AC-04)."""
        if self._roles.resolve_role(requester_id) is not Role.ADMIN:
            await self._send(chat_id, ADMIN_READ_REFUSAL)
            return ChatReply("rejected", ADMIN_READ_REFUSAL)

        user: User | None = None
        if target_id != self._admin_id:
            user = self._users.get(target_id)
            if user is None or user.state != "accepted":
                await self._send(chat_id, UNKNOWN_TARGET)
                return ChatReply("error", UNKNOWN_TARGET)

        messages = self._memory.messages(target_id)
        if not messages:
            await self._send(chat_id, EMPTY_TRANSCRIPT)
            return ChatReply("transcript", EMPTY_TRANSCRIPT)

        text = _transcript_text(target_id, user, messages)
        await self._send(chat_id, text)
        logger.info(
            "chat riletta dall'admin",
            extra={"user_id": target_id, "messages": len(messages)},
        )
        return ChatReply("transcript", text)

    async def list_authorized(self, requester_id: int, chat_id: int) -> ChatReply:
        """Elenco degli utenti autorizzati per ``/chat`` senza argomento."""
        if self._roles.resolve_role(requester_id) is not Role.ADMIN:
            await self._send(chat_id, ADMIN_READ_REFUSAL)
            return ChatReply("rejected", ADMIN_READ_REFUSAL)
        users = self._users.list("accepted")
        if not users:
            text = "Nessun utente autorizzato."
        else:
            lines = ["Utenti autorizzati:"]
            for user in users:
                line = f"• {user.telegram_id}"
                if user.username:
                    line += f" ({user.username})"
                lines.append(line)
            text = "\n".join(lines)
        await self._send(chat_id, text)
        return ChatReply("transcript", text)

    # --- risposta ---------------------------------------------------------

    async def _answer(self, user_id: int, chat_id: int, question: str) -> ChatReply:
        epoch = self._epochs.get(user_id, 0)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _CHAT_SYSTEM_PROMPT}
        ]
        messages.extend(
            {"role": message.role, "content": message.content}
            for message in self._memory.get_context(user_id)
        )
        messages.append({"role": "user", "content": question})

        started = time.monotonic()
        answer = ""
        failure: LLMError | None = None
        await self._progress.start(chat_id)
        try:
            answer = await self._complete(user_id, messages, question)
        except LLMError as exc:
            failure = exc
        finally:
            await self._progress.finish(chat_id)

        if failure is not None:
            logger.error(
                "chat fallita",
                extra={"user_id": user_id, "error": type(failure).__name__},
            )
            await self._send(chat_id, ERROR_TEXT)
            return ChatReply("error", ERROR_TEXT)

        # P-A-15: i due turni entrano in memoria solo dopo una risposta riuscita
        # e solo se un /reset non ha azzerato la conversazione nel frattempo.
        if self._epochs.get(user_id, 0) == epoch:
            self._memory.append(
                user_id, Message(user_id=user_id, role="user", content=question)
            )
            self._memory.append(
                user_id, Message(user_id=user_id, role="assistant", content=answer)
            )
        else:
            logger.info(
                "turno non registrato: conversazione azzerata durante la risposta",
                extra={"user_id": user_id},
            )
        await self._send(chat_id, answer)
        logger.info(
            "risposta chat inviata",
            extra={
                "user_id": user_id,
                "duration_ms": round((time.monotonic() - started) * 1000),
                "chars": len(answer),
            },
        )
        return ChatReply("answered", answer)

    async def _complete(
        self, user_id: int, messages: list[dict[str, Any]], reason: str
    ) -> str:
        schemas = self._tool_schemas()
        for _ in range(MAX_CHAT_TOOL_ROUNDS):
            # C-05 è sincrona (retry BR-8 inclusi): non deve fermare l'event loop,
            # altrimenti l'indicatore C-25 non scatterebbe (P-A-16).
            response = await asyncio.to_thread(self._llm.chat, messages, schemas or None)
            if not response.tool_calls:
                text = (response.text or "").strip()
                if not text:
                    raise LLMError("risposta vuota dal modello")
                return text
            messages.append(assistant_message(response))
            for call in response.tool_calls:
                output = await self._invoke_tool(
                    user_id, call.name, call.arguments, reason
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id or call.name,
                        "content": output,
                    }
                )
        raise LLMError(TOO_MANY_ROUNDS)

    def _tool_schemas(self) -> list[dict[str, Any]]:
        if self._tools is None:
            return []
        tools = self._tools.tools()
        if self._gate is None:
            # P-A-15: senza gate resta il fail-safe di item 05.
            tools = [tool for tool in tools if tool.read_only]
        return [tool.schema() for tool in tools]

    async def _invoke_tool(
        self,
        user_id: int,
        name: str,
        arguments: dict[str, Any],
        reason: str = "",
    ) -> str:
        if self._gate is not None:
            action = ToolAction(
                tool=name,
                arguments=dict(arguments or {}),
                context=ChatToolContext(user_id=user_id),
                reason=reason,
                requested_by=user_id,
            )
            try:
                # Nessun to_thread attorno all'attesa: solo l'handler viene
                # offloaded, dentro C-27.
                return await self._gate.run(action)
            except AgenteError as exc:
                logger.warning(
                    "tool in chat fallito",
                    extra={"tool": name, "error": type(exc).__name__},
                )
                return f"errore dello strumento: {exc}"

        tool: Tool | None = self._tools.get(name) if self._tools is not None else None
        if tool is None:
            logger.info("tool sconosciuto in chat", extra={"tool": name})
            return f"strumento non disponibile: {name}"
        if not tool.read_only:
            logger.info("tool modificante rifiutato in chat", extra={"tool": name})
            return (
                "azione non eseguibile in chat: richiede l'approvazione "
                "dell'amministratore"
            )
        if tool.handler is None:
            return f"strumento senza handler: {name}"
        try:
            output = tool.handler(
                ChatToolContext(user_id=user_id), dict(arguments or {})
            )
        except AgenteError as exc:
            logger.warning(
                "tool in chat fallito", extra={"tool": name, "error": type(exc).__name__}
            )
            return f"errore dello strumento: {exc}"
        text = output if isinstance(output, str) else str(output)
        if len(text) > MAX_TOOL_OUTPUT_CHARS:
            text = text[:MAX_TOOL_OUTPUT_CHARS] + "\n[output troncato]"
        return text

    async def _send(self, chat_id: int, text: str) -> None:
        try:
            await self._gateway.send(chat_id, text)
        except TelegramError as exc:
            # L'utente non riceve la risposta: il guasto è già loggato dal gateway.
            logger.error(
                "risposta chat non inviata",
                extra={"chat_id": chat_id, "error": type(exc).__name__},
            )


def _transcript_text(user_id: int, user: User | None, messages: list[Message]) -> str:
    label = f"Conversazione di {user_id}"
    if user is not None and user.username:
        label += f" ({user.username})"
    lines = [f"{label} — ultimi {len(messages)} messaggi:"]
    for message in messages:
        who = {"user": "utente", "assistant": "agente"}.get(
            message.role, message.role
        )
        lines.append(f"[{message.created_at}] {who}: {message.content}")
    return "\n".join(lines)
