"""Read Orca's test-build SwapBuffers trace and join it to driver QPC windows."""

from collections import defaultdict
import csv
from pathlib import Path
import struct
from typing import NamedTuple

from .perf_frames import percentiles

HEADER = struct.Struct("<8s4I5Q")
RECORD = struct.Struct("<3q4I")
CAPACITY = 262144
CANVAS_NAMES = ("prepare", "preview", "assemble")


class Frame(NamedTuple):
    begin: int
    before: int
    after: int
    kind: int
    canvas: int
    flags: int


def read_trace(path, pid, frequency):
    size = path.stat().st_size
    if not HEADER.size <= size <= HEADER.size + CAPACITY * RECORD.size:
        raise ValueError("invalid native frame trace size")
    with path.open("rb") as source:
        magic, head, record, owner, complete, hz, capacity, written, dropped, reserved = HEADER.unpack(
            source.read(HEADER.size))
        if ((magic, head, record, owner, hz, capacity) != (b"ORCAFRM1", HEADER.size, RECORD.size,
                                                          pid, frequency, CAPACITY)
                or hz <= 0 or complete not in (0, 1) or reserved
                or written > capacity or HEADER.size + written * RECORD.size > size):
            raise ValueError("invalid native frame trace header or process identity")
        frames = []
        previous = 0
        for begin, before, after, kind, canvas, flags, spare in RECORD.iter_unpack(
                source.read(written * RECORD.size)):
            if (not 0 < begin <= before <= after or before < previous or kind >= len(CANVAS_NAMES)
                    or not 1 <= canvas <= 32 or flags & ~3 or spare):
                raise ValueError("invalid native frame record")
            frames.append(Frame(begin, before, after, kind, canvas, flags))
            previous = before
    return frames, bool(complete), dropped


def _measure_stream(frames, hz):
    submitted = [f for f in frames if not f.flags & 2]
    tick_ms = 1000 / hz
    intervals = [(b.before - a.before) * tick_ms for a, b in zip(submitted, submitted[1:])]
    span_ms = sum(intervals)
    return {
        "frames": len(submitted), "failed_swaps": len(frames) - len(submitted),
        "overlay_only": sum(bool(f.flags & 1) for f in submitted),
        "submitted_fps": len(intervals) * 1000 / span_ms if span_ms else None,
        "frame_interval_ms": percentiles(intervals),
        "render_before_swap_ms": percentiles([(f.before - f.begin) * tick_ms for f in submitted]),
        "swap_call_ms": percentiles([(f.after - f.before) * tick_ms for f in submitted]),
    }


def _streams(frames, hz):
    streams = defaultdict(list)
    for frame in frames:
        streams[f"{CANVAS_NAMES[frame.kind]}:{frame.canvas}"].append(frame)
    return {name: _measure_stream(items, hz) for name, items in streams.items()}


def analyze(jsonl_path: Path, rows, pid, *, write_csv=False):
    sync = next((row for row in rows if row.get("name") == "render_clock_sync"), None)
    if not sync:
        return None
    path = jsonl_path.with_suffix(".render.bin")
    report = {"source": "orca_swap_buffers", "artifact": path.name}
    if sync.get("artifact") != path.name or not path.is_file():
        return {**report, "status": "unavailable", "reason": "native_trace_missing"}
    hz = sync["qpc_hz"]
    try:
        frames, complete, dropped = read_trace(path, pid, hz)
    except (OSError, ValueError) as error:
        return {**report, "status": "unavailable", "reason": str(error)}

    activities = []
    for event in rows:
        if event.get("name") != "render_activity" or event.get("qpc_hz") != hz:
            continue
        scoped = [f for f in frames if event["qpc_start"] <= f.before < event["qpc_end"]]
        activities.append({"activity": event["activity"], "inputs": event["inputs"],
                           "status": "observed" if scoped else "no_frame_submissions",
                           "streams": _streams(scoped, hz)})
    relative = (sync["start_rel"] + sync["t_rel"]) / 2
    if write_csv and frames:
        output = jsonl_path.with_suffix(".render.csv")
        with output.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(("t_rel", "qpc_before_swap", "canvas_type", "canvas_id", "overlay_only",
                             "swap_succeeded", "render_before_swap_ms", "swap_call_ms"))
            writer.writerows((relative + (f.before - sync["qpc"]) / hz, f.before,
                              CANVAS_NAMES[f.kind], f.canvas, int(bool(f.flags & 1)),
                              int(not f.flags & 2), (f.before - f.begin) * 1000 / hz,
                              (f.after - f.before) * 1000 / hz) for f in frames)
        report["csv"] = output.name
    return {**report, "status": ("partial" if not complete or dropped else
                                 "observed" if frames else "no_frame_submissions"),
            "process_id": pid, "qpc_hz": hz, "frames": len(frames), "dropped": dropped,
            "streams": _streams(frames, hz), "activities": activities}
