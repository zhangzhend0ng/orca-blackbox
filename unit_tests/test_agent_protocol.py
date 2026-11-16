"""Pure mailbox/frame tests using a fake UI; no application is started."""
import json
from pathlib import Path
import struct
from types import SimpleNamespace
import zlib

import pytest

from harness import agent_guest as worker
from harness.agent_protocol import ProtocolError, check_cancel, read_json, validate_request, write_json_once
from harness.run_contract import validate_contract
from harness.run_verdict import contract_digest


def request(seq=1, method="observe", arguments=None, obs=None):
    return {"schema_version": 1, "run_id": "run1", "seq": seq, "method": method,
            "arguments": {} if arguments is None else arguments, "observation_id": obs}


@pytest.mark.parametrize("change", [
    {"seq": True}, {"schema_version": True}, {"run_id": "other"}, {"extra": 1},
    {"method": "shell"}, {"arguments": {"x": 40}}, {"observation_id": "stale"},
])
def test_request_fields_are_strict(change):
    value = request()
    value.update(change)
    with pytest.raises(ProtocolError):
        validate_request(value, run_id="run1", expected_seq=1, observation_id=None)


@pytest.mark.parametrize("x,y", [(39, 31), (313, 31), (40, 30), (40, 68), (True, 31), (40, 31.0)])
def test_clicks_cannot_escape_tab_region_or_use_coerced_types(x, y):
    with pytest.raises(ProtocolError):
        validate_request(request(2, "click", {"x": x, "y": y}, "previous"),
                         run_id="run1", expected_seq=2, observation_id="previous")


def test_click_boundary_and_fresh_observation_are_accepted():
    value = request(2, "click", {"x": 312, "y": 67}, "previous")
    assert validate_request(value, run_id="run1", expected_seq=2, observation_id="previous") == value
    with pytest.raises(ProtocolError, match="stale"):
        validate_request(value, run_id="run1", expected_seq=2, observation_id="new")


def test_mailbox_json_rejects_duplicates_and_does_not_replace(tmp_path):
    path = tmp_path / "message.json"
    path.write_text('{"seq":1,"seq":1}', encoding="utf-8")
    with pytest.raises(ProtocolError, match="duplicate"):
        read_json(path)
    with pytest.raises(FileExistsError):
        write_json_once(path, request())
    assert path.read_text() == '{"seq":1,"seq":1}'


def test_encoder_marks_bmp_top_down_and_png_preserves_rgb():
    pixels = bytes([10, 20, 30, 255]) * (313 * 68)
    bmp, png = worker._encode_capture((313, 68, pixels))
    assert struct.unpack_from("<ii", bmp, 18) == (313, -68)
    assert bmp[54:] == pixels
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    offset, image_data = 8, b""
    while offset < len(png):
        length = struct.unpack_from(">I", png, offset)[0]
        kind, data = png[offset + 4:offset + 8], png[offset + 8:offset + 8 + length]
        if kind == b"IDAT":
            image_data += data
        offset += length + 12
    row = b"\0" + bytes([30, 20, 10]) * 313
    assert zlib.decompress(image_data) == row * 68


def test_capture_width_must_include_rightmost_allowed_click():
    with pytest.raises(ProtocolError, match="invalid_capture"):
        worker._encode_capture((312, 68, bytes(312 * 68 * 4)))


@pytest.mark.parametrize("content,code", [
    ({"schema_version": 1, "run_id": "run1", "reason": "host_stopped"}, "host_cancelled"),
    ({"schema_version": True, "run_id": "run1", "reason": "host_stopped"}, "invalid_cancel"),
    ({"schema_version": 1, "run_id": "other", "reason": "host_stopped"}, "invalid_cancel"),
    ({"reason": "host_stopped"}, "invalid_cancel"),
])
def test_host_cancellation_valid_or_invalid_always_stops(tmp_path, content, code):
    write_json_once(tmp_path / "control_cancel.json", content)
    with pytest.raises(ProtocolError, match=code):
        check_cancel(tmp_path, "run1")


@pytest.mark.parametrize("flow", ["valid", "forbidden-click", "host-cancel", "invalid-cancel"])
def test_real_worker_loop_observes_clicks_finishes_with_run_owned_trace(tmp_path, monkeypatch, flow):
    contract = validate_contract({"schema_version": 1, "case_id": "m1_minimal_loop",
        "contract_version": "ai-tabs-1", "executor": "agent_mcp", "required_checks": ["path", "business"],
        "steps": [{"id": "tabs", "goal": "Switch tabs and return"}],
        "limits": {"timeout_s": 900, "max_actions": 12, "max_retries": 0, "max_cost_usd": 0}})
    (tmp_path / "contract.json").write_text(json.dumps(contract.to_dict()), encoding="utf-8")
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    now = [0.0]
    monkeypatch.setattr(worker, "time", SimpleNamespace(monotonic=lambda: now[0],
        time_ns=lambda: int(1e18 + now[0] * 1e9), sleep=lambda seconds: now.__setitem__(0, now[0] + seconds)))
    monkeypatch.setattr(worker.host_guard, "in_guest", lambda: True)
    instances = []
    class UI:
        def __init__(self, _artifacts):
            self.clicks, self.closed = [], False
            instances.append(self)
        def identity(self):
            return {"hwnd": 9, "pid": 8, "width": 313, "height": 68, "dpi": 96}, (
                313, 68, bytes([1, 2, 3, 255]) * (313 * 68))
        def click(self, x, y):
            self.clicks.append((x, y))
        def close(self):
            self.closed = True
    monkeypatch.setattr(worker, "_WindowsUI", UI)
    original_write = worker.write_json_once
    def write(path, value):
        original_write(path, value)
        if path.name == "ready.json":
            for value in [request(), request(2, "click", {"x": 313 if flow == "forbidden-click" else 100, "y": 50}, "run1_0001"),
                          request(3, "finish", obs="run1_0002")]:
                original_write(artifacts / "mailbox" / f"request_{value['seq']:04d}.json", value)
        if path.name == "response_0001.json" and flow in {"host-cancel", "invalid-cancel"}:
            original_write(artifacts / "control_cancel.json", {"schema_version": 1,
                "run_id": "run1" if flow == "host-cancel" else "other", "reason": "host_stopped"})
    monkeypatch.setattr(worker, "write_json_once", write)
    assert worker.run_guest(artifacts, "run1", contract_digest(contract)) == (0 if flow == "valid" else 1)
    report = read_json(artifacts / "agent_report.json")
    rows = [json.loads(line) for line in (artifacts / "trace.ndjson").read_text().splitlines()]
    if flow in {"host-cancel", "invalid-cancel"}:
        assert report["status"] == "failed" and report["calls"] == 1 and report["clicks"] == 0
        assert len(rows) == 1 and instances[0].clicks == [] and instances[0].closed
        assert (artifacts / "control_cancel.json").exists()
        assert not (artifacts / "mailbox/response_0002.json").exists()
        return
    if flow == "forbidden-click":
        assert report["status"] == "failed" and report["calls"] == 1 and report["clicks"] == 0
        assert len(rows) == 2 and rows[-1]["response"]["is_error"]
        assert instances[0].clicks == [] and instances[0].closed
        assert not (artifacts / "mailbox/response_0003.json").exists()
        return
    assert report["status"] == "completed" and report["calls"] == 3 and report["clicks"] == 1
    assert len(rows) == 3 and rows[-1]["response"]["finished"]
    for row in rows:
        frames = row["response"]["observation"]["frames"]
        assert frames[1]["captured_at_ns"] - frames[0]["captured_at_ns"] >= 1_000_000_000
        assert all((artifacts / frame["path"]).exists() for frame in frames)
    assert instances[0].clicks == [(100, 50)] and instances[0].closed
