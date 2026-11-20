import csv

import pytest

from harness.native_frame_trace import CAPACITY, HEADER, RECORD, analyze


def _trace(path, *, complete=1, pid=42, dropped=0):
    frames = [
        (110, 115, 116, 1, 1, 0, 0),
        (116, 121, 122, 1, 1, 0, 0),
        (121, 124, 125, 0, 2, 1, 0),
        (124, 126, 127, 1, 1, 2, 0),
        (130, 140, 142, 1, 1, 0, 0),
        (145, 150, 151, 1, 1, 0, 0),
    ]
    path.write_bytes(HEADER.pack(b"ORCAFRM1", HEADER.size, RECORD.size, pid, complete, 1000, CAPACITY,
                                 len(frames), dropped, 0) + b"".join(RECORD.pack(*row) for row in frames))


def _events():
    return [
        {"name": "render_clock_sync", "artifact": "run.render.bin",
         "qpc_hz": 1000, "qpc": 100, "start_rel": .1, "t_rel": .1},
        {"name": "render_activity", "activity": "zoom", "qpc_hz": 1000,
         "qpc_start": 110, "qpc_end": 150, "inputs": 5},
    ]


def test_trace_uses_owned_identity_and_qpc_activity_window(tmp_path):
    jsonl = tmp_path / "run.jsonl"
    _trace(jsonl.with_suffix(".render.bin"))
    result = analyze(jsonl, _events(), 42, write_csv=True)
    assert result["status"] == "observed" and result["frames"] == 6
    activity = result["activities"][0]
    preview = activity["streams"]["preview:1"]
    assert preview["frames"] == 3 and preview["failed_swaps"] == 1
    assert preview["submitted_fps"] == 80
    assert preview["frame_interval_ms"]["p95"] == 19
    assert preview["render_before_swap_ms"]["p95"] == 10
    assert preview["swap_call_ms"]["p95"] == 2
    assert activity["streams"]["prepare:2"]["submitted_fps"] is None
    with jsonl.with_suffix(".render.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert float(rows[0]["t_rel"]) == pytest.approx(.115)
    assert rows[3]["swap_succeeded"] == "0"


def test_partial_trace_does_not_become_complete(tmp_path):
    path = tmp_path / "run.jsonl"
    _trace(path.with_suffix(".render.bin"), complete=0, dropped=8)
    result = analyze(path, _events(), 42)
    assert result["status"] == "partial" and result["dropped"] == 8


def test_trace_rejects_missing_or_foreign_trace(tmp_path):
    path = tmp_path / "run.jsonl"
    result = analyze(path, _events(), 42)
    assert result["reason"] == "native_trace_missing"
    _trace(path.with_suffix(".render.bin"), pid=99)
    result = analyze(path, _events(), 42)
    assert "process identity" in result["reason"]
