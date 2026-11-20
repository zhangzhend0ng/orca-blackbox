"""Process-bound PresentMon capture and per-activity display metrics."""

from __future__ import annotations

from collections import defaultdict
import csv
import ctypes
import math
import os
from pathlib import Path
import statistics
import subprocess
import time


def percentiles(values):
    ordered = sorted(values)
    if not ordered:
        return None
    return {"count": len(ordered), "p50": statistics.median(ordered),
            "p95": ordered[math.ceil(len(ordered) * .95) - 1],
            "p99": ordered[math.ceil(len(ordered) * .99) - 1], "max": ordered[-1]}


def _number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def clock():
    """The raw Windows clock used by PresentMon's --qpc_time."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    ticks, hz = ctypes.c_longlong(), ctypes.c_longlong()
    if not kernel.QueryPerformanceCounter(ctypes.byref(ticks)) or not kernel.QueryPerformanceFrequency(ctypes.byref(hz)):
        raise OSError("QPC unavailable")
    return ticks.value, hz.value


class FrameCapture:
    def __init__(self, pid, csv_path, instance, seconds):
        self.pid = pid
        self.path = Path(csv_path)
        self.instance = instance
        self.seconds = seconds
        self.process = None
        self.reason = "presentmon_unconfigured"

    def __enter__(self):
        exe = os.environ.get("ORCA_BB_PRESENTMON_EXE", "")
        if not exe:
            return self
        binary = Path(exe)
        if os.name != "nt" or not binary.is_absolute() or not binary.is_file():
            self.reason = "presentmon_binary_unavailable"
            return self
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists():
                self.reason = "existing_frame_csv"
                return self
            self.process = subprocess.Popen(
                [str(binary), "--process_id", str(self.pid), "--session_name", f"OrcaPerf-{self.instance}",
                 "--output_file", str(self.path), "--v2_metrics", "--qpc_time",
                 "--timed", str(self.seconds), "--terminate_after_timed", "--no_console_stats"],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            self.deadline = time.monotonic() + self.seconds + 4
            self.reason = None
        except OSError:
            self.reason = "presentmon_start_failed"
        return self

    def __exit__(self, *exc):
        if self.process is None:
            return
        try:
            # Preserve a fully flushed trace. Only this owned process is stopped on timeout.
            code = self.process.wait(timeout=max(0, self.deadline - time.monotonic()))
            if code:
                self.reason = f"presentmon_exit_{code}"
            elif not self.path.is_file():
                self.reason = "presentmon_csv_missing"
        except subprocess.TimeoutExpired:
            self.reason = "presentmon_timeout"
            try:
                self.process.kill()
                self.process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                self.reason = "presentmon_stop_unconfirmed"


def read_frames(path, pid):
    frames = []
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        required = {"ProcessID", "SwapChainAddress", "CPUStartQPC", "DisplayedTime"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("Unexpected PresentMon columns")
        for row in reader:
            if row["ProcessID"] != str(pid):
                continue
            try:
                qpc = int(row["CPUStartQPC"])
            except (TypeError, ValueError):
                continue
            duration = _number(row["DisplayedTime"])
            display = row["DisplayedTime"]
            frames.append((qpc, row["SwapChainAddress"], duration,
                           bool(display and display.strip().upper() == "NA"),
                           _number(row.get("MsGPUBusy", row.get("GPUBusy"))),
                           _number(row.get("MsCPUBusy", row.get("CPUBusy")))))
    return frames


def frame_metrics(frames, start, end):
    streams = defaultdict(list)
    for sample in frames:
        if start <= sample[0] <= end:
            streams[sample[1]].append(sample)
    results = {}
    for name, stream in streams.items():
        # DisplayedTime of the last visible frame can include the subsequent
        # idle period. Keep intervals only between frames inside this window.
        displayed = [row[2] for row in sorted(stream) if row[2] is not None and row[2] > 0]
        intervals = displayed[:-1]
        dropped = sum(row[3] for row in stream)
        result = {
            "displayed_frame_ms": percentiles(intervals),
            "displayed_fps": len(intervals) * 1000 / sum(intervals) if intervals else None,
            "presented_frames": len(stream), "displayed_frames": len(displayed),
            "dropped_frames": dropped if len(displayed) + dropped == len(stream) else None,
            "gpu_busy_ms": percentiles([r[4] for r in stream if r[4] is not None]),
            "cpu_busy_ms": percentiles([r[5] for r in stream if r[5] is not None]),
        }
        results[name] = result
    visible_streams = [s for s in results.values() if s["displayed_frames"]]
    status = ("ambiguous_swapchain" if len(visible_streams) > 1 else
              "observed" if visible_streams and visible_streams[0]["displayed_frame_ms"] else
              "insufficient_displayed_frames")
    return {"status": status, "swapchains": results,
            "metrics": visible_streams[0] if status == "observed" else None}
