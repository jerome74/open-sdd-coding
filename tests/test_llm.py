"""C-05: chiamate DeepSeek, retry, credenziali, tool call, troncamento."""

from __future__ import annotations

import json

import httpx
import pytest

from agente.config import DeepSeekConfig
from agente.errors import LLMCredentialsError, LLMError
from agente.llm import LLMClient


def _config(max_context_tokens: int = 1000) -> DeepSeekConfig:
    return DeepSeekConfig(
        model="deepseek-flash",
        api_base="https://api.deepseek.test/v1",
        api_key="secret-key",
        max_context_tokens=max_context_tokens,
    )


def _client(
    handler, *, sleeps=None, attempts: int = 3, on_credentials_error=None
) -> LLMClient:
    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport)
    return LLMClient(
        _config(),
        http_client=http,
        retry_attempts=attempts,
        retry_delay_s=60,
        sleep=(sleeps.append if sleeps is not None else (lambda _s: None)),
        on_credentials_error=on_credentials_error,
    )


def test_chat_returns_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "deepseek-flash"
        assert request.headers["Authorization"] == "Bearer secret-key"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "ciao"}}],
                "usage": {"total_tokens": 3},
            },
        )

    response = _client(handler).chat([{"role": "user", "content": "saluta"}])
    assert response.text == "ciao"
    assert response.usage["total_tokens"] == 3


def test_tool_calls_are_parsed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "function": {
                                        "name": "read_logs",
                                        "arguments": json.dumps({"path": "/tmp/a.log"}),
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
        )

    response = _client(handler).chat([{"role": "user", "content": "log"}])
    assert response.tool_calls[0].name == "read_logs"
    assert response.tool_calls[0].arguments == {"path": "/tmp/a.log"}


def test_transient_error_is_retried_three_times() -> None:
    sleeps: list[float] = []
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(503, json={"error": "down"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    response = _client(handler, sleeps=sleeps).chat([{"role": "user", "content": "x"}])
    assert response.text == "ok"
    assert len(calls) == 3
    assert sleeps == [60, 60]


def test_failure_after_three_attempts() -> None:
    sleeps: list[float] = []
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(500, json={"error": "down"})

    with pytest.raises(LLMError):
        _client(handler, sleeps=sleeps).chat([{"role": "user", "content": "x"}])
    assert len(calls) == 3
    assert sleeps == [60, 60]


def test_credentials_error_is_not_retried() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(401, json={"error": "invalid"})

    with pytest.raises(LLMCredentialsError):
        _client(handler).chat([{"role": "user", "content": "x"}])
    assert len(calls) == 1


def test_malformed_response_is_controlled() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    with pytest.raises(LLMError, match="malformata"):
        _client(handler).chat([{"role": "user", "content": "x"}])


def test_context_is_truncated_to_budget() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    messages = [{"role": "system", "content": "sistema"}]
    messages += [{"role": "user", "content": "x" * 4000} for _ in range(10)]
    response = _client(handler).chat(messages)
    assert response.truncated_messages > 0


def test_secret_never_appears_in_error_message() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid"})

    with pytest.raises(LLMCredentialsError) as excinfo:
        _client(handler).chat([{"role": "user", "content": "x"}])
    assert "secret-key" not in str(excinfo.value)


def test_credentials_error_calls_the_monitor() -> None:
    calls: list[tuple[int, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(402, json={"error": "insufficient balance"})

    with pytest.raises(LLMCredentialsError):
        _client(handler, on_credentials_error=lambda s, b: calls.append((s, b))).chat(
            [{"role": "user", "content": "x"}]
        )

    assert calls[0][0] == 402
    assert "insufficient balance" in calls[0][1]


def test_credentials_error_exposes_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": "forbidden"})

    with pytest.raises(LLMCredentialsError) as excinfo:
        _client(handler).chat([{"role": "user", "content": "x"}])

    assert excinfo.value.status == 403
