"""Opt-in external process sampling with a single writer per Orca instance.

Schema 2 uses a monotonic sampling clock, byte counters and explicit run,
instance and process identities. Machine counters are available in standalone
diagnostics. Managed runs observe only the launched process and its children.
"""

from __future__ import annotations

from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar
import json
import math
import os
from pathlib import Path
import platform
import re
import sys
import threading
import time
import urllib.request
from uuid import uuid4

SCHEMA = 2
_PHASE = ContextVar("perf_launch_phase", default=("", None))
_IGNORED_VALUES = ("", "0", "false", "no")


def _stderr(message: str) -> None:
    print(f"[perf] {message}", file=sys.stderr)


def _mib(count):
    return None if count is None else round(count / 1048576, 3)


def gui_resources(pid: int) -> tuple[int | None, int | None]:
    if os.name != "nt":
        return None, None
    from .perf_win32 import Process
    try:
        process = Process(pid)
    except OSError:
        return None, None
    try:
        return process.resources()
    finally:
        process.close()


class GrafanaAnnotations:
    """Optional post-run export. The sampler never makes network requests."""

    def __init__(self, base_url: str, token: str = "", timeout_s: float = 2.0):
        self._url = base_url.rstrip("/") + "/api/annotations"
        self._token = token
        self._timeout_s = timeout_s
        self._warned = False

    def post(self, text: str, tags: list[str], t_start: float, t_end: float | None = None) -> bool:
        body = {"text": text, "tags": tags, "time": int(t_start * 1000)}
        if t_end is not None:
            body["timeEnd"] = int(t_end * 1000)
        try:
            request = urllib.request.Request(
                self._url, data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json"}, method="POST",
            )
            if self._token:
                request.add_header("Authorization", f"Bearer {self._token}")
            with urllib.request.urlopen(request, timeout=self._timeout_s) as response:
                return 200 <= response.status < 300
        except (OSError, ValueError):
            if not self._warned:
                _stderr("Grafana annotation export failed")
                self._warned = True
            return False


class PerfMonitor:
    def __init__(self, *, out_path: Path | str, targets: list[str] | None = None,
                 anchor_pid: int | None = None, anchor_alive=None, members=None,
                 interval_s: float = 0.5, include_children: bool = True,
                 use_psutil: bool = True, include_system: bool = True,
                 label: str = "", run_id: str | None = None,
                 instance_id: str | None = None, commit: str | None = None):
        if not math.isfinite(interval_s) or interval_s <= 0:
            raise ValueError("sampling interval must be finite and positive")
        self._out_path = Path(out_path)
        self._targets = tuple(t.lower().removesuffix(".exe") for t in (targets or []))
        if any(not target for target in self._targets):
            raise ValueError("target name must be nonempty")
        self._anchor_pid = anchor_pid
        self._anchor_alive = anchor_alive
        self._anchor_identity = None
        self._members = members
        self._interval_s = max(interval_s, 0.05)
        self._include_children = include_children
        self._use_psutil = use_psutil
        self._include_system = include_system
        self._label = label or self._out_path.stem
        self.run_id = run_id or uuid4().hex
        self.instance_id = instance_id or uuid4().hex
        self._commit = commit
        self._phase = ("", self.run_id)
        self._lock = threading.Lock()
        self._steps = deque(maxlen=256)
        self._step_drops = 0
        self._stop = threading.Event()
        self._timed_out = threading.Event()
        self._thread = None
        self._summary = None
        self._previous = {}
        self._tracked = {}
        self._pids = {}
        self._last_network = None
        self._net_total = None
        self._sys_count = 0
        self._errors = 0
        self._tick = 0

    def start(self, *, step: str | None = None, case_run_id: str | None = None) -> PerfMonitor:
        if self._thread is not None:
            raise RuntimeError("sample streams cannot restart")
        self._started = time.monotonic()
        self._wall_start = time.time()
        self._thread = threading.Thread(target=self._collect, name="perf-monitor", daemon=True)
        if step is not None:
            self.set_step(step, case_run_id)
        self._thread.start()
        return self

    def stop(self, timeout_s: float = 2.0) -> dict:
        """Request stop. The writer keeps ownership of its file during a timeout."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout_s)
            if self._thread.is_alive():
                self._timed_out.set()
                return {"ev": "summary", "status": "partial", "reason": "writer_timeout",
                        "label": self._label, "pids": {}}
        return self._summary or {"ev": "summary", "status": "unavailable",
                                 "label": self._label, "pids": {}}

    def set_step(self, name: str, case_run_id: str | None = None) -> None:
        with self._lock:
            if self._thread is None or self._stop.is_set():
                return
            self._phase = (name, case_run_id or self.run_id)
            self._enqueue({
                "ev": "step", "t": time.time(), "t_rel": time.monotonic() - self._started,
                "step": name, "case_run_id": self._phase[1],
            })

    def _enqueue(self, row: dict) -> None:
        if len(self._steps) == self._steps.maxlen:
            self._step_drops += 1
        self._steps.append(row)

    def measure(self, name: str, start: float, *, end: float | None = None,
                status: str = "observed", **details) -> None:
        """Record a driver measurement using monotonic timestamps, even across phases."""
        end = time.monotonic() if end is None else end
        with self._lock:
            if self._thread is not None and not self._stop.is_set():
                self._enqueue({"ev": "measurement", "name": name, "status": status,
                               "case_run_id": self._phase[1], "t_rel": end - self._started,
                               "start_rel": start - self._started,
                               "duration_ms": (end - start) * 1000 if status == "observed" else None,
                               **details})

    def __enter__(self) -> PerfMonitor:
        return self.start()

    @property
    def frame_csv_path(self) -> Path:
        return self._out_path.with_suffix(".frames.csv")

    def __exit__(self, *exc):
        self.stop()

    def _collect(self) -> None:
        psutil = None
        windows_process = None
        mode = "unavailable"
        reason = None
        try:
            if self._use_psutil:
                try:
                    import psutil
                except ImportError:
                    _stderr("psutil missing")
            if psutil is not None:
                mode = "psutil"
                if self._anchor_pid is not None:
                    try:
                        if self._anchor_running():
                            self._anchor_identity = psutil.Process(self._anchor_pid).create_time()
                        if not self._anchor_running():
                            self._anchor_identity = None
                    except psutil.Error:
                        pass
                    if self._anchor_identity is None:
                        reason = "anchor_unavailable"
            elif os.name == "nt" and self._anchor_pid is not None:
                from .perf_win32 import Process
                mode = "ctypes"
                if self._anchor_running():
                    try:
                        windows_process = Process(self._anchor_pid)
                    except OSError:
                        pass
                if windows_process is None:
                    reason = "anchor_unavailable"
            else:
                reason = "backend_unavailable"
            self._out_path.parent.mkdir(parents=True, exist_ok=True)
            with self._out_path.open("x", encoding="utf-8", newline="\n") as stream:
                def write(row):
                    stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
                write({
                    "ev": "meta", "schema": SCHEMA, "mode": mode, "t": self._wall_start,
                    "t_rel": 0.0, "run_id": self.run_id, "instance_id": self.instance_id,
                    "label": self._label, "interval_s": self._interval_s,
                    "targets": self._targets if self._anchor_pid is None else (),
                    "anchor_pid": self._anchor_pid, "worker": platform.node(),
                    "platform": sys.platform, "commit": self._commit,
                    "scope": ("owned_job_descendants" if self._members else "anchor_descendants")
                    if self._anchor_pid is not None and mode == "psutil"
                    else ("anchor_only" if self._anchor_pid is not None else "name_diagnostic"),
                    "system_scope": "worker" if self._include_system and psutil else None,
                })
                stream.flush()
                # Take an initial snapshot even when the caller stops immediately.
                while reason is None:
                    with self._lock:
                        steps = self._take_steps()
                        step, case_run_id = self._phase
                        now = time.monotonic()
                    for event in steps:
                        write(event)
                    tag = {"tick": self._tick, "t": time.time(), "t_rel": now - self._started,
                           "step": step, "case_run_id": case_run_id}
                    self._tick += 1
                    try:
                        if psutil is not None:
                            rows = self._psutil_rows(psutil, now, tag)
                        else:
                            owned = self._members is None or self._anchor_pid in self._members()
                            snapshot = windows_process.snapshot() if owned and self._anchor_running() else None
                            rows = self._ctypes_rows(snapshot, now, tag)
                        self._write_samples(write, rows, tag)
                        if psutil is not None and self._include_system:
                            write(self._system_row(psutil, now, tag))
                    except (OSError, RuntimeError) as error:
                        self._errors += 1
                        if self._errors == 1:
                            _stderr(f"sample failed: {type(error).__name__}")
                    stream.flush()
                    if self._anchor_alive is not None and not self._anchor_running() and not self._tracked:
                        break
                    if self._stop.wait(self._interval_s):
                        break
                with self._lock:
                    steps = self._take_steps()
                for event in steps:
                    write(event)
                summary = self._finish(reason)
                write(summary)
                stream.flush()
                self._summary = summary
        except Exception as error:
            _stderr(f"{self._label}: collector failed ({type(error).__name__})")
            self._summary = self._finish("collector_failed")
        finally:
            if windows_process is not None:
                windows_process.close()

    def _take_steps(self) -> list[dict]:
        steps = list(self._steps)
        self._steps.clear()
        return steps

    def _anchor_running(self) -> bool:
        return self._anchor_alive is None or self._anchor_alive()

    def _name_match(self, exe_name: str) -> bool:
        stem = exe_name.lower().removesuffix(".exe")
        return any(stem.startswith(target) for target in self._targets)

    def _psutil_rows(self, psutil, now, tag):
        candidates = {}
        membership = self._members() if self._members is not None else None

        def add(process, role):
            try:
                identity = process.create_time()
                candidates.setdefault(process.pid, (process, role, identity))
            except psutil.Error:
                pass

        if self._anchor_pid is None:
            roots = [p for p in psutil.process_iter(["name"])
                     if self._name_match(p.info.get("name") or "")]
            role = "target"
        else:
            roots = []
            role = "anchor"
            try:
                if self._anchor_running():
                    anchor = psutil.Process(self._anchor_pid)
                    if anchor.create_time() == self._anchor_identity:
                        roots.append(anchor)
            except psutil.Error:
                pass
        for root in roots:
            add(root, role)
            if self._include_children:
                try:
                    for child in root.children(recursive=True):
                        add(child, "child")
                except psutil.Error:
                    pass
        if membership is not None:
            # Include previously confirmed descendants after their parent exits.
            # Other processes in the Job can be driver or verifier work.
            for pid, (known_role, created) in self._tracked.items():
                if known_role != "child" or pid not in membership or pid in candidates:
                    continue
                try:
                    process = psutil.Process(pid)
                    if process.create_time() == created:
                        add(process, known_role)
                except psutil.Error:
                    pass
        rows = []
        for pid, (process, process_role, created) in candidates.items():
            if membership is not None and pid not in membership:
                continue
            try:
                with process.oneshot():
                    cpu = process.cpu_times()
                    memory = process.memory_info()
                    name = process.name()
                    threads = process.num_threads()
                    io = self._optional(psutil, process.io_counters) if hasattr(process, "io_counters") else None
                    handles = self._optional(psutil, process.num_handles) if hasattr(process, "num_handles") else None
                # Connection enumeration can be costly and platform-dependent.
                # Keep it in the standalone diagnostics that also collect host counters.
                connections = None
                if self._include_system:
                    method = getattr(process, "net_connections", None) or getattr(process, "connections", None)
                    connections = self._optional(psutil, method) if method else None
                gdi, user = gui_resources(pid)
                # Fresh identity read after metrics also covers a disappearing child.
                if psutil.Process(pid).create_time() != created:
                    continue
                rows.append(self._process_row(
                    pid, created, process_role, name, now, tag, cpu.user + cpu.system,
                    memory.rss, getattr(memory, "private", None), gdi, user,
                    threads=threads, read_bytes=getattr(io, "read_bytes", None),
                    write_bytes=getattr(io, "write_bytes", None),
                    handles=handles, peak_rss_bytes=getattr(memory, "peak_wset", None),
                    page_faults=getattr(memory, "num_page_faults", None),
                    conns=len(connections) if connections is not None else None,
                ))
            except psutil.Error:
                continue
        return rows

    @staticmethod
    def _optional(psutil, method):
        try:
            return method()
        except (psutil.Error, OSError, NotImplementedError):
            return None

    def _ctypes_rows(self, snapshot, now, tag):
        if snapshot is None:
            return []
        return [self._process_row(self._anchor_pid, role="anchor", name="", now=now,
                                  tag=tag, **snapshot)]

    def _process_row(self, pid, created, role, name, now, tag, cpu, rss, private, gdi, user,
                     **optional):
        identity = f"{pid}@{created}"
        phase = tag["case_run_id"], tag["step"]
        previous = self._previous.get(identity)
        self._previous[identity] = now, cpu, phase
        dt = cpu_pct = None
        if previous is not None and now > previous[0] and cpu >= previous[1] and phase == previous[2]:
            dt = now - previous[0]
            cpu_pct = (cpu - previous[1]) / dt * 100
        return {"ev": "proc", **tag, "pid": pid, "created": created, "process_id": identity,
                "role": role, "name": name, "cpu_pct": cpu_pct, "cpu_seconds": cpu,
                "cpu_dt_s": dt, "rss_bytes": rss, "private_bytes": private,
                "rss_mb": _mib(rss), "private_mb": _mib(private), "gdi": gdi,
                "user_obj": user, **optional}

    def _write_samples(self, write, rows, tag):
        current = {}
        for row in rows:
            pid = row["pid"]
            old = self._tracked.get(pid)
            current[pid] = (row["role"], row["created"])
            if old != current[pid]:
                write({"ev": "proc_new", **tag, "pid": pid, "role": row["role"],
                       "process_id": row["process_id"]})
            write(row)
            acc = self._pids.setdefault(row["process_id"], {"pid": pid, "name": row["name"],
                "role": row["role"], "samples": 0, "rss_max_mb": None})
            acc["samples"] += 1
            if row["rss_mb"] is not None:
                acc["rss_max_mb"] = max(acc["rss_max_mb"] or 0, row["rss_mb"])
        for pid, (role, created) in self._tracked.items():
            if current.get(pid) != (role, created):
                identity = f"{pid}@{created}"
                self._previous.pop(identity, None)
                write({"ev": "proc_gone", **tag, "pid": pid, "process_id": identity, "role": role})
        self._tracked = current

    def _system_row(self, psutil, now, tag):
        net = self._optional(psutil, psutil.net_io_counters)
        delta = None
        if net is not None and self._last_network is not None:
            dt = now - self._last_network[0]
            sent = net.bytes_sent - self._last_network[1]
            received = net.bytes_recv - self._last_network[2]
            if min(sent, received) >= 0 and dt > 0:
                delta = sent, received, dt
                old_sent, old_recv = self._net_total or (0, 0)
                self._net_total = old_sent + sent, old_recv + received
        self._last_network = (now, net.bytes_sent, net.bytes_recv) if net is not None else None
        self._sys_count += 1
        return {"ev": "sys", **tag, "cpu_pct": psutil.cpu_percent(None),
                "mem_avail_pct": 100 - psutil.virtual_memory().percent,
                "net_sent_bytes": delta[0] if delta else None,
                "net_recv_bytes": delta[1] if delta else None,
                "net_dt_s": delta[2] if delta else None}

    def _finish(self, reason):
        sent, recv = self._net_total or (None, None)
        if self._pids:
            status = "partial" if reason or self._errors or self._timed_out.is_set() or self._step_drops else "complete"
        else:
            status = "unavailable"
            reason = reason or "no_process_samples"
        return {"ev": "summary", "t": time.time(), "t_rel": time.monotonic() - self._started,
                "run_id": self.run_id,
                "instance_id": self.instance_id, "label": self._label, "status": status,
                "reason": reason, "tick_errors": self._errors, "step_drops": self._step_drops,
                "pids": self._pids, "sys": {"n": self._sys_count, "net_sent_bytes": sent,
                    "net_recv_bytes": recv, "net_sent_mb": _mib(sent), "net_recv_mb": _mib(recv)}}


def env_enabled(env=None) -> bool:
    settings = os.environ if env is None else env
    return settings.get("ORCA_BB_PERF", "").strip().lower() not in _IGNORED_VALUES


def configure_worker_env(env, context) -> None:
    """Bind a trusted v3 worker to its existing runtime identity and output."""
    if env_enabled(env):
        env["ORCA_BB_PERF_RUN_ID"] = context.run_id
        env["ORCA_BB_PERF_LABEL"] = context.contract.case_id
        env["ORCA_BB_PERF_OUT"] = env.get("ORCA_BB_PERF_BATCH_DIR") or str(context.artifact_dir / "perf")
        env["ORCA_BB_PERF_JOB"] = "1"


def resolve_out_path(label: str, instance_id: str | None = None) -> Path:
    output = os.environ.get("ORCA_BB_PERF_OUT")
    directory = Path(output) if output else Path(__file__).resolve().parents[1] / "artifacts" / "perf"
    if directory.suffix.lower() == ".jsonl":
        return directory
    safe_label = re.sub(r"[^A-Za-z0-9_-]+", "_", label)[:60] or "perf"
    return directory / f"{safe_label}__{instance_id or uuid4().hex}.jsonl"


@contextmanager
def launch_phase(name: str, case_run_id: str):
    token = _PHASE.set((name, case_run_id))
    try:
        yield
    finally:
        _PHASE.reset(token)


def attach_for_session(popen, exe: Path | str) -> PerfMonitor | None:
    if not env_enabled():
        return None
    label = os.environ.get("ORCA_BB_PERF_LABEL") or Path(exe).stem
    instance = uuid4().hex
    try:
        members = None
        if os.environ.get("ORCA_BB_PERF_JOB") == "1":
            from .win32_job import current_job_process_ids
            members = current_job_process_ids
        mon = PerfMonitor(anchor_pid=popen.pid, anchor_alive=lambda: popen.poll() is None,
                          out_path=resolve_out_path(label, instance),
                          label=label, instance_id=instance, include_system=False,
                          run_id=os.environ.get("ORCA_BB_PERF_RUN_ID"),
                          commit=os.environ.get("ORCA_BB_PERF_COMMIT"), members=members)
        name, case_run_id = _PHASE.get()
        mon.start(step=name or "startup", case_run_id=case_run_id)
    except Exception as error:
        _stderr(f"{label}: attach failed ({type(error).__name__})")
        return None
    _stderr(f"attached run={mon.run_id} instance={instance} out={mon._out_path}")
    return mon


def finish_session(session) -> None:
    monitor = getattr(session, "perf", None)
    if monitor is not None:
        session.perf = None
        try:
            summary = monitor.stop()
            _stderr(f"run={monitor.run_id} instance={monitor.instance_id} {summary['status']}")
        except Exception as error:
            _stderr(f"collector stop failed ({type(error).__name__})")


def set_step(name: str, *, monitor: PerfMonitor | None = None, case_run_id: str | None = None):
    if monitor is not None:
        monitor.set_step(name, case_run_id)
