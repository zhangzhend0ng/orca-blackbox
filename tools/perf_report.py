#!/usr/bin/env python3
"""Summarize captured JSONL. Pass --grafana to export annotations after the run."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from statistics import median
import sys

if __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.perf_frames import percentiles

_RESOURCES = ("rss_mb", "private_mb", "handles", "gdi", "user_obj")
_PEAKS = (*_RESOURCES, "threads", "peak_rss_bytes", "conns")
_COUNTERS = ("read_bytes", "write_bytes", "page_faults", "cpu_seconds")


def load_rows(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                row = None
            rows.append(row if isinstance(row, dict) else {"ev": "unreadable"})
    return rows


def _peak(old, value):
    if value is None or (old is not None and old >= value):
        return old
    return value


def _average(total, duration):
    return round(total / duration, 2) if duration else None


def _network(rows, schema):
    sent = recv = 0
    n = 0
    prev_t = None
    for row in rows:
        if schema == 2:
            pair = row.get("net_sent_bytes"), row.get("net_recv_bytes")
        else:
            # Schema 1 used decimal kbit/s and wall-clock timestamps.
            t = row.get("t")
            dt = t - prev_t if t is not None and prev_t is not None else 0
            rates = row.get("net_sent_kbps"), row.get("net_recv_kbps")
            pair = tuple(v * dt * 1000 / 8 if v is not None and dt > 0 else None for v in rates)
            prev_t = t
        if all(value is not None for value in pair):
            sent += pair[0]
            recv += pair[1]
            n += 1
    return {"samples": len(rows), "network_samples": n,
            "net_sent_mb": round(sent / 1048576, 3) if n else None,
            "net_recv_mb": round(recv / 1048576, 3) if n else None}


def _measurements(rows, anchor_pid):
    groups = {}
    frames = []
    idle = []
    for row in rows:
        if row.get("ev") != "measurement":
            continue
        name = row["name"]
        if name == "frame_capture":
            frames.append(row)
            continue
        groups.setdefault(name, []).append(row)
        if name == "soak_idle" and row["status"] == "observed":
            samples = [s for s in rows if s.get("ev") == "proc" and s.get("pid") == anchor_pid
                       and s.get("step") == "soak_idle"
                       and row["start_rel"] <= s["t_rel"] <= row["t_rel"]]
            if len({s["process_id"] for s in samples}) != 1:
                samples = []
            values = {}
            for key in _RESOURCES:
                observed = [s[key] for s in samples if s.get(key) is not None]
                values[key] = median(observed) if observed else None
            idle.append({"cycle": row["cycle"], "sample_count": len(samples), "median": values,
                         "process_id": samples[0]["process_id"] if samples else None})
    baseline = next((row for row in idle if row["cycle"] == 0), {})
    for point in idle:
        comparison = baseline.get("median", {}) if point["process_id"] == baseline.get("process_id") else {}
        point["delta_from_baseline"] = {
            key: value - comparison[key] if value is not None and comparison.get(key) is not None else None
            for key, value in point["median"].items()
        }
    return ({name: {"events": events, "duration_ms": percentiles(
                [event["duration_ms"] for event in events if event.get("duration_ms") is not None])}
             for name, events in groups.items()}, frames, idle)


def summarize(rows: list[dict]) -> dict:
    meta_rows = [row for row in rows if row.get("ev") == "meta"]
    if len(meta_rows) > 1:
        raise ValueError("multiple streams in one JSONL")
    meta = next(iter(meta_rows), {})
    schema = meta.get("schema", 1)
    if schema not in (1, 2):
        raise ValueError(f"unsupported schema {schema}")
    terminal = rows[-1] if rows and rows[-1].get("ev") == "summary" else None
    status = (terminal.get("status", "complete") if terminal else "partial") if meta else "unavailable"
    if schema == 2 and terminal and any(terminal.get(key) != meta.get(key) for key in ("run_id", "instance_id")):
        raise ValueError("summary identity does not match stream")
    if meta and any(row.get("ev") == "unreadable" for row in rows):
        status = "partial"
    pids = {}
    steps = {}
    ticks = {}
    host = []
    for row in rows:
        if row.get("ev") == "sys":
            host.append(row)
        if row.get("ev") != "proc":
            continue
        pid = row.get("process_id", str(row.get("pid")))
        cpu = row.get("cpu_pct")
        duration = row.get("cpu_dt_s") if schema == 2 else 1.0
        proc = pids.setdefault(pid, {
            "pid": row.get("pid"), "name": row.get("name", ""), "role": row.get("role", ""),
            "samples": 0, "cpu_sum": 0.0, "cpu_duration": 0.0, "cpu_max": None,
            "private_max_mb": None, "rss_max_mb": None, "gdi_first": None,
            "gdi_last": None, "conns_max": None,
            "metric_peaks": dict.fromkeys(_PEAKS),
            "counter_bounds": {},
        })
        proc["samples"] += 1
        if cpu is not None and duration:
            proc["cpu_sum"] += cpu * duration
            proc["cpu_duration"] += duration
            proc["cpu_max"] = _peak(proc["cpu_max"], cpu)
        for max_field, sample_field in (("private_max_mb", "private_mb"), ("rss_max_mb", "rss_mb"),
                                        ("conns_max", "conns")):
            proc[max_field] = _peak(proc[max_field], row.get(sample_field))
        for key in _PEAKS:
            proc["metric_peaks"][key] = _peak(proc["metric_peaks"][key], row.get(key))
        for key in _COUNTERS:
            value = row.get(key)
            if value is not None:
                bounds = proc["counter_bounds"].setdefault(key, [value, value, 0, False])
                bounds[3] |= value < bounds[1]
                bounds[1] = value
                bounds[2] += 1
        gdi = row.get("gdi")
        if gdi is not None:
            if proc["gdi_first"] is None:
                proc["gdi_first"] = gdi
            proc["gdi_last"] = gdi
        phase = row.get("step") or "(none)"
        case = row.get("case_run_id")
        name = f"{case}/{phase}" if case else phase
        step = steps.setdefault(name, {"case_run_id": case, "step": phase, "samples": 0,
                                      "private_max_mb": None, "cpu_sum": 0.0, "cpu_duration": 0.0})
        step["samples"] += 1
        step["private_max_mb"] = _peak(step["private_max_mb"], row.get("private_mb"))
        if cpu is not None and duration:
            if schema == 1:
                # Preserve step CPU semantics for archived schema 1 traces.
                step["cpu_sum"] += cpu
                step["cpu_duration"] += duration
            else:
                # Sum the observed CPU-seconds per tick, then divide by
                # elapsed time once. A quiet child must not dilute the app.
                tick = ticks.setdefault((name, row["tick"]), [0.0, 0.0])
                tick[0] += cpu * duration / 100
                tick[1] = max(tick[1], duration)
    for (name, _), (cpu_seconds, duration) in ticks.items():
        steps[name]["cpu_sum"] += cpu_seconds * 100
        steps[name]["cpu_duration"] += duration
    for result in (*pids.values(), *steps.values()):
        result["cpu_avg"] = _average(result.pop("cpu_sum"), result.pop("cpu_duration"))
        if "gdi_first" in result:
            first, last = result["gdi_first"], result["gdi_last"]
            result["gdi_delta"] = None if first is None else last - first
            bounds = result.pop("counter_bounds")
            result["counter_deltas"] = {
                key: (bounds[key][1] - bounds[key][0] if key in bounds
                      and bounds[key][2] >= 2 and not bounds[key][3] else None)
                for key in _COUNTERS
            }
    operations, frames, soak = _measurements(rows, meta.get("anchor_pid"))
    return {"meta": meta, "status": status, "reason": terminal.get("reason") if terminal else None,
            "pids": pids, "steps": steps, "sys": _network(host, schema),
            "measurements": operations, "frame_captures": frames, "soak_checkpoints": soak}


def _number(n):
    return "-" if n is None else f"{n:.1f}"


def _print_report(path: Path, summary: dict) -> None:
    meta = summary["meta"]
    print(f"== {path}  label={meta.get('label')} mode={meta.get('mode')} status={summary['status']}")
    print(f"{'PID':>7} {'ROLE':<7} {'NAME':<24} {'N':>4} {'CPUavg':>7} {'CPUmax':>7} {'PRIVmax':>8} {'GDI0>1':>9}")
    for proc in summary["pids"].values():
        first, last = proc["gdi_first"], proc["gdi_last"]
        gdi = "-" if first is None else f"{first}>{last}"
        print(f"{proc['pid']:>7} {proc['role']:<7} {proc['name'][:24]:<24} {proc['samples']:>4} "
              f"{_number(proc['cpu_avg']):>7} {_number(proc['cpu_max']):>7} "
              f"{_number(proc['private_max_mb']):>8} {gdi:>9}")
    print(f"{'STEP':>32} {'N':>4} {'CPUavg':>7} {'PRIVmax':>8}")
    for step in summary["steps"].values():
        print(f"{step['step'][:32]:>32} {step['samples']:>4} {_number(step['cpu_avg']):>7} "
              f"{_number(step['private_max_mb']):>8}")
    host = summary["sys"]
    print(f"sys: samples={host['samples']} net_sent={host['net_sent_mb']} MiB "
          f"net_recv={host['net_recv_mb']} MiB")
    for name, measurement in summary["measurements"].items():
        duration = measurement["duration_ms"]
        value = f"{duration['p50']:.1f} ms (n={duration['count']})" if duration else "unavailable"
        print(f"{name}: {value}")
    for capture in summary["frame_captures"]:
        metrics = capture.get("frame_summary", {}).get("metrics")
        label = capture.get("activity", "viewport")
        if metrics:
            frame = metrics["displayed_frame_ms"]
            print(f"{label}: {metrics['displayed_fps']:.1f} displayed FPS, "
                  f"P95/P99 {frame['p95']:.1f}/{frame['p99']:.1f} ms, max {frame['max']:.1f} ms")
        else:
            print(f"{label} frames: {capture.get('reason', capture['status'])}")
    for point in summary["soak_checkpoints"]:
        print(f"idle cycle {point['cycle']}: n={point['sample_count']} "
              f"delta={point['delta_from_baseline']}")


def _export_annotations(rows, meta, client):
    if not meta:
        return False
    label = meta.get("label") or "perf"
    tags = [label, "perf-run", meta.get("run_id") or "legacy"]
    steps = [row for row in rows if row.get("ev") == "step" and row.get("t") is not None]
    def timestamp(row):
        if meta.get("schema") == 2 and row.get("t_rel") is not None:
            return meta["t"] + row["t_rel"]
        return row.get("t")

    for index, step in enumerate(steps):
        start = timestamp(step)
        end = timestamp(steps[index + 1] if index + 1 < len(steps) else rows[-1])
        if end is not None and end < start:
            end = None  # Wall clock moved backwards.
        if not client.post(step["step"], tags, start, end):
            return False
    return True


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--grafana", action="store_true")
    args = parser.parse_args(argv)
    client = None
    if args.grafana:
        url = os.environ.get("ORCA_BB_GRAFANA_URL")
        if not url:
            parser.error("--grafana requires ORCA_BB_GRAFANA_URL")
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from harness.perf_monitor import GrafanaAnnotations
        client = GrafanaAnnotations(url, os.environ.get("ORCA_BB_GRAFANA_TOKEN", ""))
    rc = 0
    for path in args.inputs:
        try:
            rows = load_rows(path)
            summary = summarize(rows)
            _print_report(path, summary)
            out = path.with_suffix(".summary.json")
            out.write_text(json.dumps(summary, ensure_ascii=False, allow_nan=False, indent=1),
                           encoding="utf-8")
            print(f"summary: {out}")
            if client is not None and not _export_annotations(rows, summary["meta"], client):
                rc = 2
        except (OSError, ValueError) as error:
            print(f"ERROR: {path}: {error}", file=sys.stderr)
            rc = 2
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
