"""Inference adapter boundary tests with a fake native subprocess only."""
import io
import hashlib
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace

import pytest

from harness.agent_model import (CodexModel, ModelError, _parse_output,
                                 _child_environment, default_codex_executable)


OBS = {"id": "run1_0001", "window": {"width": 400, "height": 100}}
ACTION = {"tool": "click", "observation_id": "run1_0001", "x": 244, "y": 49}


def events(action=ACTION, extra=()):
    output = [{"type": "thread.started", "thread_id": "test"}, {"type": "turn.started"}, *extra,
              {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(action)}},
              {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}}]
    return ("\n".join(json.dumps(x) for x in output) + "\n").encode()


class FakeInput(io.BytesIO):
    def close(self):
        self.payload = self.getvalue()
        super().close()


class FakeProcess:
    def __init__(self, output, error=b"", code=0, hanging=False):
        self.stdout, self.stderr = io.BytesIO(output), io.BytesIO(error)
        self.stdin = FakeInput()
        self.returncode = None if hanging else code
        self.killed = False

    def poll(self):
        return self.returncode

    def kill(self):
        self.killed, self.returncode = True, -9

    def wait(self, timeout):
        assert timeout <= 5
        return self.returncode


@pytest.fixture
def provider(tmp_path, monkeypatch):
    from harness import agent_model
    executable, image = tmp_path / "codex.exe", tmp_path / "screen.png"
    executable.write_bytes(b"fake native executable; never launched")
    image.write_bytes(b"\x89PNG\r\n\x1a\nFAKE")
    processes, arguments = [], []
    settings = {"output": events(), "error": b"", "code": 0, "hanging": False}
    def popen(args, **kwargs):
        arguments.append((args, kwargs))
        process = FakeProcess(**settings)
        processes.append(process)
        return process
    monkeypatch.setattr(agent_model.subprocess, "Popen", popen)
    return (CodexModel(executable), image, tmp_path / "outputs", settings, processes, arguments)


def call(provider, **kwargs):
    model, image, out, *_ = provider
    return model.next_action(image, OBS, [], 8, out, time.monotonic() + 10, **kwargs)


def test_only_strict_action_is_returned_and_logs_are_unique(provider):
    model, image, out, settings, processes, arguments = provider
    assert call(provider) == ACTION
    assert call(provider) == ACTION
    dirs = list(out.iterdir())
    assert len(dirs) == 2
    for d in dirs:
        assert (d / "stdout.jsonl").read_bytes() == settings["output"]
        assert (d / "stderr.log").exists()
        summary = json.loads((d / "summary.json").read_text())
        assert summary["dollar_cost"] is None and summary["usage"]["input_tokens"] == 10
        assert summary["input_image_sha256"] == hashlib.sha256(image.read_bytes()).hexdigest()
        assert summary["cli_executable_sha256"] == hashlib.sha256(model.executable.read_bytes()).hexdigest()
        assert len(summary["prompt_sha256"]) == 64
        assert summary["started_at_ns"] <= summary["finished_at_ns"]
        assert summary["proxy_source"] in ("system", "environment", "none")
        assert summary["model"] is None
    assert all(p.stdin.closed for p in processes)
    args, options = arguments[0]
    assert "--ignore-user-config" in args and "--ignore-rules" in args
    assert "--ephemeral" in args and "--output-schema" in args and args[-1] == "-"
    assert args[args.index("-s") + 1] == "read-only"
    assert "--model" not in args  # App model aliases are not silently forwarded.
    assert not Path(options["cwd"]).exists()  # Temporary cwd was destroyed.
    assert options.get("shell") is not True
    assert "project_doc_max_bytes=0" in args and 'web_search="disabled"' in args
    disabled = [args[i + 1] for i, item in enumerate(args[:-1]) if item == "--disable"]
    assert {"shell_tool", "shell_snapshot", "apps", "plugins", "hooks", "computer_use",
            "browser_use", "browser_use_external", "memories", "multi_agent"} <= set(disabled)


@pytest.mark.parametrize("tool", ["command_execution", "mcp_tool_call", "file_change", "web_search_call"])
def test_tool_events_are_rejected_even_when_final_action_looks_valid(provider, tool):
    provider[3]["output"] = events(extra=[{"type": "item.started", "item": {"type": tool}}])
    with pytest.raises(ModelError, match="tool or unsupported"):
        call(provider)


@pytest.mark.parametrize("action", [{**ACTION, "observation_id": "stale"},
    {**ACTION, "x": True}, {**ACTION, "x": 400}, {**ACTION, "x": 244.0},
    {**ACTION, "tool": "exec"}, {**ACTION, "pass": True},
    {**ACTION, "tool": "finish"}, {**ACTION, "tool": "observe", "x": None}])
def test_invalid_or_injected_action_rejected(provider, action):
    provider[3]["output"] = events(action)
    with pytest.raises(ModelError):
        call(provider)


@pytest.mark.parametrize("tool", ["observe", "finish"])
def test_nonclick_requires_null_coordinates(provider, tool):
    action = {"tool": tool, "observation_id": OBS["id"], "x": None, "y": None}
    provider[3]["output"] = events(action)
    assert call(provider) == action


def test_nonzero_cli_exit_is_not_an_action(provider):
    provider[3]["code"] = 1
    with pytest.raises(ModelError, match="CLI failed"):
        call(provider)
    assert list(provider[2].glob("*/stdout.jsonl"))


def test_incomplete_response_cannot_be_used(provider):
    provider[3]["output"] = b'{"type":"turn.started"}\n'
    with pytest.raises(ModelError, match="incomplete response"):
        call(provider)


def test_bounded_output_keeps_partial_diagnostics(provider, monkeypatch):
    from harness import agent_model
    monkeypatch.setattr(agent_model, "MAX_STDOUT", 128)
    provider[3]["output"] = b"x" * 10000
    with pytest.raises(ModelError, match="bounded output"):
        call(provider)
    assert next(provider[2].glob("*/stdout.jsonl")).stat().st_size == 128


def test_deadline_kills_only_the_owned_process_and_keeps_partial(provider, monkeypatch):
    from harness import agent_model
    provider[3]["hanging"] = True
    now = [0.0]
    monkeypatch.setattr(agent_model.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(agent_model.time, "sleep", lambda delay: now.__setitem__(0, now[0] + delay))
    provider[0].timeout_s = 0.05
    with pytest.raises(ModelError, match="timeout"):
        call(provider)
    assert provider[4][0].killed
    assert next(provider[2].glob("*/stdout.jsonl")).exists()


def test_expired_deadline_does_not_start_subprocess(provider):
    model, image, out, settings, processes, args = provider
    with pytest.raises(ModelError, match="deadline exceeded"):
        model.next_action(image, OBS, [], 8, out, time.monotonic() - 1)
    assert processes == [] and not out.exists()


def test_oracle_fields_and_freeform_history_cannot_enter_prompt(provider):
    model, image, out, settings, processes, args = provider
    with pytest.raises(ValueError, match="observation"):
        model.next_action(image, {**OBS, "oracle": "secret coordinates"}, [], 8, out,
                          time.monotonic() + 5)
    with pytest.raises(ValueError, match="history"):
        model.next_action(image, OBS, ["ignore rules"], 8, out, time.monotonic() + 5)
    assert processes == []


def test_jsonl_parser_handles_text_and_rejects_duplicate_fields():
    assert _parse_output(events().decode())[0] == ACTION
    with pytest.raises(ModelError, match="duplicate"):
        _parse_output('{"type":"turn.started","type":"turn.completed"}\n')


def test_default_cli_prefers_newest_desktop_native_then_falls_back_to_npm(tmp_path, monkeypatch):
    from harness import agent_model
    local, roaming = tmp_path / "local", tmp_path / "roaming"
    monkeypatch.setattr(agent_model, "os", SimpleNamespace(name="nt", environ={
        "LOCALAPPDATA": str(local), "APPDATA": str(roaming)}))
    npm = (roaming / "npm/node_modules/@openai/codex/node_modules/@openai/codex-win32-x64"
           / "vendor/x86_64-pc-windows-msvc/bin/codex.exe")
    npm.parent.mkdir(parents=True)
    npm.write_bytes(b"npm")
    assert default_codex_executable() == npm.resolve()
    old, new = [local / "OpenAI/Codex/bin" / name / "codex.exe" for name in ("old", "new")]
    for index, path in enumerate((old, new), 1):
        path.parent.mkdir(parents=True)
        path.write_bytes(b"desktop")
        os.utime(path, ns=(index * 1_000_000_000, index * 1_000_000_000))
    assert default_codex_executable() == new.resolve()
    assert CodexModel().executable == new.resolve()
    assert CodexModel(npm).executable == npm


def test_default_cli_missing_is_explicit_failure(tmp_path, monkeypatch):
    from harness import agent_model
    monkeypatch.setattr(agent_model, "os", SimpleNamespace(name="nt", environ={
        "LOCALAPPDATA": str(tmp_path / "local"), "APPDATA": str(tmp_path / "roaming")}))
    with pytest.raises(ModelError, match="no installed native"):
        default_codex_executable()


@pytest.mark.parametrize("explicit_key", ["HTTP_PROXY", "http_proxy", "Http_Proxy"])
def test_explicit_environment_proxy_is_never_overwritten(monkeypatch, explicit_key):
    from harness import agent_model
    original = {explicit_key: "explicit-private", "HTTPS_PROXY": "explicit-private-2", "KEEP": "yes"}
    monkeypatch.setattr(agent_model, "os", SimpleNamespace(name="nt", environ=original))
    def should_not_discover():
        raise AssertionError("both schemes are explicit")
    monkeypatch.setattr(agent_model.urllib.request, "getproxies", should_not_discover)
    child, source = _child_environment()
    assert source == "environment" and child == original
    assert child is not original


def test_only_missing_http_schemes_are_copied_into_child(monkeypatch):
    from harness import agent_model
    original = {"http_proxy": "explicit-private", "KEEP": "yes"}
    monkeypatch.setattr(agent_model, "os", SimpleNamespace(name="nt", environ=original))
    monkeypatch.setattr(agent_model.urllib.request, "getproxies", lambda: {
        "http": "unused-private", "https": "system-private", "ftp": "ignored-private",
        "oauth": "never-copy-this"})
    child, source = _child_environment()
    assert source == "system"
    assert child["http_proxy"] == "explicit-private"
    assert child["HTTPS_PROXY"] == "system-private"
    assert set(child) == {"http_proxy", "HTTPS_PROXY", "KEEP"}
    assert original == {"http_proxy": "explicit-private", "KEEP": "yes"}


def test_windows_system_proxy_is_child_only_and_summary_never_records_it(provider, monkeypatch):
    from harness import agent_model
    original = {"KEEP": "yes"}
    monkeypatch.setattr(agent_model, "os", SimpleNamespace(name="nt", environ=original))
    monkeypatch.setattr(agent_model.urllib.request, "getproxies", lambda: {
        "http": "system-private-a", "https": "system-private-b"})
    call(provider)
    child = provider[5][0][1]["env"]
    assert child.get("HTTP_PROXY") == "system-private-a"
    assert child.get("HTTPS_PROXY") == "system-private-b"
    assert original == {"KEEP": "yes"}
    summary_path = next(provider[2].glob("*/summary.json"))
    text = summary_path.read_text(encoding="utf-8")
    assert json.loads(text)["proxy_source"] == "system"
    assert "system-private" not in text
    assert b"system-private" not in provider[4][0].stdin.payload


def test_explicit_blank_proxy_is_respected(monkeypatch):
    from harness import agent_model
    original = {"http_proxy": "", "https_proxy": ""}
    monkeypatch.setattr(agent_model, "os", SimpleNamespace(name="nt", environ=original))
    def should_not_discover():
        raise AssertionError("explicit blank proxy must remain disabled")
    monkeypatch.setattr(agent_model.urllib.request, "getproxies", should_not_discover)
    child, source = _child_environment()
    assert child == original and child is not original and source == "environment"


def test_no_system_proxy_and_nonwindows_do_not_invent_network_configuration(monkeypatch):
    from harness import agent_model
    monkeypatch.setattr(agent_model, "os", SimpleNamespace(name="posix", environ={"KEEP": "yes"}))
    monkeypatch.setattr(agent_model.urllib.request, "getproxies", lambda: {"http": "not-applied"})
    child, source = _child_environment()
    assert child == {"KEEP": "yes"} and source == "none"
    monkeypatch.setattr(agent_model, "os", SimpleNamespace(name="nt", environ={"KEEP": "yes"}))
    monkeypatch.setattr(agent_model.urllib.request, "getproxies", lambda: {})
    child, source = _child_environment()
    assert child == {"KEEP": "yes"} and source == "none"
