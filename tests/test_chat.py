"""C-23: risposta, contesto, tool, permessi e rilettura (spec 05)."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from agente.chat import ChatHandler, ChatToolContext
from agente.chat_memory import ConversationMemory
from agente.gate import ActionGate
from agente.errors import LLMError, TelegramError
from agente.llm import LLMResponse, ToolCall
from agente.role_guard import Role
from agente.storage.db import Database
from agente.storage.repositories import Approval, Message, User, repositories
from agente.tools import Tool, ToolRegistry

ADMIN = 1
USER = 2
REVOKED = 3
CHAT = 7


class StubRoles:
    def __init__(self, role: Role = Role.AUTHORIZED, roles: dict[int, Role] | None = None) -> None:
        self._default = role
        self._roles = roles or {}

    def resolve_role(self, user_id: int) -> Role:
        return self._roles.get(user_id, self._default)


class FakeProgress:
    def __init__(self) -> None:
        self.events: list[tuple[str, int]] = []

    async def start(self, chat_id: int) -> None:
        self.events.append(("start", chat_id))

    async def finish(self, chat_id: int) -> None:
        self.events.append(("finish", chat_id))


class FakeGateway:
    def __init__(self, *, fail: bool = False) -> None:
        self.sent: list[tuple[int, str]] = []
        self.fail = fail

    async def send(self, chat_id: int, text: str) -> int:
        if self.fail:
            raise TelegramError("invio rifiutato")
        self.sent.append((chat_id, text))
        return len(self.sent)


class FakeLLM:
    def __init__(self, answers: list[object] | None = None) -> None:
        self.answers = list(answers or [])
        self.calls: list[list[dict]] = []
        self.tools_seen: list[object] = []

    def chat(self, messages, tools=None):
        self.calls.append([dict(item) for item in messages])
        self.tools_seen.append(tools)
        if not self.answers:
            return LLMResponse(text="risposta")
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


class FakeApprovals:
    def __init__(self, status: str = "approved") -> None:
        self.status = status
        self.requests: list[dict] = []

    async def request(self, **kwargs):
        self.requests.append(kwargs)
        return Approval(
            action=kwargs["action"],
            reason=kwargs["reason"],
            expires_at="2099-01-01T00:00:00+00:00",
            status=self.status,
        )

    def is_executable(self, approval: Approval) -> bool:
        return approval.status == "approved"


class SlowLLM:
    def __init__(self, delay: float = 0.05) -> None:
        self.delay = delay
        self.questions: list[str] = []

    def chat(self, messages, tools=None):
        time.sleep(self.delay)
        question = str(messages[-1]["content"])
        self.questions.append(question)
        return LLMResponse(text=f"risposta a {question}")


@pytest.fixture
def env(tmp_path: Path):
    db = Database(tmp_path / "chat.db")
    db.migrate()
    repos = repositories(db.connection)
    repos.users.upsert(User(telegram_id=USER, username="utente", state="accepted"))
    repos.users.upsert(User(telegram_id=REVOKED, username="revocato", state="revoked"))
    memory = ConversationMemory(
        repos.conversations, memory_hours=24, context_tokens=1000
    )

    def build(
        *,
        llm=None,
        role: Role = Role.AUTHORIZED,
        roles: dict[int, Role] | None = None,
        gateway=None,
        tools=None,
        progress=None,
        gate=None,
    ) -> ChatHandler:
        return ChatHandler(
            roles=StubRoles(role, roles),
            memory=memory,
            llm=llm or FakeLLM(),
            progress=progress or FakeProgress(),
            gateway=gateway or FakeGateway(),
            users=repos.users,
            tools=tools,
            admin_id=ADMIN,
            gate=gate,
        )

    yield memory, repos, build
    db.close()


def test_answer_is_sent_and_stored(env) -> None:
    memory, _repos, build = env
    gateway = FakeGateway()
    handler = build(llm=FakeLLM([LLMResponse(text="sereno")]), gateway=gateway)

    reply = asyncio.run(handler.handle(USER, CHAT, "che tempo fa?"))

    assert reply.kind == "answered"
    assert gateway.sent == [(CHAT, "sereno")]
    assert [(item.role, item.content) for item in memory.get_context(USER)] == [
        ("user", "che tempo fa?"),
        ("assistant", "sereno"),
    ]


def test_second_question_carries_the_previous_turn(env) -> None:
    _memory, _repos, build = env
    llm = FakeLLM([LLMResponse(text="prima"), LLMResponse(text="seconda")])
    handler = build(llm=llm)

    asyncio.run(handler.handle(USER, CHAT, "prima domanda"))
    asyncio.run(handler.handle(USER, CHAT, "e poi?"))

    second = llm.calls[1]
    assert {"role": "user", "content": "prima domanda"} in second
    assert {"role": "assistant", "content": "prima"} in second


def test_unknown_user_is_ignored(env) -> None:
    _memory, _repos, build = env
    gateway = FakeGateway()
    handler = build(role=Role.UNKNOWN, gateway=gateway)

    reply = asyncio.run(handler.handle(99, CHAT, "ciao"))

    assert reply.kind == "ignored"
    assert gateway.sent == []


def test_empty_question_is_ignored(env) -> None:
    _memory, _repos, build = env
    gateway = FakeGateway()
    handler = build(gateway=gateway)

    assert asyncio.run(handler.handle(USER, CHAT, "   ")).kind == "ignored"
    assert gateway.sent == []


def test_llm_failure_sends_a_message_and_stores_nothing(env) -> None:
    memory, _repos, build = env
    gateway = FakeGateway()
    handler = build(llm=FakeLLM([LLMError("down")]), gateway=gateway)

    reply = asyncio.run(handler.handle(USER, CHAT, "domanda"))

    assert reply.kind == "error"
    assert gateway.sent and "Non riesco a rispondere" in gateway.sent[0][1]
    assert memory.get_context(USER) == []


def test_progress_wraps_the_llm_call(env) -> None:
    _memory, _repos, build = env
    progress = FakeProgress()
    handler = build(progress=progress)

    asyncio.run(handler.handle(USER, CHAT, "domanda"))

    assert progress.events == [("start", CHAT), ("finish", CHAT)]


def test_telegram_failure_does_not_raise(env) -> None:
    _memory, _repos, build = env
    handler = build(gateway=FakeGateway(fail=True))

    reply = asyncio.run(handler.handle(USER, CHAT, "domanda"))

    assert reply.kind == "answered"


def test_modifying_tool_is_never_executed(env) -> None:
    _memory, _repos, build = env
    called: list[str] = []
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="run_command",
            description="esegue un comando",
            read_only=False,
            requires_approval=True,
            handler=lambda context, arguments: called.append("run"),
        )
    )
    llm = FakeLLM(
        [
            LLMResponse(
                text="",
                tool_calls=(ToolCall(id="1", name="run_command", arguments={"cmd": ["ls"]}),),
            ),
            LLMResponse(text="non posso eseguirlo"),
        ]
    )
    handler = build(llm=llm, tools=registry)

    reply = asyncio.run(handler.handle(USER, CHAT, "cancella un file"))

    assert called == []
    assert reply.kind == "answered"
    tool_messages = [item for item in llm.calls[1] if item["role"] == "tool"]
    assert tool_messages and "approvazione" in tool_messages[0]["content"]
    assert not llm.tools_seen[0]  # nessuno schema modificante esposto


def test_read_only_tool_output_reaches_the_model(env) -> None:
    _memory, _repos, build = env
    seen: list[ChatToolContext] = []
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="web_search",
            description="cerca sul web",
            read_only=True,
            requires_approval=False,
            handler=lambda context, arguments: seen.append(context) or "risultato web",
        )
    )
    llm = FakeLLM(
        [
            LLMResponse(
                text="",
                tool_calls=(ToolCall(id="1", name="web_search", arguments={"q": "x"}),),
            ),
            LLMResponse(text="ecco la risposta"),
        ]
    )
    handler = build(llm=llm, tools=registry)

    reply = asyncio.run(handler.handle(USER, CHAT, "cerca x"))

    assert reply.text == "ecco la risposta"
    assert seen and seen[0].user_id == USER and seen[0].log_allowlist == ()
    tool_messages = [item for item in llm.calls[1] if item["role"] == "tool"]
    assert tool_messages[0]["content"] == "risultato web"
    assert llm.tools_seen[0] and llm.tools_seen[0][0]["function"]["name"] == "web_search"


def test_unknown_tool_is_reported_to_the_model(env) -> None:
    _memory, _repos, build = env
    llm = FakeLLM(
        [
            LLMResponse(
                text="",
                tool_calls=(ToolCall(id="1", name="sconosciuto", arguments={}),),
            ),
            LLMResponse(text="risposta"),
        ]
    )
    handler = build(llm=llm, tools=ToolRegistry())

    asyncio.run(handler.handle(USER, CHAT, "domanda"))

    tool_messages = [item for item in llm.calls[1] if item["role"] == "tool"]
    assert "non disponibile" in tool_messages[0]["content"]


def test_system_prompt_follows_user_language(env) -> None:
    _memory, _repos, build = env
    llm = FakeLLM()
    handler = build(llm=llm)

    asyncio.run(handler.handle(USER, CHAT, "hello"))

    system = llm.calls[0][0]
    assert system["role"] == "system"
    assert "lingua dell'utente" in system["content"]


def test_two_questions_of_the_same_user_are_serialized(env) -> None:
    memory, _repos, build = env
    handler = build(llm=SlowLLM())

    async def scenario() -> None:
        await asyncio.gather(
            handler.handle(USER, CHAT, "prima"),
            handler.handle(USER, CHAT, "seconda"),
        )

    asyncio.run(scenario())

    assert [(item.role, item.content) for item in memory.get_context(USER)] == [
        ("user", "prima"),
        ("assistant", "risposta a prima"),
        ("user", "seconda"),
        ("assistant", "risposta a seconda"),
    ]


def test_reset_clears_the_conversation(env) -> None:
    memory, _repos, build = env
    gateway = FakeGateway()
    handler = build(gateway=gateway)
    asyncio.run(handler.handle(USER, CHAT, "domanda"))

    reply = asyncio.run(handler.reset(USER, CHAT))

    assert reply.kind == "reset"
    assert memory.get_context(USER) == []
    assert gateway.sent[-1] == (CHAT, "Conversazione azzerata.")


def test_reset_without_conversation_says_so(env) -> None:
    _memory, _repos, build = env
    gateway = FakeGateway()
    handler = build(gateway=gateway)

    asyncio.run(handler.reset(USER, CHAT))

    assert gateway.sent[-1] == (CHAT, "Nessuna conversazione da azzerare.")


def test_admin_reads_the_messages_of_an_authorized_user(env) -> None:
    memory, _repos, build = env
    gateway = FakeGateway()
    handler = build(role=Role.ADMIN, gateway=gateway)
    memory.append(USER, Message(user_id=USER, role="user", content="domanda utente"))
    memory.append(USER, Message(user_id=USER, role="assistant", content="risposta agente"))

    reply = asyncio.run(handler.transcript(ADMIN, CHAT, USER))

    assert reply.kind == "transcript"
    text = gateway.sent[-1][1]
    assert "Conversazione di 2" in text
    assert "domanda utente" in text and "risposta agente" in text


def test_authorized_user_cannot_read_chats(env) -> None:
    _memory, _repos, build = env
    gateway = FakeGateway()
    handler = build(role=Role.AUTHORIZED, gateway=gateway)

    reply = asyncio.run(handler.transcript(USER, CHAT, USER))

    assert reply.kind == "rejected"
    assert "Solo l'amministratore" in gateway.sent[-1][1]


def test_admin_cannot_read_an_unknown_or_revoked_user(env) -> None:
    _memory, _repos, build = env
    gateway = FakeGateway()
    handler = build(role=Role.ADMIN, gateway=gateway)

    asyncio.run(handler.transcript(ADMIN, CHAT, 99))
    assert "sconosciuto" in gateway.sent[-1][1].lower()

    asyncio.run(handler.transcript(ADMIN, CHAT, REVOKED))
    assert "sconosciuto" in gateway.sent[-1][1].lower()


def test_admin_read_without_messages(env) -> None:
    _memory, _repos, build = env
    gateway = FakeGateway()
    handler = build(role=Role.ADMIN, gateway=gateway)

    asyncio.run(handler.transcript(ADMIN, CHAT, USER))

    assert gateway.sent[-1] == (CHAT, "Nessun messaggio nelle ultime 24 ore.")


def test_list_authorized_users(env) -> None:
    _memory, _repos, build = env
    gateway = FakeGateway()
    handler = build(role=Role.ADMIN, gateway=gateway)

    asyncio.run(handler.list_authorized(ADMIN, CHAT))

    text = gateway.sent[-1][1]
    assert "Utenti autorizzati" in text
    assert "2 (utente)" in text
    assert "3" not in text  # revocato escluso


def test_reset_during_an_answer_does_not_resurrect_the_memory(env) -> None:
    """AC-03: un /reset mentre la risposta è in volo non lascia turni in memoria."""
    memory, _repos, build = env
    handler = build(llm=SlowLLM(delay=0.1))

    async def scenario() -> None:
        pending = asyncio.create_task(handler.handle(USER, CHAT, "domanda"))
        await asyncio.sleep(0.02)  # la richiesta è dentro llm.chat
        await handler.reset(USER, CHAT)
        await pending

    asyncio.run(scenario())

    assert memory.get_context(USER) == []


def test_web_search_tool_is_exposed_and_executed(env) -> None:
    _memory, _repos, build = env
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="web_search",
            description="cerca sul web",
            read_only=True,
            requires_approval=False,
            handler=lambda context, arguments: "risultato web",
        )
    )
    approvals = FakeApprovals()
    gate = ActionGate(registry, approvals)
    llm = FakeLLM(
        [
            LLMResponse(
                text="",
                tool_calls=(ToolCall(id="1", name="web_search", arguments={"query": "x"}),),
            ),
            LLMResponse(text="ecco la risposta"),
        ]
    )
    handler = build(llm=llm, tools=registry, gate=gate)

    reply = asyncio.run(handler.handle(USER, CHAT, "cerca x"))

    assert reply.text == "ecco la risposta"
    assert approvals.requests == []
    assert llm.tools_seen[0][0]["function"]["name"] == "web_search"


def test_modifying_tool_goes_through_the_gate(env) -> None:
    _memory, _repos, build = env
    called: list[bool] = []
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="delete_file",
            description="cancella",
            read_only=False,
            requires_approval=True,
            handler=lambda context, arguments, approved=False: (
                called.append(approved) or "cancellato"
            ),
        )
    )
    approvals = FakeApprovals()
    gate = ActionGate(registry, approvals)
    llm = FakeLLM(
        [
            LLMResponse(
                text="",
                tool_calls=(ToolCall(id="1", name="delete_file", arguments={"path": "/x"}),),
            ),
            LLMResponse(text="fatto"),
        ]
    )
    handler = build(llm=llm, tools=registry, gate=gate)

    reply = asyncio.run(handler.handle(USER, CHAT, "cancella /x"))

    assert reply.text == "fatto"
    assert called == [True]
    assert approvals.requests[0]["reason"] == "cancella /x"
    assert approvals.requests[0]["requester"] == USER
    assert llm.tools_seen[0][0]["function"]["name"] == "delete_file"


def test_log_reading_stays_refused_in_chat(env) -> None:
    from agente.errors import LogAccessError

    _memory, _repos, build = env
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="read_logs",
            description="legge",
            read_only=True,
            requires_approval=False,
            handler=lambda context, arguments: (_ for _ in ()).throw(
                LogAccessError(
                    "Percorsi non autorizzati: /tmp/x.log",
                    refused=("/tmp/x.log",),
                )
            ),
        )
    )
    gate = ActionGate(registry, FakeApprovals())
    llm = FakeLLM(
        [
            LLMResponse(
                text="",
                tool_calls=(ToolCall(id="1", name="read_logs", arguments={"path": "/tmp/x.log"}),),
            ),
            LLMResponse(text="non posso leggere quel file"),
        ]
    )
    handler = build(llm=llm, tools=registry, gate=gate)

    reply = asyncio.run(handler.handle(USER, CHAT, "leggi /tmp/x.log"))

    assert reply.text == "non posso leggere quel file"
    tool_message = next(
        message for message in llm.calls[1] if message.get("role") == "tool"
    )
    assert "non autorizzati" in tool_message["content"]


def test_real_read_logs_is_refused_in_chat(env) -> None:
    from agente.device import DeviceAdapter
    from agente.log_reader import LogReader
    from agente.tools import default_registry

    _memory, _repos, build = env
    device = DeviceAdapter()
    registry = default_registry(device, log_reader=LogReader(device))
    gate = ActionGate(registry, FakeApprovals())
    llm = FakeLLM(
        [
            LLMResponse(
                text="",
                tool_calls=(ToolCall(id="1", name="read_logs", arguments={"path": "/tmp/x.log"}),),
            ),
            LLMResponse(text="non posso leggere i log in chat"),
        ]
    )
    handler = build(llm=llm, tools=registry, gate=gate)

    reply = asyncio.run(handler.handle(USER, CHAT, "leggi /tmp/x.log"))

    assert reply.text == "non posso leggere i log in chat"
    tool_message = next(
        message for message in llm.calls[1] if message.get("role") == "tool"
    )
    assert "Percorsi non autorizzati: /tmp/x.log" in tool_message["content"]
