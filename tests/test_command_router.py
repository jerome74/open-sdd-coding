"""C-14: comandi rapidi, ruoli e passaggio obbligatorio da C-17."""

from __future__ import annotations

import asyncio

from agente.command_router import HELP_TEXT
from agente.schedule_interpreter import Schedule
from agente.task_manager import TaskDraft
from agente.telegram_gateway import IncomingMessage
from agente.storage.repositories import User
from conftest import ADMIN_ID, USER_ID, FakeLLM


def message(text: str = "", *, user: int = ADMIN_ID, callback: str | None = None) -> IncomingMessage:
    return IncomingMessage(
        user_id=user, chat_id=user, text=text, callback_data=callback
    )


async def approve(harness, approved: bool = True, *, by: int = ADMIN_ID) -> bool:
    for _ in range(300):
        pending = harness.confirmations.pending()
        if pending:
            return harness.confirmations.resolve(pending[0], approved, by_user_id=by)
        await asyncio.sleep(0.01)
    raise AssertionError("nessuna conferma in sospeso")


def seeded(harness, name: str = "rassegna", schedule: Schedule | None = None):
    task = harness.manager.create(
        TaskDraft(
            name=name,
            instructions="riassumi i log",
            schedule=schedule or Schedule("orario", "08:00"),
        )
    )
    harness.gateway.sent.clear()
    harness.registrar.scheduled.clear()
    harness.registrar.unscheduled.clear()
    return task


def test_help_and_unknown_command(harness_factory) -> None:
    harness = harness_factory()

    async def scenario() -> None:
        await harness.router.route(message("/help"))
        await harness.router.route(message("/sconosciuto"))

    asyncio.run(scenario())
    assert harness.gateway.texts() == [HELP_TEXT, HELP_TEXT]


def test_tasks_list_for_admin_and_authorized(harness_factory) -> None:
    harness = harness_factory()
    first = seeded(harness, "alfa")
    seeded(harness, "beta")
    harness.repos.subscriptions.add(USER_ID, first.id)

    async def scenario() -> None:
        await harness.router.route(message("/tasks"))
        await harness.router.route(message("/tasks", user=USER_ID))

    asyncio.run(scenario())
    admin_list, user_list = harness.gateway.texts()
    assert "alfa" in admin_list and "beta" in admin_list
    assert "alfa" in user_list and "beta" not in user_list


def test_pause_needs_confirmation_before_effect(harness_factory) -> None:
    harness = harness_factory()
    task = seeded(harness)

    async def scenario() -> tuple[str, str]:
        routing = asyncio.create_task(harness.router.route(message("/pause rassegna")))
        await approve(harness)
        action = await routing
        state = harness.repos.tasks.get(task.id).state
        return action.kind, state

    kind, state = asyncio.run(scenario())
    assert kind == "pause"
    assert state == "paused"
    assert harness.registrar.unscheduled == [task.id]
    assert "Riepilogo in attesa di conferma" in harness.gateway.sent[0][1]
    assert "sospeso" in harness.gateway.last()


def test_rejected_confirmation_leaves_task_active(harness_factory) -> None:
    harness = harness_factory()
    task = seeded(harness)

    async def scenario() -> str:
        routing = asyncio.create_task(harness.router.route(message("/delete rassegna")))
        await approve(harness, approved=False)
        action = await routing
        return action.kind

    assert asyncio.run(scenario()) == "cancelled"
    assert harness.repos.tasks.get(task.id) is not None
    assert "Operazione annullata." in harness.gateway.last()


def test_delete_and_rename_after_confirmation(harness_factory) -> None:
    harness = harness_factory()
    first = seeded(harness, "alfa")
    second = seeded(harness, "beta")

    async def scenario() -> None:
        routing = asyncio.create_task(harness.router.route(message("/rename alfa Gamma")))
        await approve(harness)
        await routing
        routing = asyncio.create_task(harness.router.route(message("/delete beta")))
        await approve(harness)
        await routing

    asyncio.run(scenario())
    assert harness.repos.tasks.get(first.id).name == "Gamma"
    assert harness.repos.tasks.get(second.id) is None


def test_rename_to_existing_name_reports_error(harness_factory) -> None:
    harness = harness_factory()
    seeded(harness, "alfa")
    seeded(harness, "beta")

    async def scenario() -> None:
        routing = asyncio.create_task(harness.router.route(message("/rename alfa BETA")))
        await approve(harness)
        await routing

    asyncio.run(scenario())
    assert "esiste già un compito" in harness.gateway.last()


def test_missing_name_and_unknown_task(harness_factory) -> None:
    harness = harness_factory()

    async def scenario() -> None:
        await harness.router.route(message("/pause"))
        await harness.router.route(message("/pause inesistente"))

    asyncio.run(scenario())
    assert "Indica il nome" in harness.gateway.sent[0][1]
    assert "Compito non trovato" in harness.gateway.sent[1][1]


def test_authorized_user_cannot_mutate(harness_factory) -> None:
    harness = harness_factory()
    task = seeded(harness)

    async def scenario() -> None:
        await harness.router.route(message("/pause rassegna", user=USER_ID))
        await harness.router.route(message("/delete rassegna", user=USER_ID))

    asyncio.run(scenario())
    assert harness.repos.tasks.get(task.id).state == "active"
    assert all("Solo l'amministratore" in text for text in harness.gateway.texts())


def test_unknown_user_is_ignored(harness_factory) -> None:
    harness = harness_factory()

    async def scenario() -> str:
        action = await harness.router.route(message("/tasks", user=999))
        return action.kind

    assert asyncio.run(scenario()) == "ignored"
    refused, alert = harness.gateway.sent
    assert refused[:2] == (999, "Non sei autorizzato a usare questo agente.")
    assert alert[0] == ADMIN_ID
    assert "Nuovo contatto" in alert[1] and "999" in alert[1]
    assert "Autorizza" in str(alert[2])


def test_callback_button_resolves_confirmation(harness_factory) -> None:
    harness = harness_factory()
    task = seeded(harness)

    async def scenario() -> None:
        routing = asyncio.create_task(harness.router.route(message("/pause rassegna")))
        while not harness.confirmations.pending():
            await asyncio.sleep(0.01)
        confirmation_id = harness.confirmations.pending()[0]
        await harness.router.route(
            message(callback=f"confirm:{confirmation_id}:yes")
        )
        await routing

    asyncio.run(scenario())
    assert harness.repos.tasks.get(task.id).state == "paused"


def test_text_fallback_resolves_confirmation(harness_factory) -> None:
    harness = harness_factory()
    task = seeded(harness)

    async def scenario() -> None:
        routing = asyncio.create_task(harness.router.route(message("/pause rassegna")))
        while not harness.confirmations.pending():
            await asyncio.sleep(0.01)
        await harness.router.route(message("sì"))
        await routing

    asyncio.run(scenario())
    assert harness.repos.tasks.get(task.id).state == "paused"


def test_natural_language_mutations(harness_factory) -> None:
    harness = harness_factory()
    task = seeded(harness)

    async def run(text: str) -> None:
        routing = asyncio.create_task(harness.router.route(message(text)))
        await approve(harness)
        await routing

    async def scenario() -> None:
        await run("sospendi rassegna")
        await run("riattiva rassegna")
        await run("rinomina rassegna in Gamma")

    asyncio.run(scenario())
    stored = harness.repos.tasks.get(task.id)
    assert stored.name == "Gamma"
    assert stored.state == "active"


def test_natural_language_list_request(harness_factory) -> None:
    harness = harness_factory()
    task = seeded(harness, "alfa")
    harness.repos.subscriptions.add(USER_ID, task.id)

    async def scenario() -> None:
        await harness.router.route(message("mostrami i compiti", user=USER_ID))

    asyncio.run(scenario())
    assert "alfa" in harness.gateway.last()


def test_creation_text_with_verb_inside_is_not_a_mutation(harness_factory) -> None:
    from conftest import FakeLLM

    llm = FakeLLM(
        draft={
            "name": "pulizia",
            "instructions": "elimina i file temporanei",
            "schedule": "ogni giorno alle 8",
            "recipients": [],
            "log_allowlist": [],
        }
    )
    harness = harness_factory(llm=llm)

    async def scenario() -> str:
        routing = asyncio.create_task(
            harness.router.route(message("ogni giorno alle 8 elimina i file temporanei"))
        )
        await approve(harness)
        action = await routing
        return action.kind

    assert asyncio.run(scenario()) == "created"
    assert [task.name for task in harness.repos.tasks.list()] == ["pulizia"]


def test_natural_language_mutation_refused_for_authorized_user(harness_factory) -> None:
    harness = harness_factory()
    task = seeded(harness)

    async def scenario() -> str:
        action = await harness.router.route(message("elimina rassegna", user=USER_ID))
        return action.kind

    assert asyncio.run(scenario()) == "rejected"
    assert harness.repos.tasks.get(task.id) is not None


def test_run_command_and_natural_language_launch(harness_factory) -> None:
    harness = harness_factory()
    task = seeded(harness, "news")
    harness.repos.subscriptions.add(USER_ID, task.id)

    async def scenario() -> list[str]:
        first = await harness.router.route(message("/run news"))
        second = await harness.router.route(message("lancia news"))
        return [first.kind, second.kind]

    assert asyncio.run(scenario()) == ["run", "run"]
    manual = [
        execution
        for execution in harness.repos.executions.list(task_id=task.id)
        if execution.trigger == "manual"
    ]
    assert len(manual) == 2
    assert {execution.requested_by for execution in manual} == {ADMIN_ID}


def test_natural_launch_is_not_treated_as_creation(harness_factory) -> None:
    harness = harness_factory()
    seeded(harness, "news")

    async def scenario() -> None:
        await harness.router.route(message("lancia news"))

    asyncio.run(scenario())

    assert [task.name for task in harness.repos.tasks.list()] == ["news"]
    assert harness.confirmations.pending() == []


def test_run_is_refused_for_an_unsubscribed_user(harness_factory) -> None:
    harness = harness_factory()
    task = seeded(harness, "log")

    async def scenario() -> str:
        action = await harness.router.route(message("/run log", user=USER_ID))
        return action.kind

    assert asyncio.run(scenario()) == "rejected"
    assert "Non sei iscritto" in harness.gateway.last()
    assert harness.repos.executions.list(task_id=task.id) == []


def test_run_without_name_shows_usage(harness_factory) -> None:
    harness = harness_factory()

    async def scenario() -> str:
        action = await harness.router.route(message("/run"))
        return action.kind

    assert asyncio.run(scenario()) == "rejected"
    assert "Indica il compito da lanciare" in harness.gateway.last()


def test_run_on_an_unknown_task_lists_the_available_ones(harness_factory) -> None:
    harness = harness_factory()
    seeded(harness, "news")

    async def scenario() -> None:
        await harness.router.route(message("/run bollettino"))

    asyncio.run(scenario())

    reply = harness.gateway.last()
    assert "Compito non trovato: «bollettino»." in reply
    assert "news" in reply


def test_admin_incomplete_draft_falls_back_to_chat(harness_factory) -> None:
    # FakeLLM restituisce una bozza vuota: incompleta, quindi domanda di chat.
    harness = harness_factory()

    async def scenario() -> str:
        action = await harness.router.route(message("qual è il meteo?"))
        return action.kind

    assert asyncio.run(scenario()) == "answered"
    assert harness.repos.tasks.list() == []
    assert harness.confirmations.pending() == []


def test_admin_complete_draft_still_creates_a_task(harness_factory) -> None:
    harness = harness_factory(
        llm=FakeLLM(
            draft={
                "name": "rassegna",
                "instructions": "riassumi i titoli",
                "schedule": "ogni giorno alle 8",
                "recipients": [],
                "log_allowlist": [],
            }
        )
    )

    async def scenario() -> str:
        routing = asyncio.create_task(
            harness.router.route(message("ogni giorno alle 8 riassumi i titoli"))
        )
        while not harness.confirmations.pending():
            await asyncio.sleep(0.01)
        harness.confirmations.resolve(
            harness.confirmations.pending()[0], True, by_user_id=ADMIN_ID
        )
        return (await routing).kind

    assert asyncio.run(scenario()) == "created"
    assert [task.name for task in harness.repos.tasks.list()] == ["rassegna"]


def test_revoked_user_is_ignored(harness_factory) -> None:
    harness = harness_factory()
    harness.repos.users.upsert(
        User(telegram_id=USER_ID, username="utente", state="revoked")
    )

    async def scenario() -> str:
        action = await harness.router.route(message("ciao", user=USER_ID))
        return action.kind

    assert asyncio.run(scenario()) == "ignored"
    texts = harness.gateway.texts()
    assert texts[0] == "Non sei autorizzato a usare questo agente."
    assert any("Nuovo contatto" in text for text in texts)


def test_chat_command_without_argument_lists_authorized_users(harness_factory) -> None:
    harness = harness_factory()

    async def scenario() -> str:
        action = await harness.router.route(message("/chat"))
        return action.kind

    assert asyncio.run(scenario()) == "transcript"
    assert "Utenti autorizzati" in harness.gateway.last()


def test_chat_command_with_invalid_id_shows_usage(harness_factory) -> None:
    harness = harness_factory()

    async def scenario() -> str:
        action = await harness.router.route(message("/chat utente"))
        return action.kind

    assert asyncio.run(scenario()) == "error"
    assert "Uso: /chat" in harness.gateway.last()


def test_authorized_user_incomplete_draft_goes_to_chat(harness_factory) -> None:
    # FakeLLM restituisce una bozza vuota: non è un tentativo di creazione,
    # quindi l'utente autorizzato riceve una risposta di chat (P-A-19).
    harness = harness_factory()

    async def scenario() -> str:
        action = await harness.router.route(message("che tempo fa?", user=USER_ID))
        return action.kind

    assert asyncio.run(scenario()) == "answered"
    assert harness.repos.tasks.list() == []


async def _start_approval(harness, requester=USER_ID):
    task = asyncio.create_task(
        harness.approvals.request(
            action="delete_file", reason="pulizia", requester=requester
        )
    )
    for _ in range(100):
        if harness.gateway.sent:
            break
        await asyncio.sleep(0.01)
    keyboard = harness.gateway.sent[-1][2]
    approval_id = int(keyboard[0][0][1].split(":")[1])
    return task, approval_id


def test_admin_resolves_an_approval(harness_factory) -> None:
    harness = harness_factory()

    async def scenario() -> str:
        pending, approval_id = await _start_approval(harness)
        action = await harness.router.route(
            IncomingMessage(
                user_id=ADMIN_ID,
                chat_id=ADMIN_ID,
                callback_data=f"approval:{approval_id}:approve",
            )
        )
        approval = await pending
        assert approval.status == "approved"
        return action.kind

    assert asyncio.run(scenario()) == "approval_resolved"
    assert "Azione approvata." in harness.gateway.last()


def test_non_admin_cannot_resolve_an_approval(harness_factory) -> None:
    harness = harness_factory()

    async def scenario() -> str:
        pending, approval_id = await _start_approval(harness)
        action = await harness.router.route(
            IncomingMessage(
                user_id=USER_ID,
                chat_id=USER_ID,
                callback_data=f"approval:{approval_id}:approve",
            )
        )
        assert harness.repos.approvals.get(approval_id).status == "pending"
        harness.approvals.resolve(approval_id, "rejected", by_user_id=ADMIN_ID)
        await pending
        return action.kind

    assert asyncio.run(scenario()) == "rejected"
    assert "Solo l'amministratore" in harness.gateway.last()


def test_unknown_approval_is_reported(harness_factory) -> None:
    harness = harness_factory()

    async def scenario() -> str:
        action = await harness.router.route(
            IncomingMessage(
                user_id=ADMIN_ID,
                chat_id=ADMIN_ID,
                callback_data="approval:999:approve",
            )
        )
        return action.kind

    assert asyncio.run(scenario()) == "error"
    assert "non valida o scaduta" in harness.gateway.last()


# --- spec 08: gestione utenti ------------------------------------------------


def _incoming(text: str, *, user: int, username: str | None = None, callback: str | None = None):
    return IncomingMessage(
        user_id=user, chat_id=user, text=text, callback_data=callback, username=username
    )


def test_adduser_command(harness_factory) -> None:
    harness = harness_factory()

    async def scenario() -> str:
        action = await harness.router.route(message("/adduser 55 mario"))
        return action.kind

    assert asyncio.run(scenario()) == "adduser"
    user = harness.repos.users.get(55)
    assert user.state == "pending" and user.username == "mario"
    assert "in attesa" in harness.gateway.texts()[-1]
    assert any(
        chat_id == 55 and "Privacy" in text for chat_id, text, _ in harness.gateway.sent
    )


def test_adduser_without_argument_reports_usage(harness_factory) -> None:
    harness = harness_factory()

    async def scenario() -> str:
        action = await harness.router.route(message("/adduser"))
        return action.kind

    assert asyncio.run(scenario()) == "error"
    assert "Uso: /adduser" in harness.gateway.last()


def test_removeuser_command(harness_factory) -> None:
    harness = harness_factory()

    async def scenario() -> str:
        action = await harness.router.route(message(f"/removeuser {USER_ID}"))
        return action.kind

    assert asyncio.run(scenario()) == "removeuser"
    assert harness.repos.users.get(USER_ID).state == "revoked"
    assert "revocato" in harness.gateway.last()


def test_users_command_lists_states(harness_factory) -> None:
    harness = harness_factory()
    harness.repos.users.upsert(User(telegram_id=77, username="anna", state="pending"))
    task = seeded(harness, "news")
    harness.repos.subscriptions.add(USER_ID, task.id)

    async def scenario() -> str:
        action = await harness.router.route(message("/users"))
        return action.kind

    assert asyncio.run(scenario()) == "users_listed"
    text = harness.gateway.last()
    assert "Utenti (2):" in text
    assert f"{USER_ID} (@utente) — accepted — compiti: news" in text
    assert "77 (@anna) — pending — compiti: nessuno" in text


def test_subscribe_and_unsubscribe_commands(harness_factory) -> None:
    harness = harness_factory()
    task = seeded(harness, "rassegna news")

    async def scenario() -> None:
        await harness.router.route(message(f"/subscribe rassegna news {USER_ID}"))
        await harness.router.route(message(f"/unsubscribe rassegna news {USER_ID}"))

    asyncio.run(scenario())
    assert f"Utente {USER_ID} iscritto al compito «rassegna news»." in harness.gateway.texts()
    assert f"Utente {USER_ID} disiscritto dal compito «rassegna news»." in harness.gateway.texts()
    assert harness.repos.subscriptions.tasks_for_user(USER_ID) == []
    assert task.id is not None


def test_subscribe_requires_an_accepted_user(harness_factory) -> None:
    harness = harness_factory()
    seeded(harness, "news")
    harness.repos.users.upsert(User(telegram_id=88, state="pending"))

    async def scenario() -> str:
        action = await harness.router.route(message("/subscribe news 88"))
        return action.kind

    assert asyncio.run(scenario()) == "error"
    assert "stato attuale" in harness.gateway.last()


def test_subscribe_unknown_task(harness_factory) -> None:
    harness = harness_factory()

    async def scenario() -> str:
        action = await harness.router.route(message(f"/subscribe inesistente {USER_ID}"))
        return action.kind

    assert asyncio.run(scenario()) == "error"
    assert "Compito non trovato" in harness.gateway.last()


def test_authorized_user_cannot_manage_users(harness_factory) -> None:
    harness = harness_factory()

    async def scenario() -> None:
        await harness.router.route(message("/adduser 55", user=USER_ID))
        await harness.router.route(message("/users", user=USER_ID))
        await harness.router.route(message(f"/removeuser {USER_ID}", user=USER_ID))

    asyncio.run(scenario())
    assert harness.repos.users.get(55) is None
    assert harness.repos.users.get(USER_ID).state == "accepted"
    assert all("Solo l'amministratore può gestire gli utenti." in text for text in harness.gateway.texts())


def test_authorize_callback_starts_the_consent_flow(harness_factory) -> None:
    harness = harness_factory()

    async def scenario() -> str:
        await harness.router.route(_incoming("ciao", user=999, username="mario"))
        action = await harness.router.route(_incoming("", user=ADMIN_ID, callback="authorize:999"))
        return action.kind

    assert asyncio.run(scenario()) == "authorized"
    user = harness.repos.users.get(999)
    assert user.state == "pending"
    assert user.username == "mario"
    assert any(
        chat_id == 999 and "Privacy" in text
        for chat_id, text, _ in harness.gateway.sent
    )


def test_authorize_callback_refused_for_non_admin(harness_factory) -> None:
    harness = harness_factory()

    async def scenario() -> str:
        action = await harness.router.route(
            _incoming("", user=USER_ID, callback="authorize:999")
        )
        return action.kind

    assert asyncio.run(scenario()) == "rejected"
    assert harness.repos.users.get(999) is None
    assert "Solo l'amministratore può gestire gli utenti." in harness.gateway.last()


def test_consent_callbacks_accept_and_decline(harness_factory) -> None:
    harness = harness_factory()
    harness.repos.users.upsert(User(telegram_id=55, state="pending"))
    harness.repos.users.upsert(User(telegram_id=56, state="pending"))

    async def scenario() -> tuple[str, str]:
        accepted = await harness.router.route(
            _incoming("", user=55, callback="consent:accept")
        )
        declined = await harness.router.route(
            _incoming("", user=56, callback="consent:decline")
        )
        return accepted.kind, declined.kind

    kinds = asyncio.run(scenario())
    assert kinds == ("consent_accepted", "consent_declined")
    assert harness.repos.users.get(55).state == "accepted"
    assert harness.repos.users.get(55).consent_at is not None
    assert harness.repos.users.get(56).state == "revoked"
    assert any("ha rifiutato l'informativa" in text for text in harness.gateway.texts())


def test_consent_callback_for_unknown_user_does_not_alert(harness_factory) -> None:
    harness = harness_factory()

    async def scenario() -> str:
        action = await harness.router.route(
            _incoming("", user=777, callback="consent:accept")
        )
        return action.kind

    assert asyncio.run(scenario()) == "error"
    assert harness.gateway.texts() == ["Utente non trovato: 777."]


def test_user_errors_are_translated(harness_factory) -> None:
    from agente.command_router import _user_error_text
    from agente.errors import UserAccessError

    harness = harness_factory()

    async def scenario() -> str:
        action = await harness.router.route(message("/removeuser 404"))
        return action.kind

    assert asyncio.run(scenario()) == "error"
    assert harness.gateway.last() == "Utente non trovato: 404."
    assert _user_error_text(UserAccessError("x", reason="limit")).startswith(
        "Limite di 5 utenti autorizzati raggiunto"
    )
    assert (
        _user_error_text(UserAccessError("x", reason="invalid_state"))
        == "Operazione non ammessa per lo stato attuale dell'utente."
    )
    assert (
        _user_error_text(UserAccessError("x", reason="invalid_target"))
        == "Operazione non ammessa su questo utente."
    )


def test_unknown_reason_has_a_generic_message() -> None:
    from agente.command_router import _user_error_text
    from agente.errors import UserAccessError

    assert _user_error_text(UserAccessError("x", reason="boh")) == "Operazione non riuscita."


# --- spec 09: storico delle esecuzioni --------------------------------------

from datetime import datetime, timezone

from agente.history_query import EMPTY_HISTORY, PERIOD_USAGE

HISTORY_NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


def _execution(harness, task, *, at="2026-10-31T09:00:00+00:00", outcome="ok", summary="fatto"):
    execution = harness.history.record(
        task_id=task.id, trigger="scheduled", requested_by=None, started_at=at
    )
    harness.history.finish(execution.id, outcome=outcome, summary=summary)
    return execution


def test_history_command_default(harness_factory) -> None:
    harness = harness_factory(clock=lambda: HISTORY_NOW)
    task = seeded(harness, "news")
    _execution(harness, task, at="2026-11-01T11:00:00+00:00")

    async def scenario() -> str:
        action = await harness.router.route(message("/history"))
        return action.kind

    assert asyncio.run(scenario()) == "history"
    assert "Storico — ultime 24 ore" in harness.gateway.last()
    assert "news — ok — fatto" in harness.gateway.last()


def test_history_command_with_period_and_task(harness_factory) -> None:
    harness = harness_factory(clock=lambda: HISTORY_NOW)
    news = seeded(harness, "news")
    log = seeded(harness, "log")
    _execution(harness, news, at="2026-10-31T09:00:00+00:00")
    _execution(harness, log, at="2026-10-31T10:00:00+00:00")

    async def scenario() -> str:
        action = await harness.router.route(message("/history ieri news"))
        return action.kind

    assert asyncio.run(scenario()) == "history"
    text = harness.gateway.last()
    assert "Storico — ieri (31/10)" in text
    assert "news" in text and "log" not in text


def test_history_command_accepts_task_only(harness_factory) -> None:
    harness = harness_factory(clock=lambda: HISTORY_NOW)
    news = seeded(harness, "news")
    _execution(harness, news, at="2026-11-01T11:00:00+00:00")

    async def scenario() -> str:
        action = await harness.router.route(message("/history news"))
        return action.kind

    assert asyncio.run(scenario()) == "history"
    assert "ultime 24 ore" in harness.gateway.last()


def test_history_usage_for_unknown_argument(harness_factory) -> None:
    harness = harness_factory(clock=lambda: HISTORY_NOW)

    async def scenario() -> str:
        action = await harness.router.route(message("/history 31/13"))
        return action.kind

    assert asyncio.run(scenario()) == "error"
    assert harness.gateway.last() == PERIOD_USAGE


def test_history_unknown_task(harness_factory) -> None:
    harness = harness_factory(clock=lambda: HISTORY_NOW)

    async def scenario() -> str:
        action = await harness.router.route(message("/history inesistente"))
        return action.kind

    assert asyncio.run(scenario()) == "error"
    assert harness.gateway.last() == "Compito non trovato: «inesistente»."


def test_history_degenerate_command(harness_factory) -> None:
    harness = harness_factory(clock=lambda: HISTORY_NOW)

    async def scenario() -> str:
        action = await harness.router.route(message("/history 1/1/2020"))
        return action.kind

    assert asyncio.run(scenario()) == "history"
    assert harness.gateway.last() == (
        "Nessuna esecuzione conservata: il periodo precede la retention di 30 giorni."
    )


def test_history_empty_result(harness_factory) -> None:
    harness = harness_factory(clock=lambda: HISTORY_NOW)

    async def scenario() -> str:
        action = await harness.router.route(message("/history"))
        return action.kind

    assert asyncio.run(scenario()) == "history"
    assert harness.gateway.last() == EMPTY_HISTORY


def test_natural_history_request_does_not_reach_chat(harness_factory) -> None:
    harness = harness_factory(clock=lambda: HISTORY_NOW)
    task = seeded(harness, "news")
    _execution(harness, task, at="2026-10-31T09:00:00+00:00")

    async def scenario() -> str:
        action = await harness.router.route(message("cosa hai fatto ieri?"))
        return action.kind

    assert asyncio.run(scenario()) == "history"
    assert "Storico — ieri (31/10)" in harness.gateway.last()
    assert "news — ok — fatto" in harness.gateway.last()


def test_history_request_is_case_insensitive(harness_factory) -> None:
    harness = harness_factory(clock=lambda: HISTORY_NOW)

    async def scenario() -> str:
        action = await harness.router.route(message("Cosa hai fatto ieri?"))
        return action.kind

    assert asyncio.run(scenario()) == "history"


def test_history_request_wins_over_task_list(harness_factory) -> None:
    harness = harness_factory(clock=lambda: HISTORY_NOW)
    seeded(harness, "news")

    async def scenario() -> str:
        action = await harness.router.route(message("mostra lo storico dei compiti"))
        return action.kind

    assert asyncio.run(scenario()) == "history"
    assert harness.gateway.last() == EMPTY_HISTORY


def test_history_ambiguous_nl_asks_period(harness_factory) -> None:
    harness = harness_factory(clock=lambda: HISTORY_NOW)

    async def scenario() -> str:
        action = await harness.router.route(message("storico dell'altro giorno"))
        return action.kind

    assert asyncio.run(scenario()) == "ask_period"
    assert harness.gateway.last() == PERIOD_USAGE


def test_history_degenerate_nl(harness_factory) -> None:
    harness = harness_factory(clock=lambda: HISTORY_NOW)

    async def scenario() -> str:
        action = await harness.router.route(message("storico di un anno fa"))
        return action.kind

    assert asyncio.run(scenario()) == "ask_period"
    assert harness.gateway.last().startswith("Uso: /history")


def test_schedule_request_with_history_word_is_still_a_creation(harness_factory) -> None:
    harness = harness_factory(
        llm=FakeLLM(
            draft={
                "name": "promemoria",
                "instructions": "riassumi lo storico delle esecuzioni",
                "schedule": "ogni giorno alle 8",
                "recipients": [],
                "log_allowlist": [],
            }
        ),
        clock=lambda: HISTORY_NOW,
    )

    async def scenario() -> str:
        routing = asyncio.create_task(
            harness.router.route(
                message("storico delle esecuzioni ogni giorno alle 8")
            )
        )
        await approve(harness)
        action = await routing
        return action.kind

    assert asyncio.run(scenario()) == "created"


def test_help_lists_history(harness_factory) -> None:
    harness = harness_factory()

    async def scenario() -> None:
        await harness.router.route(message("/help"))

    asyncio.run(scenario())
    assert "/history [periodo] [compito]" in harness.gateway.last()
