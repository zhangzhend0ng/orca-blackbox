#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""perf_report.py <metrics.jsonl> [...] — aggregate perf_monitor jsonl runs.

Prints a per-process table, a per-step table and host/network totals, and
writes <input>.summary.json next to each input. Read-only on the input.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def load_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # torn tail line from a crashed run — skip, keep going
    return rows


def summarize(rows: list[dict]) -> dict:
    per_pid: dict[str, dict] = {}
    per_step: dict[str, dict] = {}
    sys_rows: list[dict] = []
    meta = next((r for r in rows if r.get("ev") == "meta"), {})
    for r in rows:
        ev = r.get("ev")
        if ev == "proc":
            pid = str(r.get("pid"))
            acc = per_pid.setdefault(pid, {"name": r.get("name", ""),
                                           "role": r.get("role", ""), "n": 0,
                                           "cpu_sum": 0.0, "cpu_max": 0.0,
                                           "priv_max": 0.0, "rss_max": 0.0,
                                           "gdi_first": None, "gdi_last": None,
                                           "conns_max": 0})
            acc["n"] += 1
            cpu = r.get("cpu_pct")
            if cpu is not None:
                acc["cpu_sum"] += cpu
                acc["cpu_max"] = max(acc["cpu_max"], cpu)
            acc["priv_max"] = max(acc["priv_max"], r.get("private_mb") or 0.0)
            acc["rss_max"] = max(acc["rss_max"], r.get("rss_mb") or 0.0)
            gdi = r.get("gdi")
            if gdi is not None:
                if acc["gdi_first"] is None:
                    acc["gdi_first"] = gdi
                acc["gdi_last"] = gdi
            conns = r.get("conns")
            if conns is not None:
                acc["conns_max"] = max(acc["conns_max"], conns)
            step = r.get("step") or "(none)"
            s = per_step.setdefault(step, {"n": 0, "cpu_sum": 0.0,
                                           "priv_max": 0.0})
            s["n"] += 1
            if cpu is not None:
                s["cpu_sum"] += cpu
            s["priv_max"] = max(s["priv_max"], r.get("private_mb") or 0.0)
        elif ev == "sys":
            sys_rows.append(r)
    net_sent_mb = net_recv_mb = 0.0
    prev_t = None
    for r in sys_rows:
        t = r.get("t")
        if prev_t is not None and t is not None:
            dt = t - prev_t
            if r.get("net_sent_kbps") is not None:
                net_sent_mb += r["net_sent_kbps"] * dt / 8 / 1024
                net_recv_mb += r["net_recv_kbps"] * dt / 8 / 1024
        prev_t = r.get("t")
    return {
        "meta": {k: meta.get(k) for k in ("label", "mode", "interval_s",
                                          "targets", "host")},
        "pids": {pid: {"name": a["name"], "role": a["role"], "samples": a["n"],
                       "cpu_avg": round(a["cpu_sum"] / max(a["n"], 1), 2),
                       "cpu_max": round(a["cpu_max"], 2),
                       "private_max_mb": a["priv_max"], "rss_max_mb": a["rss_max"],
                       "gdi_first": a["gdi_first"], "gdi_last": a["gdi_last"],
                       "gdi_delta": (a["gdi_last"] - a["gdi_first"]
                                     if a["gdi_first"] is not None and a["gdi_last"] is not None
                                     else None),
                       "conns_max": a["conns_max"]}
                  for pid, a in per_pid.items()},
        "steps": {step: {"samples": s["n"],
                         "cpu_avg": round(s["cpu_sum"] / max(s["n"], 1), 2),
                         "private_max_mb": s["priv_max"]}
                  for step, s in sorted(per_step.items())},
        "sys": {"samples": len(sys_rows),
                "net_sent_mb": round(net_sent_mb, 3),
                "net_recv_mb": round(net_recv_mb, 3)}}


def _print_report(path: Path, s: dict) -> None:
    print(f"== {path}  label={s['meta'].get('label')} mode={s['meta'].get('mode')}")
    hdr = f"{'PID':>7} {'ROLE':<7} {'NAME':<24} {'N':>4} {'CPUavg':>7} {'CPUmax':>7} {'PRIVmax':>8} {'GDI0>1':>9} {'CONNmax':>7}"
    print(hdr)
    for pid, a in s["pids"].items():
        gdi = (f"{a['gdi_first']}>{a['gdi_last']}"
               if a["gdi_first"] is not None else "-")
        print(f"{pid:>7} {a['role']:<7} {a['name'][:24]:<24} {a['samples']:>4} "
              f"{a['cpu_avg']:>7.1f} {a['cpu_max']:>7.1f} {a['private_max_mb']:>8.1f} "
              f"{gdi:>9} {a['conns_max']:>7}")
    print(f"{'STEP':>32} {'N':>4} {'CPUavg':>7} {'PRIVmax':>8}")
    for step, st in s["steps"].items():
        print(f"{step[:32]:>32} {st['samples']:>4} {st['cpu_avg']:>7.1f} "
              f"{st['private_max_mb']:>8.1f}")
    sys_s = s["sys"]
    print(f"sys: samples={sys_s['samples']} net_sent={sys_s['net_sent_mb']}MB "
          f"net_recv={sys_s['net_recv_mb']}MB")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    rc = 0
    for arg in argv:
        path = Path(arg)
        if not path.exists():
            print(f"ERROR: not found: {path}", file=sys.stderr)
            rc = 2
            continue
        s = summarize(load_rows(path))
        _print_report(path, s)
        out = path.with_suffix(".summary.json")
        out.write_text(json.dumps(s, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        print(f"summary: {out}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
