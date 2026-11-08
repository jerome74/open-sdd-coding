"""C-08: registrazione, metadati, schema di web_search (spec 06)."""

from __future__ import annotations

import subprocess

import pytest

from agente.device import DeviceAdapter
from agente.errors import SearchError, ToolPolicyError
from agente.tools import Tool, ToolRegistry, default_registry
from agente.web_search import Result


class FakeRunner:
    def __call__(self, cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr="")


class FakeSearch:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def search(self, query: str, k: int):
        self.calls.append((query, k))
        return [Result("Titolo", "https://example.test", "Estratto")]


def device() -> DeviceAdapter:
    return DeviceAdapter(runner=FakeRunner())


def test_default_registry_registers_web_search() -> None:
    registry = default_registry(device())

    tool = registry.get("web_search")
    assert tool is not None
    assert tool.read_only is True
    assert tool.requires_approval is False


def test_web_search_schema_is_declared() -> None:
    tool = default_registry(device()).get("web_search")
    assert tool is not None
    parameters = tool.schema()["function"]["parameters"]

    assert parameters["type"] == "object"
    assert parameters["required"] == ["query"]
    assert parameters["properties"]["query"]["type"] == "string"
    assert parameters["properties"]["k"]["type"] == "integer"


def test_web_search_without_adapter_raises_an_explicit_error() -> None:
    tool = default_registry(device()).get("web_search")
    assert tool is not None and tool.handler is not None

    with pytest.raises(SearchError, match="non configurata"):
        tool.handler(None, {"query": "meteo"})


def test_web_search_uses_the_adapter_and_formats_results() -> None:
    search = FakeSearch()
    tool = default_registry(device(), search=search).get("web_search")
    assert tool is not None and tool.handler is not None

    output = tool.handler(None, {"query": "meteo", "k": 3})

    assert search.calls == [("meteo", 3)]
    assert "1. Titolo — https://example.test" in output
    assert "Estratto" in output


def test_web_search_rejects_a_missing_query() -> None:
    tool = default_registry(device(), search=FakeSearch()).get("web_search")
    assert tool is not None and tool.handler is not None

    with pytest.raises(SearchError, match="mancante"):
        tool.handler(None, {})


def test_contradictory_metadata_is_rejected() -> None:
    registry = ToolRegistry()

    with pytest.raises(ToolPolicyError, match="contraddittori"):
        registry.register(
            Tool(
                name="strano",
                description="x",
                read_only=True,
                requires_approval=True,
            )
        )


def test_modifying_tool_without_approval_is_rejected() -> None:
    registry = ToolRegistry()

    with pytest.raises(ToolPolicyError, match="senza approvazione"):
        registry.register(
            Tool(
                name="strano",
                description="x",
                read_only=False,
                requires_approval=False,
            )
        )


def test_device_handlers_receive_approved() -> None:
    registry = default_registry(device())
    tool = registry.get("run_command")
    assert tool is not None and tool.handler is not None

    # Senza approvazione il Device Adapter rifiuta (fail-safe).
    from agente.errors import GateError

    with pytest.raises(GateError):
        tool.handler(None, {"cmd": ["ls"]}, approved=False)
    result = tool.handler(None, {"cmd": ["ls"]}, approved=True)
    assert result.returncode == 0


def _task(*paths: str):
    from agente.storage.repositories import Task

    return Task(
        name="log",
        instructions="riassumi",
        schedule_type="orario",
        schedule_expr="08:00",
        log_allowlist=list(paths),
    )


def test_read_logs_accepts_a_folder(tmp_path) -> None:
    folder = tmp_path / "logs"
    folder.mkdir()
    (folder / "app.log").write_text("ERROR: guasto", encoding="utf-8")
    tool = default_registry(device()).get("read_logs")
    assert tool is not None and tool.handler is not None

    output = tool.handler(_task(str(folder)), {"path": str(folder)})

    assert "ERROR: guasto" in output
    assert "== " in output


def test_read_logs_schema_mentions_a_folder() -> None:
    tool = default_registry(device()).get("read_logs")
    assert tool is not None

    assert "cartella" in tool.description
    parameters = tool.schema()["function"]["parameters"]
    assert parameters["required"] == ["path"]
    assert "cartella" in parameters["properties"]["path"]["description"]


def test_read_logs_refusal_raises_an_explicit_error(tmp_path) -> None:
    from agente.errors import LogAccessError

    folder = tmp_path / "logs"
    folder.mkdir()
    outside = tmp_path / "segreto.log"
    outside.write_text("x", encoding="utf-8")
    tool = default_registry(device()).get("read_logs")
    assert tool is not None and tool.handler is not None

    with pytest.raises(LogAccessError) as caught:
        tool.handler(_task(str(folder)), {"path": str(outside)})

    assert caught.value.refused == (str(outside),)
    assert "PERCORSO NON AUTORIZZATO" in caught.value.rendered


def test_default_registry_accepts_an_injected_reader(tmp_path) -> None:
    from agente.log_reader import LogContent

    class FakeReader:
        def __init__(self) -> None:
            self.calls: list[tuple[list[str], tuple[str, ...]]] = []

        def read(self, paths, allowlist):
            self.calls.append((list(paths), tuple(allowlist)))
            return LogContent((), (), (), "contenuto finto")

    reader = FakeReader()
    tool = default_registry(device(), log_reader=reader).get("read_logs")
    assert tool is not None and tool.handler is not None

    assert tool.handler(_task("/tmp"), {"path": "/tmp/x.log"}) == "contenuto finto"
    assert reader.calls == [(["/tmp/x.log"], ("/tmp",))]


def test_refusal_payload_is_capped() -> None:
    from agente.errors import LogAccessError
    from agente.log_reader import MAX_ERROR_PAYLOAD_CHARS, LogContent

    class HugeReader:
        def read(self, paths, allowlist):
            return LogContent((), ("/segreto",), (), "x" * 20_000)

    tool = default_registry(device(), log_reader=HugeReader()).get("read_logs")
    assert tool is not None and tool.handler is not None

    with pytest.raises(LogAccessError) as caught:
        tool.handler(_task("/tmp"), {"path": "/segreto"})

    suffix = "\n[output troncato]"
    assert len(caught.value.rendered) == MAX_ERROR_PAYLOAD_CHARS + len(suffix)
    assert MAX_ERROR_PAYLOAD_CHARS == 20_000 - 200
