"""unit_tests/test_perf_monitor.py — pure tests for the metric sampler.

No GUI, no app: the monitor samples the pytest process itself (anchor-pid
mode in psutil mode with empty targets, and the ctypes fallback path). The
Grafana poster is tested against a monkeypatched urlopen — no network.
"""
import json
import os
import sys
import threading
import time
from contextlib import nullcontext
from types import SimpleNamespace

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
    pytest.importorskip("psutil")
    out = tmp_path / "m.jsonl"
    mon = pm.PerfMonitor(targets=[], anchor_pid=os.getpid(),
                         include_children=False, out_path=out, interval_s=0.05)
    mon.start(step="startup", case_run_id="case_a")
    time.sleep(0.25)
    mon.set_step("phase_b")
    time.sleep(0.25)
    summary = mon.stop()
    rows = _rows(out)

    assert rows[0]["ev"] == "meta" and rows[0]["schema"] == 2
    assert rows[0]["mode"] == "psutil"
    assert rows[-1]["ev"] == "summary"
    procs = [r for r in rows if r["ev"] == "proc"]
    own = [r for r in procs if r["pid"] == os.getpid()]
    assert own, "anchor pid must be sampled"
    assert (own[0]["step"], own[0]["case_run_id"]) == ("startup", "case_a")
    for key in ("cpu_pct", "rss_mb", "private_mb", "gdi", "user_obj", "conns"):
        assert key in own[0]
    assert any(r["ev"] == "sys" for r in rows)
    steps = [r for r in rows if r["ev"] == "step"]
    assert steps and steps[-1]["step"] == "phase_b"
    assert any(r.get("step") == "phase_b" for r in procs), \
        "rows after the step boundary must carry the label"
    me, = summary["pids"].values()
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
    assert {proc["pid"] for proc in summary["pids"].values()} == {os.getpid()}


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
    pm.set_step("anything")  # must not raise


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
    assert s["sys"]["net_sent_mb"] == pytest.approx(100 * 1000 / (8 * 1048576), abs=1e-3)
    out = capsys.readouterr().out
    assert "PID" in out and "boot" in out


def test_managed_scope_ignores_same_name_and_pid_reuse(monkeypatch, tmp_path):
    members = {101, 102, 201}
    processes = {}

    def add_process(pid, creation, child_pids=()):
        processes[pid] = SimpleNamespace(
            pid=pid, name=lambda: "snapmaker-orca.exe", create_time=lambda: creation,
            oneshot=nullcontext, children=lambda recursive: [processes[p] for p in child_pids],
            cpu_times=lambda: SimpleNamespace(user=1.0, system=0.0),
            memory_info=lambda: SimpleNamespace(rss=10),
            num_threads=lambda: 1,
        )

    add_process(101, 10, (102, 103))
    add_process(102, 11)
    add_process(103, 12)  # Descendant outside the owned Job.
    add_process(201, 13)  # Same name in the Job, unrelated to the app tree.
    backend = SimpleNamespace(Process=processes.__getitem__, Error=KeyError,
        process_iter=lambda *args: pytest.fail("managed run enumerated global names"))
    monkeypatch.setattr(pm, "gui_resources", lambda pid: (None, None))
    mon = pm.PerfMonitor(out_path=tmp_path / "owned.jsonl", targets=["snapmaker-orca"],
                         anchor_pid=101, members=lambda: members)
    mon._anchor_identity = 10
    tag = {"tick": 0, "step": "open", "case_run_id": mon.run_id}
    rows = mon._psutil_rows(backend, 2.0, tag)
    assert {(r["pid"], r["role"]) for r in rows} == {(101, "anchor"), (102, "child")}
    mon._write_samples(lambda row: None, rows, tag)
    add_process(101, 20)
    rows = mon._psutil_rows(backend, 3.0, {**tag, "tick": 1})
    assert [r["pid"] for r in rows] == [102]


def test_invalid_output_keeps_session_and_existing_file(monkeypatch, tmp_path):
    original = tmp_path / "original.jsonl"
    original.write_text("previous evidence", encoding="utf-8")
    monkeypatch.setenv("ORCA_BB_PERF", "1")
    monkeypatch.setenv("ORCA_BB_PERF_OUT", str(original))
    session = SimpleNamespace(perf=pm.attach_for_session(
        SimpleNamespace(pid=os.getpid(), poll=lambda: None), "orca.exe"))
    assert session.perf is not None
    assert session.perf.stop()["status"] == "unavailable"
    pm.finish_session(session)
    assert session.perf is None
    assert original.read_text(encoding="utf-8") == "previous evidence"


def test_stop_times_out_without_taking_writer_ownership(monkeypatch, tmp_path):
    started = threading.Event()
    release = threading.Event()
    mon = pm.PerfMonitor(out_path=tmp_path / "wait.jsonl")

    def collect():
        started.set()
        release.wait(3)

    monkeypatch.setattr(mon, "_collect", collect)
    mon.start()
    try:
        assert started.wait(1)
        assert mon.stop(timeout_s=0.01)["reason"] == "writer_timeout"
        assert mon._thread.is_alive()
    finally:
        release.set()
        mon.stop()


def test_schema_two_weights_steps_and_preserves_absence():
    meta = {"ev": "meta", "schema": 2, "run_id": "run", "instance_id": "app"}
    rows = [meta]
    for tick, duration, cpu in [(1, 0.5, 100), (2, 1, 40)]:
        for pid, load in [(101, cpu), (102, 0)]:
            rows.append({"ev": "proc", "pid": pid, "process_id": f"{pid}@1", "tick": tick,
                         "case_run_id": "child", "step": "slice", "cpu_pct": load,
                         "cpu_dt_s": duration})
    rows.append({"ev": "sys", "net_sent_bytes": 1048576, "net_recv_bytes": 0})
    partial = perf_report.summarize(rows)
    assert partial["status"] == "partial"
    assert partial["steps"]["child/slice"]["cpu_avg"] == 60.0
    assert partial["steps"]["child/slice"]["private_max_mb"] is None
    assert partial["sys"]["net_sent_mb"] == 1
    assert partial["sys"]["net_recv_mb"] == 0
    assert perf_report.summarize([meta])["sys"]["net_sent_mb"] is None


def test_monitor_handles_no_network_and_keeps_system_samples(tmp_path):
    backend = SimpleNamespace(net_io_counters=lambda: None,
        cpu_percent=lambda _: 12, virtual_memory=lambda: SimpleNamespace(percent=34), Error=OSError)
    mon = pm.PerfMonitor(out_path=tmp_path / "network.jsonl")
    row = mon._system_row(backend, 1, {"tick": 1})
    assert row["cpu_pct"] == 12
    assert row["net_sent_bytes"] is None


def test_measurements_keep_missing_values_and_same_process_idle_baseline():
    meta = {"ev": "meta", "schema": 2, "run_id": "run", "instance_id": "app", "anchor_pid": 10}
    rows = [meta]
    for cycle, rss in ((0, 20), (1, 23)):
        for offset in (.2, .7):
            rows.append({"ev": "proc", "pid": 10, "process_id": "10@1",
                         "t_rel": cycle * 3 + offset, "step": "soak_idle", "rss_mb": rss,
                         "read_bytes": 100 + cycle * 20, "handles": 3})
        rows.append({"ev": "measurement", "name": "soak_idle", "status": "observed",
                     "cycle": cycle, "start_rel": cycle * 3, "t_rel": cycle * 3 + 1,
                     "duration_ms": 1000})
    rows.append({"ev": "measurement", "name": "slice_click_to_completion_detected",
                 "status": "not_observed", "duration_ms": None})
    summary = perf_report.summarize(rows)
    delta = summary["soak_checkpoints"][1]["delta_from_baseline"]
    assert delta["rss_mb"] == 3 and delta["private_mb"] is None and delta["handles"] == 0
    assert summary["measurements"]["slice_click_to_completion_detected"]["duration_ms"] is None
    assert summary["pids"]["10@1"]["counter_deltas"]["read_bytes"] == 20
    assert summary["pids"]["10@1"]["counter_deltas"]["write_bytes"] is None


def test_presentmon_csv_filters_pid_window_and_separates_swapchains(tmp_path):
    from harness import perf_frames

    path = tmp_path / "app.frames.csv"
    path.write_text(
        "ProcessID,SwapChainAddress,CPUStartQPC,DisplayedTime,MsGPUBusy,MsCPUBusy,DisplayLatency\n"
        "99,a,105,600,600,1,900\n"
        "10,a,105,20,5,2,25\n"
        "10,a,110,NA,6,2,NA\n"
        "10,a,115,40,8,3,30\n"
        "10,a,125,300,4,2,32\n"
        "10,b,150,16,NA,1,NA\n"
        "10,b,160,16,NA,1,NA\n", encoding="utf-8",
    )
    frames = perf_frames.read_frames(path, 10)
    result = perf_frames.frame_metrics(frames, 100, 130)
    assert result["status"] == "observed"
    assert result["metrics"]["displayed_frame_ms"]["max"] == 40
    assert result["metrics"]["displayed_fps"] == pytest.approx(1000 / 30)
    assert result["metrics"]["dropped_frames"] == 1
    assert result["metrics"]["dropped_frame_pct"] == 25
    assert result["metrics"]["slow_frame_pct"]["over_33.3333_ms"] == 50
    assert result["metrics"]["display_latency_ms"]["p50"] == 30
    assert perf_frames.frame_metrics(frames, 100, 180)["status"] == "ambiguous_swapchain"
    assert perf_frames.frame_metrics(frames, 1, 30)["metrics"] is None


def test_import_without_win32_dll(monkeypatch):
    import subprocess

    code = ("import ctypes; " +
            ("del ctypes.WinDLL; " if os.name == "nt" else "") +
            "from harness import perf_monitor")
    p = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr


@pytest.mark.skipif(os.name != "nt", reason="Windows session lifecycle")
def test_session_monitor_records_unexpected_exit_without_losing_terminal_event(tmp_path, monkeypatch):
    import subprocess
    from harness.launcher import AppSession

    path = tmp_path / "exit.jsonl"
    monkeypatch.setenv("ORCA_BB_PERF", "1")
    monkeypatch.setenv("ORCA_BB_PERF_OUT", str(path))
    monkeypatch.delenv("ORCA_BB_PERF_JOB", raising=False)
    with subprocess.Popen([sys.executable, "-B", "-c", "import time; time.sleep(.3); raise SystemExit(27)"]) as process:
        session = AppSession(process, 0)
        session.perf = pm.attach_for_session(process, sys.executable, finish_on_anchor_exit=False)
        assert process.wait(timeout=5) == 27
        session.close()
    result = perf_report.summarize(perf_report.load_rows(path))
    event = result["measurements"]["close_request_to_exit"]["events"][0]
    assert event["status"] == "unexpected_exit" and event["exit_code"] == 27
    assert event["duration_ms"] is None


@pytest.mark.skipif(os.name != "nt", reason="Windows Job integration")
def test_two_owned_workers_capture_only_their_process_tree(tmp_path):
    psutil = pytest.importorskip("psutil")
    from pathlib import Path
    from uuid import uuid4

    from harness.win32_job import OwnedJobProcess

    script = """\
import subprocess
import sys
import time
from harness.perf_monitor import attach_for_session

target = subprocess.Popen([sys.executable, "-B", "-c", "import time; time.sleep(60)"])
monitor = attach_for_session(target, "snapmaker-orca.exe")
try:
    time.sleep(60)
finally:
    target.terminate()
    target.wait()
    monitor.stop()
"""
    # Windows venv launchers create an extra process. This test needs
    # exactly one worker and one target in each Job.
    worker_python = sys._base_executable
    worker_env = os.environ.copy()
    import_paths = [str(Path(psutil.__file__).resolve().parents[1])]
    if worker_env.get("PYTHONPATH"):
        import_paths.append(worker_env["PYTHONPATH"])
    worker_env["PYTHONPATH"] = os.pathsep.join(import_paths)
    workers = []
    try:
        for label in ("a", "b"):
            output = tmp_path / f"{label}.jsonl"
            owned = OwnedJobProcess.start([worker_python, "-B", "-c", script],
                cwd=Path.cwd(), log_path=tmp_path / f"{label}.log",
                env={**worker_env, "ORCA_BB_PERF": "1", "ORCA_BB_PERF_JOB": "1",
                     "ORCA_BB_PERF_RUN_ID": uuid4().hex, "ORCA_BB_PERF_OUT": str(output)})
            workers.append((owned, output))
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            rows = [perf_report.load_rows(path) if path.is_file() else [] for _, path in workers]
            if all(any(r["ev"] == "proc" for r in stream) for stream in rows):
                break
            time.sleep(0.05)
        else:
            pytest.fail("\n".join(path.with_suffix(".log").read_text() for _, path in workers))
        for stream in rows:
            assert {r["pid"] for r in stream if r["ev"] == "proc"} == {stream[0]["anchor_pid"]}
            assert stream[0]["scope"] == "owned_job_descendants"
        assert rows[0][0]["anchor_pid"] != rows[1][0]["anchor_pid"]
        workers[0][0].terminate()
        assert workers[1][0].poll() == (None, 2)
    finally:
        for worker, _ in workers:
            if worker.poll()[1]:
                worker.terminate()
            deadline = time.monotonic() + 5
            while worker.poll()[1] and time.monotonic() < deadline:
                time.sleep(0.05)
            worker.close()
