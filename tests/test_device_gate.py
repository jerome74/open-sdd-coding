"""Gate azioni e allowlist del Device Adapter (BR-2, BR-13)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from agente.device import DeviceAdapter
from agente.errors import DeviceError, GateError
from agente.tools import Tool, ToolRegistry, default_registry
from agente.errors import ToolPolicyError


class FakeRunner:
    def __init__(self, stdout: str = "{}") -> None:
        self.stdout = stdout
        self.calls: list[list[str]] = []

    def __call__(self, cmd, **kwargs):
        self.calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout=self.stdout, stderr="")


def test_battery_level_parses_termux_output() -> None:
    device = DeviceAdapter(runner=FakeRunner(json.dumps({"percentage": 42})))
    assert device.battery_level() == 42


def test_is_online_from_supplicant_state() -> None:
    online = DeviceAdapter(runner=FakeRunner(json.dumps({"supplicant_state": "COMPLETED"})))
    offline = DeviceAdapter(runner=FakeRunner(json.dumps({"supplicant_state": "DISCONNECTED"})))
    assert online.is_online() is True
    assert offline.is_online() is False


def test_missing_termux_api_is_explicit() -> None:
    def runner(cmd, **kwargs):
        raise FileNotFoundError(cmd[0])

    with pytest.raises(DeviceError, match="Termux:API"):
        DeviceAdapter(runner=runner).battery_level()


def test_run_command_requires_approval() -> None:
    runner = FakeRunner()
    device = DeviceAdapter(runner=runner)
    with pytest.raises(GateError):
        device.run_command(["ls"], approved=False)
    assert runner.calls == []
    device.run_command(["ls"], approved=True)
    assert runner.calls == [["ls"]]


def test_read_only_from_allowlist(tmp_path: Path) -> None:
    allowed = tmp_path / "logs"
    allowed.mkdir()
    log = allowed / "app.log"
    log.write_text("riga", encoding="utf-8")
    device = DeviceAdapter(runner=FakeRunner())

    assert device.read_file(log, [str(allowed)]) == "riga"
    with pytest.raises(GateError, match="allowlist"):
        device.read_file(tmp_path / "altro.log", [str(allowed)])


def test_write_and_delete_require_approval(tmp_path: Path) -> None:
    device = DeviceAdapter(runner=FakeRunner())
    target = tmp_path / "file.txt"
    with pytest.raises(GateError):
        device.write_file(target, "x", approved=False)
    device.write_file(target, "x", approved=True)
    assert target.read_text(encoding="utf-8") == "x"
    with pytest.raises(GateError):
        device.delete_file(target, approved=False)
    device.delete_file(target, approved=True)
    assert not target.exists()


def test_default_registry_marks_device_actions_as_gated() -> None:
    registry = default_registry(DeviceAdapter(runner=FakeRunner()))
    flags = {tool.name: (tool.read_only, tool.requires_approval) for tool in registry.tools()}
    assert flags["read_logs"] == (True, False)
    assert flags["run_command"] == (False, True)
    assert flags["write_file"] == (False, True)
    assert flags["delete_file"] == (False, True)


def test_registry_rejects_modifying_tool_without_gate() -> None:
    registry = ToolRegistry()
    with pytest.raises(ToolPolicyError):
        registry.register(Tool("pericoloso", "x", read_only=False, requires_approval=False))


def test_inspect_path_classifies_file_folder_and_missing(tmp_path: Path) -> None:
    folder = tmp_path / "logs"
    folder.mkdir()
    log = folder / "app.log"
    log.write_text("riga", encoding="utf-8")
    device = DeviceAdapter(runner=FakeRunner())

    info = device.inspect_path(log, [str(folder)])
    assert (info.exists, info.is_file, info.is_dir, info.size, info.readable) == (
        True,
        True,
        False,
        4,
        True,
    )
    assert device.inspect_path(folder, [str(folder)]).is_dir is True
    missing = device.inspect_path(folder / "assente.log", [str(folder)])
    assert missing.exists is False and missing.size == 0
    with pytest.raises(GateError, match="allowlist"):
        device.inspect_path(log, [str(tmp_path / "altro")])


def test_read_file_tail_enforces_the_allowlist(tmp_path: Path) -> None:
    folder = tmp_path / "logs"
    folder.mkdir()
    log = folder / "app.log"
    log.write_text("a" * 100 + "CODA", encoding="utf-8")
    device = DeviceAdapter(runner=FakeRunner())

    tail = device.read_file_tail(log, [str(folder)], max_chars=10)

    assert tail.text == "a" * 6 + "CODA"
    assert tail.size == 104
    assert tail.truncated is True
    with pytest.raises(GateError, match="allowlist"):
        device.read_file_tail(log, [str(tmp_path / "altro")], max_chars=10)


def test_list_files_is_not_recursive_and_counts(tmp_path: Path) -> None:
    folder = tmp_path / "logs"
    folder.mkdir()
    (folder / "b.log").write_text("x", encoding="utf-8")
    (folder / "a.log").write_text("x", encoding="utf-8")
    (folder / "sub").mkdir()
    (folder / "link.log").symlink_to(folder / "a.log")
    device = DeviceAdapter(runner=FakeRunner())

    listing = device.list_files(folder, [str(folder)], limit=1)

    assert [Path(item).name for item in listing.files] == ["a.log"]
    assert listing.skipped_dirs == 1
    assert listing.skipped_links == 1
    assert listing.truncated is True
