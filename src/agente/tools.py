"""C-08 Tool Registry — strumenti e policy di conferma.

Regola invariabile: uno strumento modificante deve richiedere approvazione; i
metadati contraddittori (read-only + approvazione) sono rifiutati alla
registrazione (spec 06, D1). Il registry fornisce gli schemi al modello; da
spec 06 l'esecuzione passa da C-27, che classifica e chiede conferma.

Contratto degli handler (spec 03, C-09): ``handler(context, arguments)`` per i
read-only e ``handler(context, arguments, approved=...)`` per i modificanti
(V-03). ``approved`` è keyword-only con default ``False``: un chiamante che lo
dimentica non esegue nulla.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from .device import DeviceAdapter
from .errors import (
    DeviceError,
    LogAccessError,
    SearchError,
    ToolPolicyError,
)
from .log_reader import MAX_ERROR_PAYLOAD_CHARS, LogReader
from .web_search import DEFAULT_RESULTS, format_results

logger = logging.getLogger("agente.tools")

ToolHandler = Callable[[Any, dict[str, Any]], Any]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    read_only: bool
    requires_approval: bool
    handler: ToolHandler | None = None
    parameters: dict[str, Any] = field(default_factory=dict)

    def schema(self) -> dict[str, Any]:
        """Schema OpenAI-compatible della funzione, per C-05."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
                or {"type": "object", "properties": {}},
            },
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if not tool.name:
            raise ToolPolicyError("strumento senza nome")
        if not tool.read_only and not tool.requires_approval:
            raise ToolPolicyError(
                f"strumento modificante senza approvazione: {tool.name}"
            )
        if tool.read_only and tool.requires_approval:
            # Metadati contraddittori: read-only non può richiedere conferma.
            # Il rifiuto alla registrazione è più restrittivo della conferma
            # (spec 06, D1/V-15).
            raise ToolPolicyError(
                f"metadati contraddittori: read_only con approvazione: {tool.name}"
            )
        if tool.name in self._tools:
            raise ToolPolicyError(f"strumento duplicato: {tool.name}")
        self._tools[tool.name] = tool

    def tools(self) -> list[Tool]:
        return [self._tools[name] for name in sorted(self._tools)]

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def __len__(self) -> int:
        return len(self._tools)


def default_registry(
    device: DeviceAdapter,
    *,
    search: Any = None,
    log_reader: LogReader | None = None,
) -> ToolRegistry:
    """Strumenti della fondazione, della ricerca web e del device.

    ``web_search`` è sempre registrato (D5): senza adapter risponde con un
    errore esplicito invece di sparire dal catalogo. ``read_logs`` passa da C-29
    (spec 07): accetta un file o una cartella autorizzata. Gli handler
    modificanti ricevono ``approved`` da C-27; il default ``False`` mantiene il
    fail-safe.
    """
    registry = ToolRegistry()
    reader = log_reader or LogReader(device)
    registry.register(
        Tool(
            name="read_logs",
            description=(
                "Legge un file o una cartella di log autorizzata dall'allowlist del compito"
            ),
            read_only=True,
            requires_approval=False,
            handler=lambda task, arguments: _read_logs(reader, task, arguments),
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Percorso assoluto del file o della cartella di log da leggere"
                        ),
                    }
                },
                "required": ["path"],
            },
        )
    )
    registry.register(
        Tool(
            name="run_command",
            description="Esegue un comando sul telefono",
            read_only=False,
            requires_approval=True,
            handler=lambda task, arguments, *, approved=False: device.run_command(
                arguments.get("cmd", []), approved=approved
            ),
            parameters={
                "type": "object",
                "properties": {"cmd": {"type": "array", "items": {"type": "string"}}},
                "required": ["cmd"],
            },
        )
    )
    registry.register(
        Tool(
            name="write_file",
            description="Scrive un file sul telefono",
            read_only=False,
            requires_approval=True,
            handler=lambda task, arguments, *, approved=False: device.write_file(
                arguments.get("path", ""),
                arguments.get("content", ""),
                approved=approved,
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        )
    )
    registry.register(
        Tool(
            name="delete_file",
            description="Cancella un file sul telefono",
            read_only=False,
            requires_approval=True,
            handler=lambda task, arguments, *, approved=False: device.delete_file(
                arguments.get("path", ""), approved=approved
            ),
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        )
    )
    registry.register(
        Tool(
            name="web_search",
            description=(
                "Cerca sul web e restituisce titolo, URL ed estratto dei risultati"
            ),
            read_only=True,
            requires_approval=False,
            handler=lambda context, arguments: _web_search(search, arguments),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Testo da cercare sul web",
                    },
                    "k": {
                        "type": "integer",
                        "description": (
                            f"Numero di risultati (default {DEFAULT_RESULTS}, max 10)"
                        ),
                    },
                },
                "required": ["query"],
            },
        )
    )
    return registry


def _web_search(search: Any, arguments: dict[str, Any]) -> str:
    if search is None:
        raise SearchError("ricerca web non configurata")
    query = arguments.get("query")
    if not isinstance(query, str) or not query.strip():
        raise SearchError("query di ricerca mancante")
    k = arguments.get("k", DEFAULT_RESULTS)
    return format_results(search.search(query, k))


def _read_logs(reader: LogReader, task: Any, arguments: dict[str, Any]) -> str:
    path = arguments.get("path")
    if not isinstance(path, str) or not path.strip():
        raise DeviceError("percorso mancante per read_logs")
    allowlist = getattr(task, "log_allowlist", ()) or ()
    content = reader.read([path], allowlist)
    if content.refused:
        payload = content.rendered
        if len(payload) > MAX_ERROR_PAYLOAD_CHARS:
            payload = payload[:MAX_ERROR_PAYLOAD_CHARS] + "\n[output troncato]"
        logger.warning(
            "lettura log rifiutata",
            extra={"paths": list(content.refused)},
        )
        raise LogAccessError(
            f"Percorsi non autorizzati: {', '.join(content.refused)}",
            refused=content.refused,
            rendered=payload,
        )
    return content.rendered
