"""Load real m0 functions with fake platform ports; never import GUI modules."""
import argparse
import ast
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


@pytest.fixture
def m0(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[1] / "tests/engine/m0_boot_check.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    functions = [x for x in tree.body if isinstance(x, ast.FunctionDef)]
    calls = {"archives": [], "seed": [], "closed": 0, "captures": 0}
    class CaptureError(Exception):
        pass
    class Stop:
        def set(self):
            calls["stopped"] = True
    def archive(session, name, **kwargs):
        calls["archives"].append(kwargs)
        return Stop()
    monkeypatch.setitem(sys.modules, "harness.shot_archive", SimpleNamespace(
        start_archiver=archive, hook_stdout_tee=lambda x: None))
    session = SimpleNamespace(pid=200, hwnd=300)
    def close():
        calls["closed"] += 1
    session.close = close
    def capture(hwnd):
        calls["captures"] += 1
        return 3, 2, b"pixels"
    env = {"argparse": argparse, "json": json, "os": os, "Path": Path, "sys": sys,
           "time": SimpleNamespace(sleep=lambda _: None), "HERE": tmp_path,
           "env_check": SimpleNamespace(print_preflight=lambda _: {}),
           "profile": SimpleNamespace(seed_profile=lambda *a, **kw: calls["seed"].append((a, kw))),
           "launcher": SimpleNamespace(launch=lambda **kw: session),
           "winutil": SimpleNamespace(capture_window=capture, CaptureError=CaptureError,
                                      save_capture_bmp=lambda p, cap: Path(p).write_bytes(b"BMP"))}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), "exec"), env)
    return env, calls


def test_explicit_output_isolated_and_report_records_facts(m0, tmp_path, monkeypatch):
    env, calls = m0
    out = tmp_path / "owned"
    monkeypatch.setattr(sys, "argv", ["m0_boot_check.py", "--datadir", str(tmp_path / "new-profile"),
                                      "--output-dir", str(out)])
    assert env["main"]() == 0
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["driver_pid"] == os.getpid() and report["app_pid"] == 200
    assert len(report["captures"]) == 3
    assert report["phases"][-2:] == ["close_requested", "closed"]
    assert calls["archives"] == [{"out_root": out / "shots"}]
    assert calls["closed"] == 1 and calls["stopped"]
    assert not (tmp_path / "artifacts/m0").exists()


def test_legacy_output_default_and_archive_location_unchanged(m0, tmp_path, monkeypatch):
    env, calls = m0
    monkeypatch.setattr(sys, "argv", ["m0_boot_check.py"])
    assert env["main"]() == 0
    assert (tmp_path / "artifacts/m0/startup_0.bmp").exists()
    assert calls["archives"] == [{}]


def test_run_owned_directory_cannot_reuse_previous_output(m0, tmp_path):
    env, _ = m0
    out = tmp_path / "owned"
    out.mkdir()
    (out / "report.json").write_text("old evidence", encoding="utf-8")
    with pytest.raises(ValueError, match="must be empty"):
        env["prepare_output"](out)


@pytest.mark.parametrize("fresh", [False, True])
def test_owned_output_never_enters_global_fresh_cleanup(m0, tmp_path, monkeypatch, fresh):
    env, calls = m0
    profile = tmp_path / "profile"
    argv = ["m0_boot_check.py", "--datadir", str(profile), "--output-dir", str(tmp_path / "out")]
    if fresh:
        argv.append("--fresh")
    else:
        profile.mkdir()
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit):
        env["main"]()
    assert calls["seed"] == []


def test_capture_failure_closes_session_and_records_incomplete_evidence(m0, tmp_path, monkeypatch):
    env, calls = m0
    def fail(_):
        raise env["winutil"].CaptureError("simulated failure")
    env["winutil"].capture_window = fail
    out = tmp_path / "out"
    monkeypatch.setattr(sys, "argv", ["m0_boot_check.py", "--datadir", str(tmp_path / "new-profile"),
                                      "--output-dir", str(out)])
    assert env["main"]() == 2
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert "captures_complete" not in report["phases"] and not report["captures"]
    assert calls["closed"] == 1
