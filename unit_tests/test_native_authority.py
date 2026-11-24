"""Exercise real dispatcher accounting with fake GUI ports, never host input."""
import asyncio
import json
from types import SimpleNamespace

import pytest

from harness.native_authority import AuthorityController
from runner.windows_mcp_bridge import authority_receipt

RUN = "a" * 32


class Guard:
    def __init__(self, root, error=None):
        self.root, self.error = root, error

    def check(self, name, args):
        self.arguments_validated = True
        if (self.root / "input_revoked").exists():
            raise ValueError("native_input_revoked")
        self.last_window = dict(app_pid=1, foreground_pid=1, target_pid=1,
            foreground_hwnd=10, target_hwnd=20, target_class="wxWindowNR")
        if self.error and name == "Type":
            raise ValueError(self.error)
        return self.last_window


def execute(controller, name, args, dispatched, *, error=False):
    async def dispatch():
        dispatched.append(name)
        return SimpleNamespace(is_error=error)
    return asyncio.run(controller.call(name, args, dispatch))


def test_fatal_refusal_durably_revokes_and_no_later_input_dispatches(tmp_path):
    guard = Guard(tmp_path, "native_target_not_owned")
    controller = AuthorityController(guard, tmp_path, RUN, recovery_enabled=True)
    dispatched = []
    assert execute(controller, "Type", {"text": "10"}, dispatched)[1]["decision"] == "fatal"
    guard.error = None
    assert execute(controller, "Click", {"loc": [10, 10]}, dispatched)[1]["decision"] == "fatal"
    assert dispatched == []
    assert (tmp_path / "input_revoked").exists()
    assert json.loads((tmp_path / "authority_abort.json").read_text())["error_code"] == "native_target_not_owned"


def test_bounded_refusal_observe_then_native_dispatch_and_independent_audit(tmp_path):
    from harness.native_recovery import audit_trace
    guard = Guard(tmp_path, "native_type_requires_owned_edit")
    controller = AuthorityController(guard, tmp_path, RUN, recovery_enabled=True)
    dispatched = []
    assert execute(controller, "Type", {"text": "0.24"}, dispatched)[1]["decision"] == "recoverable"
    assert not (tmp_path / "input_revoked").exists()
    execute(controller, "Screenshot", {}, dispatched)
    guard.error = None
    execute(controller, "Type", {"text": "0.24"}, dispatched)
    trace = [json.loads(line) for line in (tmp_path / "native_trace.ndjson").read_text().splitlines()]
    assert dispatched == ["Screenshot", "Type"]
    assert audit_trace(trace, RUN, enabled=True)["recoveries"] == 1


def test_diagnostic_refuses_only_first_guard_approved_numeric_edit(tmp_path):
    from harness.native_diagnostic_recovery import ERROR_CODE, PROTOCOL

    class EditGuard(Guard):
        def check(self, name, args):
            window = super().check(name, args)
            window["target_class"] = "Edit"
            return window

    controller = AuthorityController(EditGuard(tmp_path), tmp_path, RUN, diagnostic_enabled=True)
    dispatched = []
    assert execute(controller, "Type", {"text": "C:/owned.3mf"}, dispatched)[1]["decision"] == "completed"
    refusal = execute(controller, "Type", {"text": "0.24"}, dispatched)[1]
    assert (refusal["decision"], refusal["error_code"], refusal["dispatched"]) == ("recoverable", ERROR_CODE, False)
    assert refusal["recovery"]["protocol"] == PROTOCOL
    execute(controller, "Screenshot", {}, dispatched)
    execute(controller, "Type", {"text": "0.24"}, dispatched)
    assert dispatched == ["Type", "Screenshot", "Type"]
    trace = [json.loads(line) for line in (tmp_path / "native_trace.ndjson").read_text().splitlines()]
    assert trace[1]["window"]["target_class"] == "Edit"
    assert trace[1]["guard_allowed"] is True and trace[1]["diagnostic_injection"] is True
    assert not (tmp_path / "input_revoked").exists()


@pytest.mark.parametrize("action", ["Click", "Type", "Shortcut"])
def test_missing_new_observation_after_refusal_is_terminal(tmp_path, action):
    guard = Guard(tmp_path, "native_type_requires_owned_edit")
    controller = AuthorityController(guard, tmp_path, RUN, recovery_enabled=True)
    dispatched = []
    execute(controller, "Type", {"text": "10"}, dispatched)
    guard.error = None
    assert execute(controller, action, {"text": "10"}, dispatched)[1]["decision"] == "fatal"
    assert not dispatched


def test_original_tool_error_is_fatal_even_if_it_returns_normally(tmp_path):
    controller = AuthorityController(Guard(tmp_path), tmp_path, RUN, recovery_enabled=True)
    dispatched = []
    receipt = execute(controller, "Screenshot", {}, dispatched, error=True)[1]
    assert receipt["decision"] == "fatal" and receipt["dispatched"] is True
    assert (tmp_path / "input_revoked").exists()


def test_legacy_contract_does_not_gain_recovery(tmp_path):
    controller = AuthorityController(Guard(tmp_path, "native_type_requires_owned_edit"), tmp_path, RUN)
    assert execute(controller, "Type", {"text": "10"}, [])[1]["decision"] == "fatal"


def test_output_schema_fields_survive_authority_attachment():
    from harness.native_authority import attach_authority
    original = {"result": "Waited 0 seconds"}
    metadata = {"protocol": "native-authority-1"}
    assert attach_authority(original, metadata) == {**original, "authority": metadata}
    assert original == {"result": "Waited 0 seconds"}
    with pytest.raises(ValueError):
        attach_authority({"authority": "not ours"}, metadata)


def test_oversized_canvas_frame_stays_inline_at_original_coordinates():
    import base64
    import io
    import random
    from runner.windows_mcp_bridge import inline_canvas_observations, ZCODE_INLINE_TARGET

    Image = pytest.importorskip("PIL.Image")
    frame = Image.new("RGB", (1920, 1080), "white")
    noisy = Image.frombytes("RGB", (280, 240), random.Random(0).randbytes(280 * 240 * 3))
    frame.paste(noisy, (700, 440))
    raw = io.BytesIO()
    frame.save(raw, format="PNG")
    oversized = base64.b64encode(raw.getvalue()).decode("ascii")
    text = {"type": "text", "text": "Overview"}
    item = {"type": "image", "mimeType": "image/png", "data": oversized}
    result = {"content": [text, item], "structuredContent": {"authority": {"seq": 7}}}
    assert inline_canvas_observations(result) == [
        {"before_base64": len(oversized), "after_base64": len(item["data"]), "mime_type": "image/jpeg"},
    ]
    assert len(item["data"]) <= ZCODE_INLINE_TARGET
    assert result["content"][0] == text and result["structuredContent"]["authority"]["seq"] == 7
    with Image.open(io.BytesIO(base64.b64decode(item["data"]))) as observed:
        assert observed.format == "JPEG" and observed.size == frame.size
    assert inline_canvas_observations(result) == []


def test_journal_write_failure_stops_all_later_dispatches(tmp_path):
    (tmp_path / "native_trace.ndjson").mkdir()
    controller = AuthorityController(Guard(tmp_path), tmp_path, RUN)
    dispatched = []
    for _ in range(2):
        with pytest.raises(OSError):
            execute(controller, "Click", {"loc": [1, 1]}, dispatched)
    assert dispatched == ["Click"]
    assert controller.gate.fatal is True
    assert (tmp_path / "authority_abort.json").exists()


@pytest.mark.parametrize("fault", [None, "run_id", "contract_sha256", "scenario", "actor", "app_pid", "hwnd", "output_path"])
def test_scope_is_bound_to_canonical_contract_before_enabling_recovery(fault):
    from harness.native_authority import validate_scope
    from harness.native_save_session import native_contract
    from harness.run_verdict import contract_digest
    contract = native_contract("zcode", "recovery_owned_edit")
    digest = contract_digest(contract)
    scope = dict(run_id=RUN, contract_sha256=digest, scenario="recovery_owned_edit",
                 actor="zcode", app_pid=1, hwnd=2, output_path="C:/owned/0001.3mf")
    if fault:
        scope[fault] = True if fault in {"app_pid", "hwnd"} else "wrong"
    kwargs = dict(run_id=RUN, output_path="C:/owned/0001.3mf")
    manifest = dict(run_id=RUN, contract_sha256=digest)
    if fault:
        with pytest.raises(ValueError):
            validate_scope(scope, manifest, contract.to_dict(), **kwargs)
    else:
        assert validate_scope(scope, manifest, contract.to_dict(), **kwargs) is True


@pytest.mark.parametrize("fault", [None, "run_id", "seq", "tool", "isError", "dispatched", "missing"])
def test_sidecar_only_accepts_bound_guest_receipt(fault):
    receipt = dict(protocol="native-authority-1", run_id=RUN, seq=1,
                   tool="Screenshot", decision="completed", dispatched=True)
    result = dict(structuredContent={"authority": receipt}, isError=False)
    if fault == "missing":
        result["structuredContent"] = {}
    elif fault == "isError":
        result["isError"] = True
    elif fault:
        receipt[fault] = False if fault == "dispatched" else "wrong"
    response = {"result": result}
    request = {"params": {"name": "Screenshot"}}
    if fault:
        with pytest.raises(ValueError):
            authority_receipt(response, request, RUN, 1)
    else:
        assert authority_receipt(response, request, RUN, 1) == receipt



def test_server_reads_unicode_comparison_contract_as_utf8(tmp_path, monkeypatch):
    import json
    from pathlib import Path

    from harness.native_save_session import native_contract
    from harness.run_verdict import contract_digest
    from tools.native_save_server import load_scope

    run_id = "a" * 32
    scenario = "compare_276_quality"
    root = tmp_path / "artifacts"
    root.mkdir()
    contract = native_contract("zcode", scenario)
    digest = contract_digest(contract)
    manifest = dict(run_id=run_id, contract_sha256=digest)
    scope = dict(manifest, actor="zcode", scenario=scenario, app_pid=1, hwnd=2,
                 output_path=str(root / "projects/0001.3mf"))
    encoded = json.dumps(contract.to_dict(), ensure_ascii=False)
    assert "mm³/s" in encoded
    (root / "scope.json").write_text(json.dumps(scope), encoding="utf-8")
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "contract.json").write_text(encoded, encoding="utf-8")

    read_text = Path.read_text

    def legacy_windows_read(path, encoding=None, errors=None):
        return read_text(path, encoding=encoding or "cp1252", errors=errors)

    monkeypatch.setattr(Path, "read_text", legacy_windows_read)
    assert load_scope(root, run_id) == (scope, False)
