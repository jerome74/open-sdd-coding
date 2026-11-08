"""C-14 Command Router — comandi rapidi e messaggi in linguaggio naturale.

Instrada gli aggiornamenti normalizzati da C-03 verso le operazioni sui compiti
(spec 02), il lancio manuale (spec 04) e la chat (spec 05). Regole applicate in
codice, mai delegate al LLM: il ruolo viene da C-04 e solo l'amministratore crea,
modifica o elimina compiti (BR-12); ogni modifica passa da C-17 (BR-1). Il LLM
(C-05) produce solo una bozza, sempre riepilogata e confermata prima dell'effetto.

Spec 05 (D1): una richiesta di creazione richiede una bozza completa (nome,
istruzioni, schedulazione); altrimenti il testo libero è una domanda e va a C-23.
Per l'utente autorizzato una bozza completa resta un tentativo di creazione e
riceve il rifiuto di spec 02 AC-03. La risposta della chat è inviata da C-23.

Spec 08: i callback sono instradati **prima** del rifiuto agli utenti
sconosciuti, perché un ``pending`` deve poter accettare l'informativa e l'admin
deve poter premere «Autorizza». Uno sconosciuto che scrive riceve un rifiuto e
genera l'avviso di C-33 (una volta ogni 24 ore); uno sconosciuto che preme un
bottone non genera avvisi. I comandi di gestione utenti sono solo admin.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Sequence

from .approvals import ApprovalManager
from .authorization_notifier import AUTHORIZE_PREFIX, AuthorizationNotifier
from .chat import ChatHandler
from .confirmation import CONFIRM_PREFIX, ConfirmationFlow
from .consent import CONSENT_PREFIX, ConsentFlow
from .errors import AgenteError, RunRefused, TelegramError, UserAccessError
from .history_query import AmbiguousPeriod, HistoryQuery, ParsedFilter
from .execution import ExecutionResult
from .role_guard import Role, RoleGuard
from .run_dispatcher import RunDispatcher
from .schedule_interpreter import (
    Ambiguous,
    Schedule,
    ScheduleInterpreter,
    describe,
)
from .task_manager import TaskDraft, TaskManager, TaskValidationError, TaskView
from .telegram_gateway import IncomingMessage
from .user_manager import UserManager
from .user_state import MAX_AUTHORIZED_USERS

logger = logging.getLogger("agente.router")

HELP_TEXT = (
    "Comandi disponibili:\n"
    "/tasks — elenca i compiti\n"
    "/run <nome> — esegue subito un compito\n"
    "/reset — azzera la conversazione\n"
    "/pause <nome> — sospendi un compito\n"
    "/resume <nome> — riattiva un compito\n"
    "/delete <nome> — elimina un compito\n"
    "/rename <nome> <nuovo nome> — rinomina un compito\n"
    "/chat <telegram_id> — rilegge la chat di un utente (solo admin)\n"
    "/adduser <telegram_id> [username] — autorizza un utente (solo admin)\n"
    "/removeuser <telegram_id> — revoca un utente (solo admin)\n"
    "/users — elenca gli utenti e i loro compiti (solo admin)\n"
    "/subscribe <compito> <telegram_id> — iscrive un utente (solo admin)\n"
    "/unsubscribe <compito> <telegram_id> — disiscrive un utente (solo admin)\n"
    "/history [periodo] [compito] — storico delle esecuzioni\n\n"
    "Per creare un compito scrivi in linguaggio naturale cosa deve fare e quando "
    "(es. «ogni giorno alle 8 riassumi i log»). Per eseguirne uno subito scrivi "
    "«lancia <nome>» o /run <nome>."
)

ADMIN_REFUSAL = "Solo l'amministratore può creare o modificare i compiti."
USER_ADMIN_REFUSAL = "Solo l'amministratore può gestire gli utenti."
UNKNOWN_REFUSAL = "Non sei autorizzato a usare questo agente."

_DRAFT_SYSTEM_PROMPT = (
    "Estrai i campi di un compito ricorrente dal messaggio dell'amministratore. "
    "Rispondi SOLO con un oggetto JSON, senza testo aggiuntivo, con questa forma:\n"
    '{"name": "...", "instructions": "...", "schedule": "...", '
    '"recipients": [123], "log_allowlist": ["/percorso/file.log"]}\n'
    "Regole: `name` è un nome breve e univoco; `instructions` è ciò che il compito "
    "deve fare; `schedule` è il testo originale della schedulazione, senza "
    "interpretarlo; `recipients` elenca solo gli id Telegram citati (lista vuota se "
    "nessuno); `log_allowlist` elenca solo i percorsi citati (lista vuota se nessuno). "
    "Non inventare valori mancanti."
)


@dataclass(frozen=True)
class Action:
    """Esito del routing, per test e log (nessun effetto proprio)."""

    kind: str
    task_id: int | None = None


@dataclass(frozen=True)
class _Draft:
    name: str = ""
    instructions: str = ""
    schedule_text: str = ""
    recipients: tuple[int, ...] = field(default_factory=tuple)
    log_allowlist: tuple[str, ...] = field(default_factory=tuple)


class CommandRouter:
    def __init__(
        self,
        *,
        roles: RoleGuard,
        tasks: TaskManager,
        interpreter: ScheduleInterpreter,
        confirmations: ConfirmationFlow,
        gateway: Any,
        llm: Any,
        run_dispatcher: RunDispatcher,
        chat: ChatHandler,
        approvals: ApprovalManager,
        users: UserManager,
        consent: ConsentFlow,
        notifier: AuthorizationNotifier,
        history_query: HistoryQuery,
        admin_id: int,
    ) -> None:
        self._roles = roles
        self._tasks = tasks
        self._interpreter = interpreter
        self._confirmations = confirmations
        self._gateway = gateway
        self._llm = llm
        self._run = run_dispatcher
        self._chat = chat
        self._approvals = approvals
        self._users = users
        self._consent = consent
        self._notifier = notifier
        self._history_query = history_query
        self._admin_id = admin_id

    async def route(self, message: IncomingMessage) -> Action:
        role = self._roles.resolve_role(message.user_id)
        if message.callback_data:
            return await self._on_callback(message, role)

        if role is Role.UNKNOWN:
            await self._refuse_unknown(message)
            return Action("ignored")

        text = (message.text or "").strip()
        if not text:
            return Action("ignored")

        if text.lower() in _CONFIRM_WORDS and self._confirmations.resolve_text(
            message.user_id, text
        ):
            return Action("confirm_resolved")

        if text.startswith("/"):
            return await self._on_command(message, role, text)
        return await self._on_natural(message, role, text)

    # --- comandi -----------------------------------------------------------

    async def _on_command(
        self, message: IncomingMessage, role: Role, text: str
    ) -> Action:
        command, _, argument = text.partition(" ")
        name = command.lstrip("/").split("@", 1)[0].lower()
        argument = argument.strip()
        logger.info("comando riconosciuto", extra={"command": name})

        if name in ("help", "start"):
            await self._gateway.send(message.chat_id, HELP_TEXT)
            return Action("help")

        if name == "tasks":
            if role is Role.UNKNOWN:
                return Action("ignored")
            await self._send_list(message, role)
            return Action("listed")

        if name == "run":
            return await self._launch(message, role, argument)

        if name == "reset":
            reply = await self._chat.reset(message.user_id, message.chat_id)
            return Action(reply.kind)

        if name == "chat":
            return await self._chat_read(message, argument)

        if name == "history":
            return await self._history(message, role, argument)

        if name in ("adduser", "removeuser", "users", "subscribe", "unsubscribe"):
            return await self._user_command(message, role, name, argument)

        if name in ("pause", "resume", "delete", "rename"):
            if role is not Role.ADMIN:
                await self._gateway.send(message.chat_id, ADMIN_REFUSAL)
                logger.info("comando rifiutato per ruolo", extra={"command": name})
                return Action("rejected")
            if name == "rename":
                current, _, new_name = argument.partition(" ")
                return await self._mutate(
                    message, name, current.strip(), new_name.strip()
                )
            return await self._mutate(message, name, argument)

        await self._gateway.send(message.chat_id, HELP_TEXT)
        return Action("help")

    async def _mutate(
        self, message: IncomingMessage, command: str, current: str, new_name: str = ""
    ) -> Action:
        if not current:
            await self._gateway.send(
                message.chat_id, f"Indica il nome del compito: /{command} <nome>."
            )
            return Action("error")
        task = self._tasks.find(current)
        if task is None:
            await self._gateway.send(
                message.chat_id, f"Compito non trovato: «{current}»."
            )
            return Action("error")
        assert task.id is not None

        if command == "rename" and not new_name:
            await self._gateway.send(
                message.chat_id, "Indica il nuovo nome: /rename <nome> <nuovo nome>."
            )
            return Action("error")

        summary = _mutation_summary(command, task.name, new_name)
        if not await self._confirmations.confirm(
            requested_by=message.user_id,
            chat_id=message.chat_id,
            summary=summary,
        ):
            return Action("cancelled")

        try:
            if command == "pause":
                self._tasks.pause(task.id)
                reply = f"Compito «{task.name}» sospeso."
            elif command == "resume":
                self._tasks.resume(task.id)
                reply = f"Compito «{task.name}» riattivato."
            elif command == "delete":
                self._tasks.delete(task.id)
                reply = f"Compito «{task.name}» eliminato."
            else:
                renamed = self._tasks.rename(task.id, new_name)
                reply = f"Compito «{task.name}» rinominato in «{renamed.name}»."
        except TaskValidationError as exc:
            await self._gateway.send(message.chat_id, str(exc))
            return Action("error")

        await self._gateway.send(message.chat_id, reply)
        return Action(command, task_id=task.id)

    # --- lancio manuale (spec 04) -----------------------------------------

    async def _launch(self, message: IncomingMessage, role: Role, name: str) -> Action:
        """Inoltra il lancio a C-21 e riporta al richiedente rifiuto o esito."""
        try:
            result = await self._run.run(role, message.user_id, name)
        except RunRefused as exc:
            await self._gateway.send(message.chat_id, str(exc))
            logger.info("lancio rifiutato", extra={"reason": exc.reason})
            return Action("rejected", task_id=None)
        if result.outcome != "ok":
            # P-A-06: il risultato non c'è, ma il richiedente non resta muto.
            await self._gateway.send(message.chat_id, _outcome_notice(result))
        return Action("run", task_id=result.task_id)

    # --- linguaggio naturale ----------------------------------------------

    async def _on_natural(
        self, message: IncomingMessage, role: Role, text: str
    ) -> Action:
        # Il lancio precede il ramo di creazione: «lancia news» non deve
        # diventare una bozza di nuovo compito (spec 04, D3).
        launch = _NL_RUN.match(text)
        if launch is not None:
            return await self._launch(message, role, _clean_name(launch.group("name")))

        mutation = _parse_nl_mutation(text)
        if mutation is not None:
            command, current, new_name = mutation
            if role is not Role.ADMIN:
                await self._gateway.send(message.chat_id, ADMIN_REFUSAL)
                logger.info("modifica rifiutata per ruolo")
                return Action("rejected")
            return await self._mutate(message, command, current, new_name)

        # Spec 09: lo storico precede l'elenco compiti e la chat; una richiesta
        # che contiene un indizio di schedulazione resta una creazione.
        history_match = _NL_HISTORY.match(text)
        if history_match is not None and _NL_SCHEDULE_HINT.search(text) is None:
            return await self._history(
                message,
                role,
                history_match.group("rest").strip(),
                allow_llm=True,
            )

        listing = _NL_LIST.match(text)
        if listing is not None:
            await self._send_list(message, role)
            return Action("listed")

        # Spec 05, D1: la creazione richiede una bozza completa; altrimenti la
        # richiesta è una domanda di chat. Per l'utente autorizzato una bozza
        # completa resta un tentativo di creazione e va rifiutata (spec 02 AC-03).
        if role is not Role.ADMIN:
            draft = await asyncio.to_thread(self._extract_draft, text)
            if draft is not None and _draft_complete(draft):
                await self._gateway.send(message.chat_id, ADMIN_REFUSAL)
                logger.info("creazione rifiutata per ruolo")
                return Action("rejected")
            return await self._chat_reply(message, text)

        draft = await asyncio.to_thread(self._extract_draft, text)
        if draft is None or not _draft_complete(draft):
            return await self._chat_reply(message, text)

        parsed = await asyncio.to_thread(self._interpreter.parse, draft.schedule_text)
        if isinstance(parsed, Ambiguous):
            await self._gateway.send(message.chat_id, parsed.question)
            return Action("ask_schedule")
        schedule: Schedule = parsed

        summary = _draft_summary(draft, schedule)
        if not await self._confirmations.confirm(
            requested_by=message.user_id,
            chat_id=message.chat_id,
            summary=summary,
        ):
            return Action("cancelled")

        try:
            task = self._tasks.create(
                TaskDraft(
                    name=draft.name,
                    instructions=draft.instructions,
                    schedule=schedule,
                    recipients=draft.recipients,
                    log_allowlist=draft.log_allowlist,
                )
            )
        except TaskValidationError as exc:
            await self._gateway.send(message.chat_id, str(exc))
            return Action("error")

        await self._gateway.send(
            message.chat_id,
            f"Compito «{task.name}» creato e attivo: {describe(schedule)}.",
        )
        return Action("created", task_id=task.id)

    def _extract_draft(self, text: str) -> _Draft | None:
        try:
            response = self._llm.chat(
                [
                    {"role": "system", "content": _DRAFT_SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ]
            )
            payload = json.loads(_strip_fence(response.text))
        except (AgenteError, ValueError, TypeError):
            logger.warning("estrazione della bozza non riuscita")
            return None
        if not isinstance(payload, dict):
            return None
        return _Draft(
            name=str(payload.get("name") or "").strip(),
            instructions=str(payload.get("instructions") or "").strip(),
            schedule_text=str(payload.get("schedule") or "").strip(),
            recipients=_ints(payload.get("recipients")),
            log_allowlist=_strings(payload.get("log_allowlist")),
        )

    # --- storico (spec 09) ------------------------------------------------

    async def _history(
        self,
        message: IncomingMessage,
        role: Role,
        argument: str,
        *,
        allow_llm: bool = False,
    ) -> Action:
        """Interpreta il filtro, legge C-11 e invia l'elenco (C-34)."""
        if allow_llm:
            parsed = await asyncio.to_thread(
                self._history_query.parse_filter, argument
            )
        else:
            parsed = self._history_query.parse_filter(argument)

        if isinstance(parsed, AmbiguousPeriod):
            await self._gateway.send(message.chat_id, parsed.question)
            return Action("ask_period" if allow_llm else "error")

        task = None
        if parsed.task_name:
            task = self._history_query.resolve_task(
                parsed.task_name, role=role, user_id=message.user_id
            )
            if task is None and allow_llm and not parsed.period_found:
                window = await asyncio.to_thread(
                    self._history_query.parse_window_with_llm, argument
                )
                if isinstance(window, AmbiguousPeriod):
                    await self._gateway.send(message.chat_id, window.question)
                    return Action("ask_period")
                parsed = ParsedFilter(window, None, True)
            elif task is None:
                await self._gateway.send(
                    message.chat_id,
                    f"Compito non trovato: «{parsed.task_name}».",
                )
                return Action("error")

        try:
            history_filter = self._history_query.build_filter(parsed, task)
        except ValueError:
            await self._gateway.send(message.chat_id, "Operazione non riuscita.")
            return Action("error")

        executions = self._history_query.query(role, message.user_id, history_filter)
        await self._gateway.send(
            message.chat_id,
            self._history_query.render(
                executions,
                label=history_filter.label,
                degenerate=history_filter.degenerate,
            ),
        )
        return Action("history")

    # --- chat (spec 05) ---------------------------------------------------

    async def _chat_reply(self, message: IncomingMessage, text: str) -> Action:
        reply = await self._chat.handle(message.user_id, message.chat_id, text)
        return Action(reply.kind)

    async def _chat_read(self, message: IncomingMessage, argument: str) -> Action:
        if not argument:
            reply = await self._chat.list_authorized(
                message.user_id, message.chat_id
            )
            return Action(reply.kind)
        if not argument.isdigit():
            await self._gateway.send(
                message.chat_id, "Uso: /chat <telegram_id> (solo admin)."
            )
            return Action("error")
        reply = await self._chat.transcript(
            message.user_id, message.chat_id, int(argument)
        )
        return Action(reply.kind)

    # --- utenti (spec 08) -------------------------------------------------

    async def _refuse_unknown(self, message: IncomingMessage) -> None:
        """Rifiuto allo sconosciuto + avviso all'admin (antispam in C-33)."""
        try:
            await self._gateway.send(message.chat_id, UNKNOWN_REFUSAL)
        except (TelegramError, AgenteError) as exc:
            logger.warning(
                "rifiuto a sconosciuto non inviato", extra={"error": str(exc)}
            )
        await self._notifier.notify_unknown(message.user_id, message.username)

    async def _user_command(
        self, message: IncomingMessage, role: Role, name: str, argument: str
    ) -> Action:
        """Comandi di gestione utenti: solo l'amministratore (BR-12)."""
        if role is not Role.ADMIN:
            await self._gateway.send(message.chat_id, USER_ADMIN_REFUSAL)
            logger.info("comando utenti rifiutato per ruolo", extra={"command": name})
            return Action("rejected")

        try:
            if name == "users":
                views = self._users.list_users(message.user_id)
                await self._gateway.send(message.chat_id, _users_summary(views))
                return Action("users_listed")

            if name == "adduser":
                telegram_id, username = _split_adduser(argument)
                result = await self._users.authorize(
                    message.user_id, telegram_id, username=username
                )
            elif name == "removeuser":
                result = self._users.revoke(
                    message.user_id,
                    _parse_id(argument, "Uso: /removeuser <telegram_id>."),
                )
            else:
                task_name, telegram_id = _split_subscription(argument, name)
                task = self._tasks.find(task_name)
                if task is None or task.id is None:
                    await self._gateway.send(
                        message.chat_id, f"Compito non trovato: «{task_name}»."
                    )
                    return Action("error")
                if name == "subscribe":
                    result = self._users.subscribe(
                        message.user_id, telegram_id, task.id
                    )
                else:
                    result = self._users.unsubscribe(
                        message.user_id, telegram_id, task.id
                    )
        except _UsageError as exc:
            await self._gateway.send(message.chat_id, str(exc))
            return Action("error")
        except UserAccessError as exc:
            await self._gateway.send(message.chat_id, _user_error_text(exc))
            return Action("rejected" if exc.reason == "forbidden" else "error")

        await self._gateway.send(message.chat_id, result.note)
        return Action(name)

    async def _on_authorize(
        self, message: IncomingMessage, role: Role, data: str
    ) -> Action:
        """Pulsante «Autorizza»: crea il pending e invia l'informativa."""
        if role is not Role.ADMIN:
            await self._gateway.send(message.chat_id, USER_ADMIN_REFUSAL)
            logger.info("autorizzazione da pulsante rifiutata per ruolo")
            return Action("rejected")
        parts = data.split(":")
        if len(parts) != 2 or not parts[1].isdigit():
            await self._gateway.send(message.chat_id, "Richiesta non valida.")
            return Action("error")
        telegram_id = int(parts[1])
        try:
            result = await self._users.authorize(
                message.user_id,
                telegram_id,
                username=self._notifier.username_for(telegram_id),
            )
        except UserAccessError as exc:
            await self._gateway.send(message.chat_id, _user_error_text(exc))
            return Action("rejected" if exc.reason == "forbidden" else "error")
        await self._gateway.send(message.chat_id, result.note)
        return Action("authorized")

    async def _on_consent(
        self, message: IncomingMessage, role: Role, data: str
    ) -> Action:
        """Bottoni Accetto/Rifiuto dell'informativa privacy (BR-18)."""
        parts = data.split(":")
        if len(parts) != 2 or parts[1] not in ("accept", "decline"):
            return Action("ignored")
        try:
            if parts[1] == "accept":
                result = await self._consent.accept(
                    message.user_id, by_user_id=message.user_id
                )
                kind = "consent_accepted"
            else:
                result = await self._consent.decline(
                    message.user_id, by_user_id=message.user_id
                )
                kind = "consent_declined"
        except UserAccessError as exc:
            await self._gateway.send(message.chat_id, _user_error_text(exc))
            return Action("error")
        await self._gateway.send(message.chat_id, result.note)
        return Action(kind)

    # --- conferme e supporto ----------------------------------------------

    async def _on_callback(
        self, message: IncomingMessage, role: Role
    ) -> Action:
        data = message.callback_data or ""
        if data.startswith(f"{AUTHORIZE_PREFIX}:"):
            return await self._on_authorize(message, role, data)
        if data.startswith(f"{CONSENT_PREFIX}:"):
            return await self._on_consent(message, role, data)
        if data.startswith("approval:"):
            return await self._on_approval(message, role, data)
        if not data.startswith(f"{CONFIRM_PREFIX}:"):
            return Action("ignored")
        parts = data.split(":")
        if len(parts) != 3:
            return Action("ignored")
        _, confirmation_id, verdict = parts
        approved = verdict == "yes"
        if self._confirmations.resolve(
            confirmation_id, approved, by_user_id=message.user_id
        ):
            return Action("confirm_resolved")
        await self._gateway.send(
            message.chat_id, "Conferma non valida o già scaduta."
        )
        return Action("error")

    async def _on_approval(
        self, message: IncomingMessage, role: Role, data: str
    ) -> Action:
        """Risolve una richiesta di C-28; solo l'admin (A5)."""
        parts = data.split(":")
        if len(parts) != 3 or parts[2] not in ("approve", "reject"):
            await self._gateway.send(
                message.chat_id, "Richiesta non valida o scaduta."
            )
            return Action("error")
        if role is not Role.ADMIN:
            await self._gateway.send(
                message.chat_id, "Solo l'amministratore può approvare le azioni."
            )
            logger.info("approvazione rifiutata per ruolo")
            return Action("rejected")
        try:
            approval_id = int(parts[1])
        except ValueError:
            await self._gateway.send(
                message.chat_id, "Richiesta non valida o scaduta."
            )
            return Action("error")

        decision = "approved" if parts[2] == "approve" else "rejected"
        if not self._approvals.resolve(
            approval_id, decision, by_user_id=message.user_id
        ):
            await self._gateway.send(
                message.chat_id, "Richiesta non valida o scaduta."
            )
            return Action("error")
        text = (
            "Azione approvata."
            if decision == "approved"
            else "Azione rifiutata."
        )
        await self._gateway.send(message.chat_id, text)
        return Action("approval_resolved")

    async def _send_list(self, message: IncomingMessage, role: Role) -> None:
        views = self._tasks.list(role, message.user_id)
        if not views:
            await self._gateway.send(message.chat_id, "Nessun compito.")
            return
        lines = [f"Compiti ({len(views)}):"]
        lines.extend(_view_line(view) for view in views)
        await self._gateway.send(message.chat_id, "\n".join(lines))


_CONFIRM_WORDS = frozenset(
    {"sì", "si", "confermo", "approvo", "ok", "no", "annulla", "annullo"}
)

# Modifica in linguaggio naturale (spec 02, §Flussi 3): solo verbi imperativi in
# apertura, così una richiesta di creazione («ogni giorno elimina i file») non
# viene scambiata per un'eliminazione.
_NL_MUTATIONS = (
    ("rename", re.compile(
        r"^(?:rinomina|chiama)\s+(?P<name>.+?)\s+(?:in|come)\s+(?P<new>.+)$",
        re.IGNORECASE,
    )),
    ("pause", re.compile(r"^(?:sospendi|metti\s+in\s+pausa|pausa)\s+(?P<name>.+)$", re.IGNORECASE)),
    ("resume", re.compile(r"^(?:riattiva|riprendi|riavvia)\s+(?P<name>.+)$", re.IGNORECASE)),
    ("delete", re.compile(r"^(?:elimina|cancella|rimuovi)\s+(?P<name>.+)$", re.IGNORECASE)),
)

_NL_LIST = re.compile(
    r"^(?:elenca|mostra|lista|quali)\w*\b.*\bcompit", re.IGNORECASE
)

_NL_HISTORY = re.compile(
    r"^(?:che\s+cosa\s+(?:hai|ha|avete)\s+fatto"
    r"|cosa\s+(?:hai|ha|avete)\s+fatto"
    r"|mostra(?:mi)?\s+(?:lo|le)?\s*(?:storico|esecuzioni)"
    r"|(?:lo|il)?\s*storico"
    r"|(?:le|gli)?\s*esecuzioni)\b(?P<rest>.*)$",
    re.IGNORECASE,
)

# Spec 09, P-A-13: un indizio di schedulazione vince sulla richiesta di storico.
_NL_SCHEDULE_HINT = re.compile(
    r"\b(?:ogni|tutti\s+i\s+giorni|giornalier\w*|settimanal\w*|mensil\w*|intervall\w*)",
    re.IGNORECASE,
)

# Lancio manuale in linguaggio naturale: solo il verbo documentato da spec 04
# (decisione D3); i sinonimi non sono dichiarati e non si inventano.
_NL_RUN = re.compile(r"^lancia\s+(?P<name>.+)$", re.IGNORECASE)

_ARTICLES = ("il compito ", "la lista ", "il ", "lo ", "la ", "i ", "gli ", "le ")


def _parse_nl_mutation(text: str) -> tuple[str, str, str] | None:
    for command, pattern in _NL_MUTATIONS:
        match = pattern.match(text.strip())
        if match is None:
            continue
        name = _clean_name(match.group("name"))
        if command == "rename":
            new_name = _clean_name(match.group("new"))
            if not name or not new_name:
                return None
            return command, name, new_name
        if not name:
            return None
        return command, name, ""
    return None


def _clean_name(value: str) -> str:
    cleaned = value.strip().strip("«»\"'`.,;:!?").strip()
    lowered = cleaned.lower()
    for article in _ARTICLES:
        if lowered.startswith(article):
            cleaned = cleaned[len(article):].strip()
            break
    return cleaned


def _mutation_summary(command: str, name: str, new_name: str = "") -> str:
    labels = {
        "pause": "sospendi",
        "resume": "riattiva",
        "delete": "elimina",
        "rename": "rinomina",
    }
    label = labels.get(command, command)
    lines = [f"Azione: {label} compito", f"Nome: {name}"]
    if command == "rename":
        lines.append(f"Nuovo nome: {new_name}")
    lines.append("Conferma per applicare la modifica.")
    return "\n".join(lines)


def _draft_summary(draft: _Draft, schedule: Schedule) -> str:
    recipients = ", ".join(str(item) for item in draft.recipients) or "solo amministratore"
    allowlist = ", ".join(draft.log_allowlist) or "nessuna"
    return "\n".join(
        [
            "Nuovo compito",
            f"Nome: {draft.name}",
            f"Istruzioni: {draft.instructions}",
            f"Orario: {describe(schedule)}",
            f"Destinatari: {recipients}",
            f"Log consentiti: {allowlist}",
        ]
    )


def _draft_complete(draft: _Draft) -> bool:
    """La bozza è completa solo con nome, istruzioni e schedulazione (D1)."""
    return bool(draft.name and draft.instructions and draft.schedule_text)


def _outcome_notice(result: ExecutionResult) -> str:
    """Riga di stato per un lancio manuale senza risultato (P-A-06)."""
    label = "interrotta" if result.outcome == "interrotto" else "non riuscita"
    detail = (result.summary or "").strip()
    return f"Esecuzione {label}: {detail}" if detail else f"Esecuzione {label}."


def _view_line(view: TaskView) -> str:
    task = view.task
    try:
        schedule = describe(
            Schedule(task.schedule_type, task.schedule_expr)  # type: ignore[arg-type]
        )
    except Exception:  # noqa: BLE001 - espressione storica non interpretabile
        schedule = f"{task.schedule_type} {task.schedule_expr}"
    recipients = ", ".join(str(item) for item in view.recipients) or "nessuno"
    return f"• {task.name} — {task.state} — {schedule} — destinatari: {recipients}"


def _ints(value: Any) -> tuple[int, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(int(item) for item in value if isinstance(item, (int, str)) and str(item).lstrip("-").isdigit())


def _strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


class _UsageError(ValueError):
    """Sintassi di un comando errata: il testo è il messaggio d'uso."""


def _parse_id(argument: str, usage: str) -> int:
    text = (argument or "").strip()
    if not text.isdigit():
        raise _UsageError(usage)
    return int(text)


def _split_adduser(argument: str) -> tuple[int, str | None]:
    parts = (argument or "").split()
    if not parts or not parts[0].isdigit():
        raise _UsageError("Uso: /adduser <telegram_id> [username].")
    username = parts[1].lstrip("@").strip() if len(parts) > 1 else ""
    return int(parts[0]), username or None


def _split_subscription(argument: str, command: str) -> tuple[str, int]:
    usage = f"Uso: /{command} <compito> <telegram_id>."
    parts = (argument or "").rsplit(maxsplit=1)
    if len(parts) != 2 or not parts[1].isdigit():
        raise _UsageError(usage)
    task_name = parts[0].strip().strip("«»\"'`")
    if not task_name:
        raise _UsageError(usage)
    return task_name, int(parts[1])


def _users_summary(views: Sequence[Any]) -> str:
    if not views:
        return "Nessun utente."
    lines = [f"Utenti ({len(views)}):"]
    for view in views:
        user = view.user
        who = (
            f"{user.telegram_id} (@{user.username})"
            if user.username
            else str(user.telegram_id)
        )
        tasks = ", ".join(view.task_names) or "nessuno"
        lines.append(f"• {who} — {user.state} — compiti: {tasks}")
    return "\n".join(lines)


_USER_ERRORS = {
    "forbidden": USER_ADMIN_REFUSAL,
    "invalid_state": "Operazione non ammessa per lo stato attuale dell'utente.",
    "invalid_target": "Operazione non ammessa su questo utente.",
}


def _user_error_text(exc: UserAccessError) -> str:
    if exc.reason == "limit":
        return (
            f"Limite di {MAX_AUTHORIZED_USERS} utenti autorizzati raggiunto: "
            "revoca un utente prima di autorizzarne un altro."
        )
    message = _USER_ERRORS.get(exc.reason)
    if message is not None:
        return message
    if exc.reason == "not_found":
        text = str(exc)
        return text[:1].upper() + text[1:] + "."
    return "Operazione non riuscita."


def _strip_fence(text: str) -> str:
    stripped = text.strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end > start:
        return stripped[start : end + 1]
    return stripped
