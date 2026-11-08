"""C-05 LLM Client — DeepSeek (API compatibile OpenAI).

Contesto troncato entro ``max_context_tokens`` (turni più recenti) e retry BR-8.
Nessun segreto nei log.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

import httpx

from .config import DeepSeekConfig
from .errors import LLMCredentialsError, LLMError
from .retry import retry_call

logger = logging.getLogger("agente.llm")

# Stima grezza: ~4 caratteri per token. Non è una misura del tokenizer reale,
# ma basta a tenere il contesto sotto il budget dichiarato dalla spec.
_CHARS_PER_TOKEN = 4
_SUMMARY_SYSTEM_PROMPT = "Riassumi il testo in modo conciso, in italiano."


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMResponse:
    text: str
    tool_calls: tuple[ToolCall, ...] = ()
    usage: dict[str, Any] = field(default_factory=dict)
    truncated_messages: int = 0


def assistant_message(response: LLMResponse) -> dict[str, Any]:
    """Messaggio ``assistant`` con eventuali tool call, per i loop di tool calling.

    Formato condiviso da C-09 (esecuzione) e C-23 (chat): il modello deve
    rivedere la propria richiesta di tool prima del messaggio ``tool``.
    """
    message: dict[str, Any] = {"role": "assistant", "content": response.text or ""}
    if response.tool_calls:
        message["tool_calls"] = [
            {
                "id": call.id or call.name,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": json.dumps(call.arguments, ensure_ascii=False),
                },
            }
            for call in response.tool_calls
        ]
    return message


class _RetryableLLMError(Exception):
    """Errore transitorio: rete, 429 o 5xx."""


class LLMClient:
    def __init__(
        self,
        config: DeepSeekConfig,
        *,
        http_client: httpx.Client | None = None,
        timeout_s: float = 30.0,
        retry_attempts: int = 3,
        retry_delay_s: float = 60.0,
        sleep: Callable[[float], None] = time.sleep,
        on_credentials_error: Callable[[int, str], bool] | None = None,
    ) -> None:
        self._config = config
        self._client = http_client or httpx.Client(timeout=timeout_s)
        self._retry_attempts = retry_attempts
        self._retry_delay_s = retry_delay_s
        self._sleep = sleep
        self._on_credentials_error = on_credentials_error

    def chat(
        self,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]] | None = None,
    ) -> LLMResponse:
        prepared, dropped = self._truncate(messages)
        payload: dict[str, Any] = {
            "model": self._config.model,
            "messages": prepared,
        }
        if tools:
            payload["tools"] = list(tools)

        try:
            response = retry_call(
                lambda: self._post(payload),
                attempts=self._retry_attempts,
                delay_s=self._retry_delay_s,
                retry_on=(_RetryableLLMError,),
                sleep=self._sleep,
            )
        except _RetryableLLMError as exc:
            logger.error("DeepSeek non disponibile dopo i retry")
            raise LLMError(f"DeepSeek non disponibile: {exc}") from exc

        parsed = self._parse(response)
        logger.info(
            "chiamata LLM completata",
            extra={
                "model": self._config.model,
                "tool_calls": len(parsed.tool_calls),
                "truncated_messages": dropped,
            },
        )
        return LLMResponse(
            text=parsed.text,
            tool_calls=parsed.tool_calls,
            usage=parsed.usage,
            truncated_messages=dropped,
        )

    def summarize(self, text: str) -> str:
        response = self.chat(
            [
                {"role": "system", "content": _SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ]
        )
        if not response.text.strip():
            raise LLMError("risposta di riassunto vuota")
        return response.text.strip()

    def _post(self, payload: Mapping[str, Any]) -> httpx.Response:
        url = f"{self._config.api_base.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._config.api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = self._client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise _RetryableLLMError(str(exc)) from exc

        status = response.status_code
        if status in (401, 402, 403):
            if self._on_credentials_error is not None:
                try:
                    self._on_credentials_error(status, response.text[:500])
                except Exception:  # noqa: BLE001 - l'avviso non maschera l'errore
                    logger.exception("callback credenziali fallita")
            raise LLMCredentialsError(
                f"credenziali DeepSeek non valide o credito esaurito (HTTP {status})",
                status=status,
            )
        if status == 429 or status >= 500:
            raise _RetryableLLMError(f"HTTP {status}")
        if status >= 400:
            raise LLMError(f"richiesta DeepSeek rifiutata (HTTP {status})")
        return response

    def _parse(self, response: httpx.Response) -> LLMResponse:
        try:
            data = response.json()
            message = data["choices"][0]["message"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError("risposta DeepSeek malformata") from exc

        text = message.get("content") or ""
        if not isinstance(text, str):
            raise LLMError("contenuto DeepSeek malformato")

        calls: list[ToolCall] = []
        for raw_call in message.get("tool_calls") or []:
            try:
                function = raw_call["function"]
                arguments = function.get("arguments") or "{}"
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
                calls.append(
                    ToolCall(
                        id=str(raw_call.get("id", "")),
                        name=str(function["name"]),
                        arguments=dict(arguments),
                    )
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise LLMError("tool call DeepSeek malformata") from exc

        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        return LLMResponse(text=text, tool_calls=tuple(calls), usage=usage)

    def _truncate(
        self, messages: Sequence[Mapping[str, Any]]
    ) -> tuple[list[Mapping[str, Any]], int]:
        budget = self._config.max_context_tokens
        prepared = list(messages)
        dropped = 0
        total = sum(_estimate_tokens(message) for message in prepared)
        while total > budget and len(prepared) > 1:
            index = 1 if _role(prepared[0]) == "system" else 0
            total -= _estimate_tokens(prepared.pop(index))
            dropped += 1
        return prepared, dropped


def _role(message: Mapping[str, Any]) -> str:
    return str(message.get("role", ""))


def _estimate_tokens(message: Mapping[str, Any]) -> int:
    content = message.get("content")
    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False, default=str)
    return max(1, len(content) // _CHARS_PER_TOKEN)
