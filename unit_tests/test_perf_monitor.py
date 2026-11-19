"""unit_tests/test_perf_monitor.py — pure tests for the metric sampler.

No GUI, no app: the monitor samples the pytest process itself (anchor-pid
mode in psutil mode with empty targets, and the ctypes fallback path). The
Grafana poster is tested against a monkeypatched urlopen — no network.
"""
import json
import os
import time

import psutil
import pytest

from harness import perf_monitor as pm
from tools import perf_report


def _rows(path) -> list[dict]:
    return [json.loads(l) for l in
            path.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_gui_resources_returns_ints_for_self():
    gdi, usr = pm.gui_resources(os.getpid())
    assert gdi is None or isinstance(gdi, int) and gdi >= 0
    assert usr is None or isinstance(usr, int) and usr >= 0


def test_name_match_stem_and_case_insensitive(tmp_path):
    m = pm.PerfMonitor(out_path=tmp_path / "x.jsonl",
                       targets=["Snapmaker-Orca.exe"])
    assert m._name_match("snapmaker-orca.EXE")   # exact stem, any case
    assert m._name_match("snapmaker-orca")       # stem without .exe
    # startswith is intentional: suffixed builds (snapmaker-orca_beta.exe)
    # belong to the same app family and must be captured
    assert m._name_match("snapmaker-orca-updater.EXE")
    assert not m._name_match("orca.exe")


def test_psutil_monitor_jsonl_schema_and_steps(tmp_path):
    out = tmp_path / "m.jsonl"
    mon = pm.PerfMonitor(targets=[], anchor_pid=os.getpid(),
                         include_children=False, out_path=out, interval_s=0.05)
    mon.start()
    time.sleep(0.25)
    mon.set_step("phase_b")
    time.sleep(0.25)
    summary = mon.stop()
    rows = _rows(out)

    assert rows[0]["ev"] == "meta" and rows[0]["schema"] == 1
    assert rows[0]["mode"] == "psutil"
    assert rows[-1]["ev"] == "summary"
    procs = [r for r in rows if r["ev"] == "proc"]
    own = [r for r in procs if r["pid"] == os.getpid()]
    assert own, "anchor pid must be sampled"
    for key in ("cpu_pct", "rss_mb", "private_mb", "gdi", "user_obj", "conns"):
        assert key in own[0]
    assert any(r["ev"] == "sys" for r in rows)
    steps = [r for r in rows if r["ev"] == "step"]
    assert steps and steps[-1]["step"] == "phase_b"
    assert any(r.get("step") == "phase_b" for r in procs), \
        "rows after the step boundary must carry the label"
    me = summary["pids"][str(os.getpid())]
    assert me["samples"] >= 2 and me["role"] == "anchor"
    assert me["rss_max_mb"] and me["rss_max_mb"] > 0


def test_ctypes_fallback_samples_anchor(tmp_path):
    if os.name != "nt":
        pytest.skip("ctypes fallback is Windows-only")
    out = tmp_path / "c.jsonl"
    mon = pm.PerfMonitor(targets=[], anchor_pid=os.getpid(),
                         out_path=out, interval_s=0.05, use_psutil=False)
    mon.start()
    time.sleep(0.25)
    summary = mon.stop()
    rows = _rows(out)
    assert rows[0]["mode"] == "ctypes"
    procs = [r for r in rows if r["ev"] == "proc"]
    assert len(procs) >= 2
    assert procs[0]["rss_mb"] is not None and procs[0]["rss_mb"] > 0
    assert str(os.getpid()) in summary["pids"]


def test_stop_is_idempotent_single_summary_row(tmp_path):
    out = tmp_path / "i.jsonl"
    mon = pm.PerfMonitor(targets=[], anchor_pid=os.getpid(), out_path=out,
                         interval_s=0.05)
    mon.start()
    time.sleep(0.12)
    s1 = mon.stop()
    s2 = mon.stop()
    assert s1["ev"] == "summary" and s2["ev"] == "summary"
    summaries = [r for r in _rows(out) if r["ev"] == "summary"]
    assert len(summaries) == 1


def test_grafana_post_builds_request(monkeypatch):
    captured = {}

    class FakeResp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["data"] = json.loads(req.data.decode("utf-8"))
        captured["auth"] = req.get_header("Authorization")
        return FakeResp()

    monkeypatch.setattr(pm.urllib.request, "urlopen", fake_urlopen)
    g = pm.GrafanaAnnotations("http://g:3000/", token="tk")
    assert g.post("step: x", ["t1", "step"], 1000.0, 1005.0) is True
    assert captured["url"] == "http://g:3000/api/annotations"
    assert captured["data"]["time"] == 1000000
    assert captured["data"]["timeEnd"] == 1005000
    assert captured["auth"] == "Bearer tk"


def test_grafana_failure_swallowed(monkeypatch):
    def boom(req, timeout=None):
        raise OSError("network down")

    monkeypatch.setattr(pm.urllib.request, "urlopen", boom)
    g = pm.GrafanaAnnotations("http://g:3000")
    assert g.post("x", ["t"], 1.0) is False  # must not raise


def test_set_step_noop_when_detached():
    prev, pm._ACTIVE = pm._ACTIVE, None
    try:
        pm.set_step("anything")  # must not raise
    finally:
        pm._ACTIVE = prev


def test_env_enabled_gate(monkeypatch):
    monkeypatch.delenv("ORCA_BB_PERF", raising=False)
    assert pm.env_enabled() is False
    for v in ("0", "false", "no", ""):
        monkeypatch.setenv("ORCA_BB_PERF", v)
        assert pm.env_enabled() is False
    monkeypatch.setenv("ORCA_BB_PERF", "1")
    assert pm.env_enabled() is True


def test_report_aggregates_pids_steps_and_net(tmp_path, capsys):
    p = tmp_path / "run.jsonl"
    lines = [
        {"ev": "meta", "label": "t", "mode": "psutil"},
        {"ev": "step", "t": 1.0, "step": "boot"},
        {"ev": "proc", "t": 1.1, "step": "boot", "pid": 10, "name": "a.exe",
         "role": "target", "cpu_pct": 10.0, "rss_mb": 50.0, "private_mb": 40.0,
         "threads": 3, "read_mb": 1.0, "write_mb": 2.0, "gdi": 5,
         "user_obj": 2, "conns": 1},
        {"ev": "proc", "t": 1.2, "step": "slice", "pid": 10, "name": "a.exe",
         "role": "target", "cpu_pct": 50.0, "rss_mb": 90.0, "private_mb": 100.0,
         "threads": 4, "read_mb": 2.0, "write_mb": 4.0, "gdi": 9,
         "user_obj": 3, "conns": 2},
        {"ev": "proc", "t": 1.1, "step": "boot", "pid": 11, "name": "cp.exe",
         "role": "child", "cpu_pct": 1.0, "rss_mb": 5.0, "private_mb": 4.0,
         "threads": 1, "read_mb": None, "write_mb": None, "gdi": None,
         "user_obj": None, "conns": None},
        {"ev": "sys", "t": 1.1, "step": "boot", "cpu_pct": 12.0,
         "mem_avail_pct": 40.0, "net_sent_kbps": 100.0, "net_recv_kbps": 500.0},
        {"ev": "sys", "t": 2.1, "step": "slice", "cpu_pct": 30.0,
         "mem_avail_pct": 39.0, "net_sent_kbps": 100.0, "net_recv_kbps": 500.0},
        {"ev": "summary", "t": 3.0, "label": "t", "pids": {}, "sys": {}},
    ]
    p.write_text("\n".join(json.dumps(l) for l in lines) + "\n", encoding="utf-8")
    rc = perf_report.main([str(p)])
    assert rc == 0
    s = json.loads(p.with_suffix(".summary.json").read_text(encoding="utf-8"))
    a10 = s["pids"]["10"]
    assert a10["samples"] == 2
    assert a10["cpu_max"] == 50.0
    assert a10["private_max_mb"] == 100.0
    assert a10["gdi_delta"] == 4
    assert set(s["steps"]) == {"boot", "slice"}
    assert s["steps"]["boot"]["samples"] == 2  # pid 10 + pid 11 both in boot
    assert s["steps"]["boot"]["cpu_avg"] == pytest.approx(5.5)
    assert s["sys"]["samples"] == 2
    # 100 kbps * 1 s = 100 kbit = 12.5 KB (report rounds to 3 decimals)
    assert s["sys"]["net_sent_mb"] == pytest.approx(100 * 1 / 8 / 1024, abs=1e-3)
    out = capsys.readouterr().out
    assert "PID" in out and "boot" in out
