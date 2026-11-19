# perf_monitor.py — process/host metric sampler attached to a black-box run.
#
# Observes the app-under-test from OUTSIDE only (README boundary: upstream
# source is read-only). Samples per-process CPU/memory/threads/IO/connections
# plus GDI/USER handle counts and host-wide CPU/memory/network counters, and
# appends one JSON object per line to a run-local jsonl file. Case code can
# mark step boundaries via set_step() (module-level no-op when nothing is
# attached); each boundary is optionally mirrored to a Grafana annotations
# endpoint (ORCA_BB_GRAFANA_URL/TOKEN) so metric charts and case steps share
# one timeline.
#
# Zero-dependency discipline: importing this module is stdlib-only; psutil is
# imported lazily and without it the sampler degrades to a ctypes single-pid
# mode (GetProcessTimes / K32GetProcessMemoryInfo / GetGuiResources). All
# diagnostics go to stderr — never stdout (mcp_server owns stdout).
#
# Rows (one JSON object per line, "ev" discriminates):
#   meta       {ev, schema, t0, label, mode, interval_s, targets, anchor_pid, host}
#   step       {ev, t, t_rel, step}
#   proc       {ev, t, t_rel, step, pid, name, role, cpu_pct, rss_mb,
#               private_mb, threads, read_mb, write_mb, gdi, user_obj, conns}
#   sys        {ev, t, t_rel, step, cpu_pct, mem_avail_pct,
#               net_sent_kbps, net_recv_kbps}
#   proc_new / proc_gone   {ev, t, t_rel, pid, name, role}
#   summary    {ev, t, pids: {pid: {...}}, sys: {...}}
#
# Target discovery is by exe name (so app restarts mid-case are captured);
# children of matched processes (e.g. crashpad_handler) are tracked with
# role="child". cpu_pct semantics match psutil: percent of ONE core, so a
# busy 8-core app shows ~800; the first sample after discovery reads 0.0
# (cpu_percent needs two calls to form a delta).

from __future__ import annotations

import ctypes
import json
import os
import platform
import sys
import threading
import time
import urllib.request
from pathlib import Path

from . import winutil

SCHEMA = 1
_MIN_INTERVAL_S = 0.05
_GR_GDIOBJECTS = 0
_GR_USEROBJECTS = 1
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

_ACTIVE: "PerfMonitor | None" = None


def _stderr(msg: str) -> None:
    print(f"[perf] {msg}", file=sys.stderr)


# --- ctypes helpers (work with or without psutil) ---------------------------

def gui_resources(pid: int) -> tuple[int | None, int | None]:
    """Return (gdi_objects, user_objects) for a pid via GetGuiResources.

    The one GUI-leak metric psutil does not expose. Returns (None, None) when
    the handle cannot be opened (process gone / access denied / non-Windows).
    """
    if os.name != "nt":
        return (None, None)
    h = winutil.kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return (None, None)
    try:
        gdi = winutil.user32.GetGuiResources(h, _GR_GDIOBJECTS)
        usr = winutil.user32.GetGuiResources(h, _GR_USEROBJECTS)
        return (int(gdi), int(usr))
    finally:
        winutil.kernel32.CloseHandle(h)


class _FILETIME(ctypes.Structure):  # type: ignore[name-defined]  # noqa: F821
    _fields_ = [("dwLowDateTime", ctypes.c_uint32),
                ("dwHighDateTime", ctypes.c_uint32)]


def _filetime_s(ft: "_FILETIME") -> float:
    return ((ft.dwHighDateTime << 32) | ft.dwLowDateTime) / 1e7


class _PMC_EX(ctypes.Structure):  # type: ignore[name-defined]  # noqa: F821
    _fields_ = [("cb", ctypes.c_uint32),
                ("PageFaultCount", ctypes.c_uint32),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t)]


def _ctypes_proc_snapshot(pid: int) -> dict | None:
    """CPU seconds + memory bytes for one pid, no psutil. Windows-only."""
    if os.name != "nt":
        return None
    k32 = winutil.kernel32
    h = k32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return None
    try:
        creat, exit_t, kern, user = (_FILETIME(), _FILETIME(), _FILETIME(), _FILETIME())
        if not k32.GetProcessTimes(h, ctypes.byref(creat), ctypes.byref(exit_t),
                                   ctypes.byref(kern), ctypes.byref(user)):
            return None
        pmc = _PMC_EX()
        pmc.cb = ctypes.sizeof(pmc)
        rss = private = None
        if k32.K32GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb):
            rss, private = pmc.WorkingSetSize, pmc.PrivateUsage
        return {"cpu_seconds": _filetime_s(kern) + _filetime_s(user),
                "rss": rss, "private": private}
    finally:
        k32.CloseHandle(h)


# --- Grafana annotations (optional, env-configured) -------------------------

class GrafanaAnnotations:
    """Minimal Grafana /api/annotations client; every failure is swallowed
    (monitoring must never break a run) and logged once per instance."""

    def __init__(self, base_url: str, token: str = "", timeout_s: float = 2.0):
        self._url = base_url.rstrip("/") + "/api/annotations"
        self._token = token
        self._timeout_s = timeout_s
        self._warned = False

    def post(self, text: str, tags: list[str],
             t_start: float, t_end: float | None = None) -> bool:
        body = {"text": text, "tags": tags,
                "time": int(t_start * 1000),
                "timeEnd": int((t_end if t_end is not None else t_start) * 1000)}
        req = urllib.request.Request(
            self._url, data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        if self._token:
            req.add_header("Authorization", f"Bearer {self._token}")
        try:
            with urllib.request.urlopen(req, timeout=self._timeout_s) as resp:
                return 200 <= resp.status < 300
        except Exception as exc:  # noqa: BLE001 — telemetry must not raise
            if not self._warned:
                _stderr(f"grafana annotation failed ({exc}); further errors silent")
                self._warned = True
            return False


# --- the monitor ------------------------------------------------------------

class PerfMonitor:
    """Sample target processes + host counters into a jsonl file.

    psutil mode: discovers targets by exe name each tick (restart-safe) and
    tracks their children. ctypes fallback (use_psutil=False, Windows only):
    samples ONLY anchor_pid with CPU/memory/GDI handles — no name discovery,
    no threads/IO/connections (psutil's per-process net_io_counters is
    Linux-only anyway; per-process bytes on Windows need ETW — out of scope).
    """

    def __init__(self, *, out_path: Path | str,
                 targets: list[str] | None = None,
                 anchor_pid: int | None = None,
                 interval_s: float = 0.5,
                 include_children: bool = True,
                 use_psutil: bool = True,
                 grafana: GrafanaAnnotations | None = None,
                 label: str = ""):
        self._out_path = Path(out_path)
        self._targets = [t.lower().removesuffix(".exe") for t in (targets or [])]
        self._anchor_pid = anchor_pid
        self._interval_s = max(interval_s, _MIN_INTERVAL_S)
        self._include_children = include_children
        self._use_psutil = use_psutil
        self._grafana = grafana
        self._label = label or self._out_path.stem
        self._step = ""
        self._t0 = 0.0
        self._f = None
        self._thread: threading.Thread | None = None
        self._stop_evt = threading.Event()
        self._lock = threading.Lock()
        self._tracked: dict[int, tuple[str, object]] = {}   # pid -> (role, Process)
        self._anchor_proc = None  # cached Process so cpu_percent deltas survive ticks
        self._ct_prev: dict[int, float] = {}                # pid -> cpu_seconds
        self._acc: dict[int, dict] = {}                     # pid -> accumulators
        self._sys_acc = {"n": 0, "cpu_n": 0, "cpu_sum": 0.0, "cpu_max": 0.0,
                         "sent_sum_kb": 0.0, "recv_sum_kb": 0.0,
                         "sent_max_kbps": 0.0, "recv_max_kbps": 0.0,
                         "mem_avail_min_pct": None}
        self._last_sys_net: tuple[float, float, float] | None = None  # (t, sent, recv)

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> "PerfMonitor":
        self._out_path.parent.mkdir(parents=True, exist_ok=True)
        self._f = self._out_path.open("a", encoding="utf-8")
        self._t0 = time.time()
        self._row({"ev": "meta", "schema": SCHEMA, "t": self._t0, "t_rel": 0.0,
                   "label": self._label, "mode": "psutil" if self._use_psutil else "ctypes",
                   "interval_s": self._interval_s, "targets": self._targets,
                   "anchor_pid": self._anchor_pid, "host": platform.node()})
        self._thread = threading.Thread(target=self._loop, name="perf-monitor",
                                        daemon=True)
        self._thread.start()
        return self

    def stop(self) -> dict:
        """Stop sampling, write the summary row, return the summary dict.
        Idempotent: a second call is a no-op returning the same summary."""
        with self._lock:
            if self._f is None:
                return self._summary_payload()
            self._stop_evt.set()
            th, self._thread = self._thread, None
        if th is not None:
            th.join(timeout=self._interval_s * 6 + 1.0)
        summary = self._summary_payload()
        with self._lock:
            if self._f is not None:
                self._row(summary)
                self._f.close()
                self._f = None
        if self._grafana is not None:
            self._grafana.post(f"run end: {self._label}", [self._label, "perf-run"],
                               self._t0, time.time())
        return summary

    def set_step(self, name: str) -> None:
        """Record a step boundary; subsequent rows carry this label."""
        with self._lock:
            self._step = name
            if self._f is not None:
                self._row({"ev": "step", "t": time.time(),
                           "t_rel": round(time.time() - self._t0, 3), "step": name})
        if self._grafana is not None:
            self._grafana.post(f"step: {name}", [self._label, "step"], time.time())

    def __enter__(self) -> "PerfMonitor":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()

    # -- sampling loop --------------------------------------------------------

    def _loop(self) -> None:
        if self._use_psutil:
            try:
                import psutil  # noqa: F401  (presence check)
            except ImportError:
                _stderr("psutil missing — degrading to ctypes anchor-pid mode")
                self._use_psutil = False
        while not self._stop_evt.is_set():
            try:
                if self._use_psutil:
                    self._tick_psutil()
                else:
                    self._tick_ctypes()
            except Exception as exc:  # noqa: BLE001 — sampler must survive
                _stderr(f"tick error: {exc!r}")
            self._stop_evt.wait(self._interval_s)

    def _tick_psutil(self) -> None:
        import psutil

        seen: dict[int, tuple[str, object]] = {}
        for proc in psutil.process_iter(["pid", "name"]):
            name = proc.info["name"] or ""
            if self._name_match(name):
                # process_iter caches Process instances across calls, so
                # cpu_percent(None) on them forms real deltas between ticks
                seen[proc.info["pid"]] = ("target", proc)
        if self._include_children:
            for pid in [p for p, (role, _) in seen.items() if role == "target"]:
                try:
                    for child in psutil.Process(pid).children(recursive=True):
                        # children() hands out FRESH Process objects each call —
                        # reuse the cached one so the child's cpu_percent has a
                        # baseline instead of reading 0.0 forever
                        prev = self._tracked.get(child.pid)
                        seen.setdefault(child.pid,
                                        ("child", prev[1] if prev else child))
                except psutil.Error:
                    pass
        if self._anchor_pid is not None and self._anchor_pid not in seen:
            try:
                if self._anchor_proc is None or self._anchor_proc.pid != self._anchor_pid:
                    self._anchor_proc = psutil.Process(self._anchor_pid)
                seen[self._anchor_pid] = ("anchor", self._anchor_proc)
            except psutil.Error:
                self._anchor_proc = None
        self._emit_lifecycle(seen)
        for pid, (role, proc) in sorted(seen.items()):
            row = self._sample_psutil_proc(pid, role, proc)
            if row:
                self._row(row)
        self._tick_sys()

    def _name_match(self, exe_name: str) -> bool:
        low = exe_name.lower()
        stem = low.removesuffix(".exe")
        return any(stem == t or stem.startswith(t) for t in self._targets)

    def _sample_psutil_proc(self, pid: int, role: str, proc) -> dict | None:
        import psutil

        try:
            cpu = proc.cpu_percent(None)  # first call after (re)discovery: 0.0
            mi = proc.memory_info()
            threads = proc.num_threads()
        except psutil.Error:
            return None
        read_mb = write_mb = conns = None
        try:
            io = proc.io_counters()
            read_mb, write_mb = round(io.read_bytes / 1048576, 3), round(io.write_bytes / 1048576, 3)
        except psutil.Error:
            pass
        try:
            if hasattr(proc, "net_connections"):     # psutil >= 7.2
                conns = len(proc.net_connections())
            else:                                    # psutil < 7.2
                conns = len(proc.connections())
        except psutil.Error:
            pass
        gdi, user_obj = gui_resources(pid)
        return self._proc_row(pid, _safe_name(proc), role, cpu,
                              mi.rss, getattr(mi, "private", None),
                              threads, read_mb, write_mb, gdi, user_obj, conns)

    def _tick_ctypes(self) -> None:
        if self._anchor_pid is None:
            return
        snap = _ctypes_proc_snapshot(self._anchor_pid)
        t = time.time()
        if snap is None:
            if self._anchor_pid in self._tracked:
                self._row({"ev": "proc_gone", "t": t, "t_rel": round(t - self._t0, 3),
                           "pid": self._anchor_pid, "name": "", "role": "anchor"})
                self._tracked.pop(self._anchor_pid, None)
            return
        prev = self._ct_prev.get(self._anchor_pid)
        self._ct_prev[self._anchor_pid] = snap["cpu_seconds"]
        cpu_pct = None
        if prev is not None:
            cpu_pct = round((snap["cpu_seconds"] - prev) / self._interval_s * 100, 2)
        self._tracked[self._anchor_pid] = ("anchor", None)
        row = self._proc_row(self._anchor_pid, "", "anchor", cpu_pct,
                             snap["rss"], snap["private"], None,
                             None, None, *gui_resources(self._anchor_pid), None)
        self._row(row)

    def _tick_sys(self) -> None:
        import psutil

        t = time.time()
        net = psutil.net_io_counters()
        sent_kbps = recv_kbps = None
        last = self._last_sys_net
        self._last_sys_net = (t, net.bytes_sent, net.bytes_recv)
        if last is not None:
            dt = max(t - last[0], 1e-6)
            sent_kbps = round((net.bytes_sent - last[1]) / dt * 8 / 1000, 2)
            recv_kbps = round((net.bytes_recv - last[2]) / dt * 8 / 1000, 2)
            acc = self._sys_acc
            acc["n"] += 1
            acc["sent_sum_kb"] += sent_kbps * dt / 1000
            acc["recv_sum_kb"] += recv_kbps * dt / 1000
            acc["sent_max_kbps"] = max(acc["sent_max_kbps"], sent_kbps)
            acc["recv_max_kbps"] = max(acc["recv_max_kbps"], recv_kbps)
        cpu = psutil.cpu_percent(None)
        vm = psutil.virtual_memory()
        mem_avail = vm.available * 100 / vm.total
        acc = self._sys_acc
        acc["cpu_n"] += 1
        acc["cpu_sum"] += cpu
        acc["cpu_max"] = max(acc["cpu_max"], cpu)
        acc["mem_avail_min_pct"] = (mem_avail if acc["mem_avail_min_pct"] is None
                                    else min(acc["mem_avail_min_pct"], mem_avail))
        self._row({"ev": "sys", "t": t, "t_rel": round(t - self._t0, 3),
                   "step": self._step, "cpu_pct": round(cpu, 2),
                   "mem_avail_pct": round(mem_avail, 2),
                   "net_sent_kbps": sent_kbps, "net_recv_kbps": recv_kbps})

    # -- bookkeeping ----------------------------------------------------------

    def _emit_lifecycle(self, seen: dict[int, tuple[str, object]]) -> None:
        t = time.time()
        for pid, (role, proc) in seen.items():
            if pid not in self._tracked:
                self._row({"ev": "proc_new", "t": t, "t_rel": round(t - self._t0, 3),
                           "pid": pid, "name": _safe_name(proc), "role": role})
        for pid in set(self._tracked) - set(seen):
            role = self._tracked.pop(pid, ("?", None))[0]
            self._acc.setdefault(pid, self._blank_acc(""))["gone"] = True
            self._row({"ev": "proc_gone", "t": t, "t_rel": round(t - self._t0, 3),
                       "pid": pid, "name": "", "role": role})
        self._tracked = seen

    def _blank_acc(self, name: str) -> dict:
        return {"name": name, "role": "", "samples": 0, "cpu_sum": 0.0, "cpu_max": 0.0,
                "rss_max": 0, "private_max": 0, "gdi_first": None, "gdi_last": None,
                "conns_max": 0, "read_mb": 0.0, "write_mb": 0.0}

    def _proc_row(self, pid, name, role, cpu_pct, rss, private, threads,
                  read_mb, write_mb, gdi, user_obj, conns) -> dict:
        acc = self._acc.setdefault(pid, self._blank_acc(name))
        acc["name"], acc["role"] = name, role
        acc["samples"] += 1
        if cpu_pct is not None:
            acc["cpu_sum"] += cpu_pct
            acc["cpu_max"] = max(acc["cpu_max"], cpu_pct)
        if rss:
            acc["rss_max"] = max(acc["rss_max"], rss)
        if private:
            acc["private_max"] = max(acc["private_max"], private)
        if gdi is not None:
            if acc["gdi_first"] is None:
                acc["gdi_first"] = gdi
            acc["gdi_last"] = gdi
        if conns is not None:
            acc["conns_max"] = max(acc["conns_max"], conns)
        if read_mb:
            acc["read_mb"] = max(acc["read_mb"], read_mb)
        if write_mb:
            acc["write_mb"] = max(acc["write_mb"], write_mb)
        return {"ev": "proc", "t": time.time(),
                "t_rel": round(time.time() - self._t0, 3), "step": self._step,
                "pid": pid, "name": name, "role": role,
                "cpu_pct": cpu_pct, "rss_mb": _mb(rss),
                "private_mb": _mb(private), "threads": threads,
                "read_mb": read_mb, "write_mb": write_mb,
                "gdi": gdi, "user_obj": user_obj, "conns": conns}

    def _summary_payload(self) -> dict:
        pids = {}
        for pid, acc in self._acc.items():
            n = max(acc["samples"], 1)
            pids[str(pid)] = {
                "name": acc["name"], "role": acc["role"],
                "samples": acc["samples"],
                "cpu_avg": round(acc["cpu_sum"] / n, 2),
                "cpu_max": round(acc["cpu_max"], 2),
                "rss_max_mb": _mb(acc["rss_max"]),
                "private_max_mb": _mb(acc["private_max"]),
                "gdi_first": acc["gdi_first"], "gdi_last": acc["gdi_last"],
                "gdi_delta": (acc["gdi_last"] - acc["gdi_first"]
                              if acc["gdi_first"] is not None and acc["gdi_last"] is not None
                              else None),
                "conns_max": acc["conns_max"],
                "read_mb_max": acc["read_mb"], "write_mb_max": acc["write_mb"],
                "gone": acc.get("gone", False)}
        sys_acc = self._sys_acc
        return {"ev": "summary", "t": time.time(),
                "label": self._label,
                "pids": pids,
                "sys": {"n": sys_acc["n"],
                        "cpu_avg": round(sys_acc["cpu_sum"] / max(sys_acc["cpu_n"], 1), 2),
                        "cpu_max": round(sys_acc["cpu_max"], 2),
                        "net_sent_mb": round(sys_acc["sent_sum_kb"] / 1024, 3),
                        "net_recv_mb": round(sys_acc["recv_sum_kb"] / 1024, 3),
                        "net_sent_max_kbps": round(sys_acc["sent_max_kbps"], 2),
                        "net_recv_max_kbps": round(sys_acc["recv_max_kbps"], 2),
                        "mem_avail_min_pct": (round(sys_acc["mem_avail_min_pct"], 2)
                                              if sys_acc["mem_avail_min_pct"] is not None
                                              else None)}}

    def _row(self, obj: dict) -> None:
        if self._f is not None:
            self._f.write(json.dumps(obj, ensure_ascii=False) + "\n")
            self._f.flush()


def _safe_name(proc) -> str:
    try:
        return proc.name()
    except Exception:  # noqa: BLE001 — name is cosmetic
        return ""


def _mb(n) -> float | None:
    return round(n / 1048576, 2) if n else None


# --- launcher integration (env-gated) ----------------------------------------

def env_enabled() -> bool:
    return os.environ.get("ORCA_BB_PERF", "").strip().lower() not in ("", "0", "false", "no")


def resolve_out_path(label: str) -> Path:
    """ORCA_BB_PERF_OUT (file path, or dir when it ends without .jsonl) wins;
    default artifacts/perf/<label>__<ts>.jsonl under the repo root."""
    env = os.environ.get("ORCA_BB_PERF_OUT")
    if env:
        p = Path(env)
        return p if p.suffix == ".jsonl" else p / f"{label}__{_ts()}.jsonl"
    root = Path(__file__).resolve().parents[1]
    return root / "artifacts" / "perf" / f"{label}__{_ts()}.jsonl"


def _ts() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def attach_for_session(popen, exe: Path | str,
                       interval_s: float = 0.5) -> PerfMonitor:
    """launcher.launch() hook: monitor by exe name + the launched pid."""
    label = (os.environ.get("ORCA_BB_PERF_LABEL")
             or f"{Path(exe).stem}__pid{popen.pid}")
    grafana = None
    url = os.environ.get("ORCA_BB_GRAFANA_URL")
    if url:
        grafana = GrafanaAnnotations(url, os.environ.get("ORCA_BB_GRAFANA_TOKEN", ""))
    mon = PerfMonitor(targets=[Path(exe).name], anchor_pid=popen.pid,
                      out_path=resolve_out_path(label),
                      interval_s=interval_s, grafana=grafana, label=label)
    mon.start()
    global _ACTIVE
    _ACTIVE = mon
    _stderr(f"attached label={label} out={mon._out_path}")
    return mon


def set_step(name: str) -> None:
    """Mark a step boundary on the active monitor (no-op when detached).
    Safe to call from any case/driver code unconditionally."""
    mon = _ACTIVE
    if mon is not None:
        mon.set_step(name)
