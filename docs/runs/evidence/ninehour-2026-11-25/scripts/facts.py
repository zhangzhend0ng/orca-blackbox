#!/usr/bin/env python3
"""Part A - business facts from the harvested G-code and saved projects (offline, read-only).

    set PYTHONDONTWRITEBYTECODE=1
    python -B C:\\coil\\vm_setup\\ninehour_1125\\recompute\\facts.py [--verbose] [--out facts.json]

Reads the harvests of C:\\coil\\Projects\\SnapmakerOrca\\external\\orca-blackbox (branch
software_testing) and of its .worktrees\\glm, imports repository code read-only (no bytecode is
written into the checkouts) and writes facts.json next to this script. It launches nothing and
modifies nothing outside its own directory.

Every number in facts.json is read from a file whose sha256 is recorded beside it. The harvest
root is written to while a batch runs, so each run id is resolved again on every invocation and
the root actually read is recorded ("locations").
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import inspect
import io
import json
import math
import os
import subprocess
import sys
import time
import zipfile
from decimal import Decimal
from pathlib import Path

sys.dont_write_bytecode = True          # belt and braces next to `python -B`
HERE = Path(__file__).resolve().parent
REPO = Path(r"C:\coil\Projects\SnapmakerOrca\external\orca-blackbox")
ROOTS = [("main", REPO / "artifacts" / "windows_mcp_harvest"),
         ("glm-worktree", REPO / ".worktrees" / "glm" / "artifacts" / "windows_mcp_harvest")]
DISPATCH = Path(r"C:\coil\vm_setup\ninehour_1125")       # host-side ledger of tonight's batch (read)
SETTINGS_MEMBER = "Metadata/project_settings.config"
ABSENT = object()                                         # a key missing from a config

# run id, Feishu row, role. The scenario is read from each run's scope.json, never assumed.
RUNS = [
    ("ec032d7cc54844f1a6f970a6990fa032", "276", "case"),
    ("eebdf238d72e401b9636b161bad6c465", "276", "case"),
    ("5359abcadafa48a2bc493ee3acf56114", "276", "case"),
    ("e9aa6f88eca940b385bfe531703f644e", "276", "fixed comparison baseline (harness.param_comparison._BASELINES)"),
    ("7484bd43c9114b5b8f8d098a6ac978e3", "264", "case"),
    ("b697f7c24c6c49849c05b22c2a8ed1a3", "264", "case"),
    ("8e207463943845c2a4564a47efc54d64", "264", "case"),
    ("19d6103223264b2c8f21a0b8c5f76d1e", "264", "case"),
    ("0cccce4a3b3f40798bcab64c8a815680", "264", "default-parameter baseline of the fdmt fixture (uia_param_fdmt_save_only)"),
]
# The Feishu steps, verbatim values. A tuple value marks a per-extruder list: (index, value).
FEISHU = {
    "264": {"detect_overhang_wall": "1", "enable_overhang_speed": "1",
            "overhang_1_4_speed": "40", "overhang_2_4_speed": "30", "overhang_3_4_speed": "20",
            "overhang_4_4_speed": "10", "overhang_totally_speed": "5"},
    "276": {"outer_wall_speed": "700", "layer_height": "0.20", "outer_wall_line_width": "0.42",
            "filament_max_volumetric_speed": (0, "15"),      # filament slot 1
            "machine_max_speed_x": (0, "500")},               # normal mode (index 1 is silent)
}
SHORT = {"detect_overhang_wall": "detect", "enable_overhang_speed": "enable", "overhang_1_4_speed": "1/4",
         "overhang_2_4_speed": "2/4", "overhang_3_4_speed": "3/4", "overhang_4_4_speed": "4/4",
         "overhang_totally_speed": "totally", "outer_wall_speed": "ow_speed", "layer_height": "layer_h",
         "outer_wall_line_width": "ow_width", "filament_max_volumetric_speed": "maxvol[slot1]",
         "machine_max_speed_x": "maxX[normal]"}
FEISHU_F = [2400, 1800, 1200, 600, 300]          # row 264 expectation 2, mm/min
OVERHANG_TYPES = ("Overhang wall", "Overhang bridge")
BRIDGE_TYPES = ("Bridge", "Internal Bridge")
PIN_NAMES = {"ed1ca79dd1dd1de28e9d21fb55efc5cee12f1215fbad9cac07159e5d7687d8ef": "LAYER_FIXTURE (fixtures/agent_layer_cube.3mf)",
             "36389ec3d26c54fc8d3e6bfccac3097fb080a12ab8fab0f2b7f8038cfc278d94": "STD_FIXTURE (fixtures/feishu_std_cube.3mf)"}

sys.path.insert(0, str(REPO))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from harness import param_comparison, pilot_common  # noqa: E402
from harness.agent_protocol import BASELINES, FIXTURE_SUFFIXES  # noqa: E402
from harness.gcode_check import config_value_all  # noqa: E402
from harness.native_pilots import CONTROLS, native_fixture, verify_business  # noqa: E402
from tools import audit_276_flow  # noqa: E402
from tools.feishu_model_fixtures import feishu_rows, fixture_for, row_plan  # noqa: E402
from tools.gcode_facts import COORD_RE, F_RE, _num, gcode_facts  # noqa: E402


# --------------------------------------------------------------------------- provenance helpers
def cite(function):
    """Where a repository function lives, read from the imported object itself."""
    file = Path(inspect.getsourcefile(function))
    return {"function": function.__module__ + "." + function.__qualname__, "file": str(file),
            "line": inspect.getsourcelines(function)[1], "sha256_of_file": sha256_file(file)}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def git_head(root: Path) -> str:
    """Read-only `git rev-parse HEAD`; 'unknown' when git cannot answer."""
    try:
        return subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True,
                              text=True, timeout=20).stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError) as exc:
        return "unknown (%s)" % type(exc).__name__


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def settings_of(archive: bytes) -> dict:
    """The project's settings member as a dict (std-lib zip + json; no repository code)."""
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        return json.loads(zipped.read(SETTINGS_MEMBER).decode("utf-8-sig"))


def normalize(value):
    """The app writes an EDITED scalar as a one-element list; compare it with its scalar."""
    if isinstance(value, list) and len(value) == 1:
        return value[0]
    return value


def same(a, b):
    """Numeric equality when both are numbers (Decimal), text equality otherwise; None if impossible."""
    try:
        return Decimal(str(a)) == Decimal(str(b))
    except Exception:  # noqa: BLE001 - non-numeric values compare as text
        try:
            return str(a) == str(b)
        except Exception:  # noqa: BLE001
            return None


def classify(key, before, after, targets) -> str:
    """Why `key` differs between the fixture and the saved project, by the repository's own rules
    (harness.pilot_common._ADDED_DEFAULTS / _VECTOR_MIGRATIONS / inspect_preserved_settings)."""
    if key == "different_settings_to_system":
        return "dirty-list"
    if key in targets:
        if before is ABSENT or after is ABSENT:
            return "target (key added or removed)"
        return "target" if normalize(before) != normalize(after) else "target (value unchanged, shape migrated)"
    if before is ABSENT:
        if key in pilot_common._ADDED_DEFAULTS and after == pilot_common._ADDED_DEFAULTS[key]:
            return "migration: key added with its 2.4.0 default"
        return "OTHER (key added, not a target, not a known migration)"
    if after is ABSENT:
        return "OTHER (key removed)"
    if key in pilot_common._VECTOR_MIGRATIONS and type(before) is str and after == [before]:
        return "migration: scalar written as one-element list"
    if key in ("printer_settings_id", "print_settings_id") and after == before + "(fixture.3mf)":
        return "migration: preset name gets (fixture.3mf) suffix"
    if key == "filament_settings_id" and after == [v + "(fixture.3mf)" for v in before]:
        return "migration: preset name gets (fixture.3mf) suffix"
    if key == "version" and before == "2.3.6" and after == "2.4.0":
        return "migration: version 2.3.6 -> 2.4.0"
    if key == "filament_ids" and before and before[0] == "GFSG99" and after == [""] + before[1:]:
        return "migration: filament_ids slot 1"
    return "OTHER (not a target, not a known migration)"


def show(value):
    return None if value is ABSENT else value


# --------------------------------------------------------------------------- harvest resolution
def file_map(directory: Path) -> dict:
    return {path.relative_to(directory).as_posix(): sha256_file(path)
            for path in sorted(directory.rglob("*")) if path.is_file()}


def resolve(run_id: str) -> dict:
    """Locate a run in the (live) roots; record every copy and whether the copies agree."""
    locations, first = [], None
    for label, root in ROOTS:
        directory = root / run_id
        if directory.is_dir():
            files = file_map(directory)
            if first is None:
                first = files
            locations.append({"root": label, "dir": str(directory), "files": len(files),
                              "identical_to_first_copy": files == first})
    if not locations:
        raise SystemExit("run not found in any root: " + run_id)
    return {"locations": locations, "dir": Path(locations[0]["dir"])}


def machine_evidence(directory: Path) -> dict:
    """Which machine produced a run, from files only (harness/host_guard.py writes the markers)."""
    out = {"execution_host_json": None, "non_guest_marker_in_native_run_log": None, "sandbox": None,
           "output_path": None, "host_guard_lines_in_worker_log": None}
    host = directory / "execution_host.json"
    if host.is_file():
        out["execution_host_json"] = read_json(host)
    run_log = directory / "native_run.log"
    if run_log.is_file():
        out["non_guest_marker_in_native_run_log"] = "NON-GUEST test machine" in run_log.read_text(
            encoding="utf-8", errors="replace")
    worker_log = directory / "native_worker.log"
    if worker_log.is_file():
        out["host_guard_lines_in_worker_log"] = sum(
            1 for line in worker_log.read_text(encoding="utf-8", errors="replace").splitlines() if "host_guard" in line)
    scope = directory / "scope.json"
    if scope.is_file():
        out["output_path"] = read_json(scope).get("output_path")
        for sandbox in ("orca-blackbox-glm", "orca-blackbox-v3-r1"):
            if sandbox in (out["output_path"] or ""):
                out["sandbox"] = sandbox
    testbox = out["execution_host_json"] is not None or out["non_guest_marker_in_native_run_log"] is True
    out["attribution"] = ("non-guest test machine (host_guard ORCA_BB_ALLOW_TESTBOX marker)" if testbox else
                          "not flagged as non-guest by host_guard")
    out["machine_name_recorded"] = (out["execution_host_json"] or {}).get("machine")
    return out


def ledger_evidence(run_id: str) -> dict:
    """What the host-side dispatcher wrote down about a run (machine, commit). Read-only."""
    out = {"ledger_jsonl": None, "logs_mentioning_run": []}
    ledger = DISPATCH / "ledger.jsonl"
    if ledger.is_file():
        for line in ledger.read_text(encoding="utf-8-sig").splitlines():
            if run_id in line:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                out["ledger_jsonl"] = {k: row.get(k) for k in
                                       ("machine", "scenario", "label", "run_id", "commit", "started", "ended", "exit",
                                        "comparison_status", "business_status")}
                break
    logs = DISPATCH / "logs"
    if logs.is_dir():
        out["logs_mentioning_run"] = sorted(p.name for p in logs.glob("*.*")
                                            if p.is_file() and run_id in p.read_text(encoding="utf-8", errors="replace"))
    return out


# --------------------------------------------------------------------------- G-code reader
def scan_gcode(data: bytes) -> dict:
    """Own reader (stdlib only). F is modal; an extruding move is a G0/G1 with positive E and XY
    motion. `feeds_all` counts the F in effect on every extruding move; `feeds_counted` follows
    tools/gcode_facts.py (a feed set by a travel move is not the feature's) so the two can be
    compared. `moves` keeps one tuple per extruding move for baseline-vs-case matching."""
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    sc = {"lines": len(lines), "layers": 0, "z": [], "type_counts": {}, "sections": [], "feeds_all": {},
          "feeds_counted": {}, "moves_by_type": {}, "e_by_type": {}, "moves": [], "header": {}, "echo": {},
          "echo_duplicates": {}, "config_block": None}
    lo = next((i for i, l in enumerate(lines) if l == "; CONFIG_BLOCK_START"), None)
    hi = next((i for i, l in enumerate(lines) if l == "; CONFIG_BLOCK_END"), None)
    sc["config_block"] = {"start_line": None if lo is None else lo + 1, "end_line": None if hi is None else hi + 1,
                          "start_markers": sum(l == "; CONFIG_BLOCK_START" for l in lines),
                          "end_markers": sum(l == "; CONFIG_BLOCK_END" for l in lines)}
    for raw in (lines[lo + 1:hi] if lo is not None and hi is not None else []):
        if raw.startswith("; ") and " = " in raw:
            key, value = raw[2:].split(" = ", 1)
            sc["echo_duplicates"][key] = sc["echo_duplicates"].get(key, 1) + 1
            sc["echo"][key] = value
    for raw in lines:
        for prefix, name in (("; generated by ", "generated_by"), ("; total layer number: ", "total_layer_number"),
                             ("; max_z_height: ", "max_z_height")):
            if raw.startswith(prefix):
                sc["header"][name] = raw[len(prefix):]
    layer, z_cur, kind, feed, feed_ok = 0, None, None, None, False
    absolute_e, e_last, x, y, section = False, None, None, None, None
    for raw in lines[:lo if lo is not None else len(lines)]:
        line = raw.split(";", 1)[0].strip()
        if raw.startswith(";LAYER_CHANGE"):
            layer += 1
            sc["layers"] += 1
        elif raw.startswith(";TYPE:"):
            kind = raw[6:].strip()
            sc["type_counts"][kind] = sc["type_counts"].get(kind, 0) + 1
            section = {"i": len(sc["sections"]) + 1, "type": kind, "layer": layer, "z": z_cur, "feeds": {},
                       "moves": 0, "e": 0.0, "moves_with_travel_feed": 0}
            sc["sections"].append(section)
        elif raw.startswith(";Z:"):
            z_cur = raw[3:].strip()
            sc["z"].append(z_cur)
        if not line:
            continue
        if line[:3] == "M82":
            absolute_e, e_last = True, None
            continue
        if line[:3] == "M83":
            absolute_e = False
            continue
        if line[:2] not in ("G0", "G1", "G2", "G3"):
            continue
        coords = {m.group(1): float(m.group(2)) for m in COORD_RE.finditer(line)}
        found = F_RE.search(line)
        if found:
            feed = _num(found.group(1))
        moving_xy = "X" in coords or "Y" in coords
        length = 0.0
        if moving_xy and x is not None and y is not None:
            length = math.hypot(coords.get("X", x) - x, coords.get("Y", y) - y)
        e = coords.get("E")
        delta = (e - e_last) if (absolute_e and e_last is not None) else e
        extruding = delta is not None and delta > 0 and moving_xy and "Z" not in coords
        if found:
            feed_ok = not (moving_xy and not extruding)
        if extruding:
            feature = kind or "Custom"
            bucket = "first" if layer <= 1 else "other"
            if feed is not None:
                table = sc["feeds_all"].setdefault(feature, {"first": {}, "other": {}})
                table[bucket][feed] = table[bucket].get(feed, 0) + 1
                if feed_ok:
                    counted = sc["feeds_counted"].setdefault(feature, {"first": {}, "other": {}})
                    counted[bucket][feed] = counted[bucket].get(feed, 0) + 1
            sc["moves_by_type"][feature] = sc["moves_by_type"].get(feature, 0) + 1
            sc["e_by_type"][feature] = round(sc["e_by_type"].get(feature, 0.0) + delta, 4)
            if section is not None:
                section["moves"] += 1
                section["e"] = round(section["e"] + delta, 5)
                if feed is not None:
                    section["feeds"][feed] = section["feeds"].get(feed, 0) + 1
                if not feed_ok:
                    section["moves_with_travel_feed"] += 1
            sc["moves"].append((layer, feature, x, y, coords.get("X", x), coords.get("Y", y), feed, e, round(length, 5)))
        if "X" in coords:
            x = coords["X"]
        if "Y" in coords:
            y = coords["Y"]
        if e is not None:
            e_last = e
    return sc


def ranked(table: dict, limit=12):
    """gcode_facts' ordering: most used first, ties in first-seen order."""
    return [[feed, n] for feed, n in sorted(table.items(), key=lambda kv: -kv[1])][:limit]


def cross_check_gcode_facts(path: Path, sc: dict) -> dict:
    """Compare this reader with the repository's tools/gcode_facts.py on the same file."""
    facts = gcode_facts(str(path))
    out = {"gcode_facts_layers": facts["layers"], "own_layers": sc["layers"],
           "gcode_facts_z_first": facts["z_first"], "own_z_first": sc["z"][0] if sc["z"] else None,
           "gcode_facts_z_last": facts["z_last"], "own_z_last": sc["z"][-1] if sc["z"] else None,
           "feature_blocks_equal": {}, "feature_moves_equal": {}, "feeds_top12_equal": {"first": {}, "other": {}},
           "features_only_in": {"gcode_facts": sorted(set(facts["features"]) - set(sc["moves_by_type"])),
                               "own": sorted(set(sc["moves_by_type"]) - set(facts["features"]))}}
    for kind in sorted(set(facts["features"]) & set(sc["moves_by_type"])):
        out["feature_blocks_equal"][kind] = facts["features"][kind]["blocks"] == sc["type_counts"].get(kind, 0)
        out["feature_moves_equal"][kind] = facts["features"][kind]["moves"] == sc["moves_by_type"][kind]
        for bucket in ("first", "other"):
            out["feeds_top12_equal"][bucket][kind] = (
                facts["features"][kind]["feeds"][bucket] == ranked(sc["feeds_counted"].get(kind, {}).get(bucket, {})))
    out["all_equal"] = bool(
        facts["layers"] == sc["layers"] and facts["z_first"] == out["own_z_first"] and facts["z_last"] == out["own_z_last"]
        and not out["features_only_in"]["gcode_facts"] and not out["features_only_in"]["own"]
        and all(out["feature_blocks_equal"].values()) and all(out["feature_moves_equal"].values())
        and all(out["feeds_top12_equal"][b][k] for b in ("first", "other") for k in out["feeds_top12_equal"][b]))
    return out


def feeds_table(sc: dict, types, bucket=None, counted=False) -> collections.Counter:
    """{F (mm/min, float): extruding moves} summed over the given TYPE sections."""
    table = collections.Counter()
    source = sc["feeds_counted"] if counted else sc["feeds_all"]
    for kind in types:
        entry = source.get(kind, {})
        for name, counts in entry.items():
            if bucket is None or name == bucket:
                for feed, n in counts.items():
                    table[float(feed)] += n
    return table


def counts_text(counter) -> dict:
    return {"%g" % f: n for f, n in sorted(counter.items())}


# --------------------------------------------------------------------------- judge (recomputation only)
def run_judge(scenario: str, project: bytes, fixture: bytes, gcode: bytes, baseline: bytes | None):
    """Call the suite's own business judge (harness.native_pilots.verify_business) and report
    its verdict or the exact reason string it raised."""
    try:
        detail = verify_business(scenario, project, fixture, gcode, baseline_gcode=baseline)
    except Exception as exc:  # noqa: BLE001 - the judge signals through _InvalidEvidence(ValueError)
        return {"accepted": False, "exception_type": type(exc).__name__, "reason": str(exc)}
    return {"accepted": True, "reason": None, "detail": detail}


# --------------------------------------------------------------------------- per-run facts
def load_run(run_id: str, row: str, role: str) -> dict:
    where = resolve(run_id)
    d = where["dir"]
    scope, proof = read_json(d / "scope.json"), read_json(d / "proof.json")
    result = read_json(d / "result.json") if (d / "result.json").is_file() else {}
    scenario = scope["scenario"]
    fixture = (d / "input" / "fixture.3mf").read_bytes()
    project = (d / "proof" / "0001.3mf").read_bytes()
    gcode = (d / "exports" / "0001.gcode").read_bytes()
    saved_copy = (d / "projects" / "0001.3mf").read_bytes() if (d / "projects" / "0001.3mf").is_file() else None
    run = {"run_id": run_id, "feishu_row": row, "role": role, "scenario": scenario, "locations": where["locations"],
           "machine": dict(machine_evidence(d), ledger=ledger_evidence(run_id)),
           "case_id": (read_json(d / "manifest.json").get("case_id") if (d / "manifest.json").is_file()
                       else result.get("case_id")),
           "release_verdict_recorded": result.get("release_verdict"),
           "artifacts": {
               "fixture": {"path": str(d / "input" / "fixture.3mf"), "sha256": sha256_bytes(fixture), "bytes": len(fixture)},
               "proof_3mf": {"path": str(d / "proof" / "0001.3mf"), "sha256": sha256_bytes(project), "bytes": len(project)},
               "projects_3mf": ({"sha256": sha256_bytes(saved_copy), "bytes": len(saved_copy)} if saved_copy is not None else None),
               "gcode": {"path": str(d / "exports" / "0001.gcode"), "sha256": sha256_bytes(gcode), "bytes": len(gcode)},
               "proof_json": {k: proof.get(k) for k in ("project_sha256", "gcode_sha256", "sut_sha256", "old_pid",
                                                        "reopened_pid", "old_exit_code", "reopened_exit_code", "reopened_closed")}},
           "fixture_pin": []}
    fixture_sha = run["artifacts"]["fixture"]["sha256"]
    pins = [PIN_NAMES[fixture_sha]] if fixture_sha in PIN_NAMES else []
    pins += ["FIXTURE_SUFFIXES[%r] = %s" % (name, FIXTURE_SUFFIXES[name][0])
             for name, (_p, sha) in FIXTURE_SUFFIXES.items() if sha == fixture_sha]
    pins += ["harness.agent_protocol.LAYER_FIXTURE" if fixture_sha == "ed1ca79dd1dd1de28e9d21fb55efc5cee12f1215fbad9cac07159e5d7687d8ef"
             else "harness.agent_protocol.STD_FIXTURE" if fixture_sha == "36389ec3d26c54fc8d3e6bfccac3097fb080a12ab8fab0f2b7f8038cfc278d94"
             else "NOT a pinned fixture"]
    run["fixture_pin"] = pins
    run["artifacts"]["proof_3mf"]["sha256_matches_receipt"] = sha256_bytes(project) == proof.get("project_sha256")
    run["artifacts"]["gcode"]["sha256_matches_receipt"] = sha256_bytes(gcode) == proof.get("gcode_sha256")
    run["artifacts"]["projects_equals_proof"] = saved_copy == project

    # (1) target keys in the fixture and in the saved project
    original, actual = settings_of(fixture), settings_of(project)
    targets = {}
    for key, expected in FEISHU[row].items():
        index = None
        if isinstance(expected, tuple):
            index, expected = expected

        def pick(table, key=key, index=index):
            if key not in table:
                return ABSENT
            if index is None or not isinstance(table[key], list):
                return table[key]
            return table[key][index] if index < len(table[key]) else ABSENT
        before, after = pick(original), pick(actual)
        entry = {"input": show(before), "saved": show(after), "feishu": expected,
                 "feishu_index": "slot %d of the per-extruder list" % (index + 1) if index is not None else None,
                 "input_full_value": original.get(key), "saved_full_value": actual.get(key)}
        if after is ABSENT or before is ABSENT:
            entry["saved_matches_feishu"] = None
            entry["changed_by_edit"] = None
            entry["note"] = ("key absent from the saved 2.4.0 project config (input: %s)" %
                             ("absent" if before is ABSENT else "present"))
        else:
            # The app stores an EDITED scalar as a one-element list (['700']); compare the way the
            # repository's judge does (harness.param_case_lib.make_verify), i.e. after normalize().
            entry["saved_matches_feishu"] = same(normalize(after), expected)
            entry["changed_by_edit"] = normalize(before) != normalize(after)
            entry["input_normalized"] = normalize(before)
            entry["saved_normalized"] = normalize(after)
            entry["stored_as_one_element_list"] = isinstance(after, list) and len(after) == 1
        targets[key] = entry
    run["targets"] = targets

    # (2) every key that differs, with before/after and its class
    diff = []
    for key in sorted(set(original) | set(actual)):
        before, after = original.get(key, ABSENT), actual.get(key, ABSENT)
        if before == after:
            continue
        diff.append({"key": key, "before": show(before), "after": show(after),
                     "class": classify(key, before, after, FEISHU[row])})
    run["config_diff"] = {
        "fixture_keys": len(original), "saved_keys": len(actual), "differing_keys": len(diff),
        "by_class": dict(collections.Counter(item["class"] for item in diff)),
        "not_target_not_migration": [item for item in diff if item["class"].startswith("OTHER")], "all": diff}
    run["dirty_list"] = {"input": original.get("different_settings_to_system"),
                         "saved": actual.get("different_settings_to_system")}

    # (3) the same keys echoed in the G-code config block
    sc = scan_gcode(gcode)
    run["gcode"] = {"header": sc["header"], "lines": sc["lines"], "config_block": sc["config_block"],
                    "echo_keys": len(sc["echo"]), "echo_key_seen_more_than_once": {k: v for k, v in sc["echo_duplicates"].items() if v > 1},
                    "layers": sc["layers"], "z_first": sc["z"][0] if sc["z"] else None, "z_last": sc["z"][-1] if sc["z"] else None,
                    "z_lines": len(sc["z"]), "type_counts": dict(sorted(sc["type_counts"].items(), key=lambda kv: -kv[1])),
                    "moves_by_type": sc["moves_by_type"], "e_by_type": sc["e_by_type"], "extruding_moves": len(sc["moves"]),
                    "largest_F_on_any_extruding_move": max((float(f) for t in sc["feeds_all"].values() for b in t.values() for f in b), default=None),
                    "cross_check_vs_tools_gcode_facts": None}
    for key, entry in targets.items():
        echo = sc["echo"].get(key)
        echo_all = config_value_all(gcode, key)            # repository function, whole file
        saved = entry["saved_full_value"]
        wanted = ",".join(saved) if isinstance(saved, list) else saved
        entry["gcode_echo"] = echo
        entry["gcode_echo_config_value_all"] = echo_all
        entry["gcode_echo_matches_saved_project"] = None if echo is None or wanted is None else echo == wanted
        entry["gcode_echo_matches_feishu"] = None if echo is None else (
            same(echo.split(",")[0], entry["feishu"]) if entry["feishu_index"] else same(echo, entry["feishu"]))
        if echo is None:
            entry["echo_note"] = "key not echoed in the G-code config block"
    recorded = (result.get("checks") or {}).get("business", {})
    recompute = run_judge(scenario, project, fixture, gcode, None)
    try:
        equal = json.loads(recorded.get("detail")) == recompute.get("detail") if recompute["accepted"] else None
    except (TypeError, ValueError):
        equal = False
    run["judge_recompute_without_baseline"] = dict(
        recompute, recorded_detail_in_result_json=recorded.get("detail"), recorded_status=recorded.get("status"),
        recorded_detail_equals_recomputed=equal)
    run["_scan"], run["_bytes"], run["_settings"] = sc, {"fixture": fixture, "project": project, "gcode": gcode}, (original, actual)
    return run


def overhang_bridge_sections(sc: dict) -> list:
    """(4) every Overhang wall / Bridge-type section with the set of F values on its extruding moves."""
    out = []
    for section in sc["sections"]:
        if section["type"] in OVERHANG_TYPES + BRIDGE_TYPES:
            out.append({"i": section["i"], "type": section["type"], "layer": section["layer"], "z": section["z"],
                        "extruding_moves": section["moves"], "extruded_filament_mm": section["e"],
                        "F_values_mm_min": sorted(float(f) for f in section["feeds"]),
                        "F_values_mm_s": sorted(float(f) / 60 for f in section["feeds"]),
                        "F_move_counts": counts_text({float(f): n for f, n in section["feeds"].items()}),
                        "moves_whose_F_was_set_by_a_travel_move": section["moves_with_travel_feed"]})
    return out


def row264_facts(run: dict) -> dict:
    sc = run["_scan"]
    original, actual = run["_settings"]
    wall = feeds_table(sc, OVERHANG_TYPES)
    wall_first, wall_other = feeds_table(sc, OVERHANG_TYPES, "first"), feeds_table(sc, OVERHANG_TYPES, "other")
    bridge = feeds_table(sc, BRIDGE_TYPES)
    by_type = {t: feeds_table(sc, [t]) for t in sc["feeds_all"]}
    anywhere = collections.Counter()
    for table in by_type.values():
        anywhere.update(table)
    facts = {
        "type_counts": run["gcode"]["type_counts"],
        "has_overhang_wall_sections": any(t in sc["type_counts"] for t in OVERHANG_TYPES),
        "has_bridge_sections": any(t in sc["type_counts"] for t in BRIDGE_TYPES),
        "overhang_wall": {"sections": sum(sc["type_counts"].get(t, 0) for t in OVERHANG_TYPES),
                          "extruding_moves": sum(wall.values()), "F_values_mm_min": sorted(wall),
                          "F_values_mm_s": sorted(f / 60 for f in wall), "F_move_counts": counts_text(wall),
                          "first_layer_F_move_counts": counts_text(wall_first),
                          "other_layers_F_move_counts": counts_text(wall_other)},
        "bridge": {"sections": sum(sc["type_counts"].get(t, 0) for t in BRIDGE_TYPES), "extruding_moves": sum(bridge.values()),
                   "F_values_mm_min": sorted(bridge), "F_values_mm_s": sorted(f / 60 for f in bridge),
                   "F_move_counts": counts_text(bridge)},
        "wall_type_F_move_counts_other_layers": {t: counts_text(dict(feeds_table(sc, [t], "other").most_common(40)))
                                                 for t in sorted(sc["feeds_all"]) if "wall" in t.lower()},
        "feishu_expected_F": {},
        "bridge_speed": {"input": show(original.get("bridge_speed", ABSENT)), "saved": show(actual.get("bridge_speed", ABSENT)),
                         "echo_mm_s": sc["echo"].get("bridge_speed")},
        "related_echo": {k: sc["echo"].get(k) for k in (
            "outer_wall_speed", "inner_wall_speed", "bridge_speed", "internal_bridge_speed", "filament_max_volumetric_speed",
            "filament_flow_ratio", "filament_diameter", "layer_height", "line_width", "slowdown_for_curled_perimeters",
            "enable_overhang_speed", "detect_overhang_wall", "overhang_totally_speed",
            "slow_down_for_layer_cooling", "slow_down_layer_time", "slow_down_min_speed")},
        "sections_overhang_and_bridge": overhang_bridge_sections(sc)}
    prof = profile(sc)["length_by_F"]
    length_at = lambda table_types, f: round(sum(prof.get(t, {}).get(f, 0.0) for t in table_types), 3)  # noqa: E731
    try:
        cooling_floor = 60 * float(sc["echo"]["slow_down_min_speed"].split(",")[0])       # slot 1
    except (KeyError, ValueError):
        cooling_floor = None
    facts["layer_cooling_floor_F_mm_min_slot1"] = cooling_floor
    for value in FEISHU_F:
        nearest = min(sorted(wall), key=lambda f: (abs(f - value), f)) if wall else None
        facts["feishu_expected_F"][str(value)] = {
            "mm_s": value / 60, "moves_on_overhang_wall_at_exactly_this_F": wall.get(float(value), 0),
            "moves_on_overhang_wall_within_1_percent": sum(n for f, n in wall.items() if abs(f - value) <= 0.01 * value),
            "nearest_overhang_wall_F_mm_min": nearest,
            "extruding_moves_anywhere_at_exactly_this_F": anywhere.get(float(value), 0),
            "length_mm_at_exactly_this_F_all_types": length_at(sorted(sc["feeds_all"]), float(value)),
            "length_mm_at_exactly_this_F_overhang_wall_sections": length_at(OVERHANG_TYPES, float(value)),
            "F_equals_60x_slow_down_min_speed (the layer-cooling floor)": (
                None if cooling_floor is None else abs(value - cooling_floor) < 0.5),
            "by_type_at_exactly_this_F": {t: by_type[t].get(float(value), 0) for t in sorted(by_type) if by_type[t].get(float(value))}}
    top = max(wall) if wall else None
    facts["lowest_band"] = {
        "largest_overhang_wall_F_mm_min": top, "largest_overhang_wall_F_mm_s": None if top is None else top / 60,
        "bridge_speed_echo_mm_s": sc["echo"].get("bridge_speed"),
        "largest_overhang_wall_F_equals_bridge_speed_x60": (
            None if top is None or sc["echo"].get("bridge_speed") is None else same(top / 60, sc["echo"].get("bridge_speed"))),
        "source_note": ("upstream tag sm-v2.4.0, src/libslic3r/GCode.cpp:7681 overhang_overlap_levels({90, 75, 50, 25, 13, 0}); "
                        "7719-7720 give the lowest level (0 % overlap) bridge_speed; "
                        "src/libslic3r/GCode/ExtrusionProcessor.hpp:425-447 interpolates and rounds the speed per point")}
    return facts


def row276_facts(run: dict) -> dict:
    """(5) layer count, peak outer-wall feed and volumetric flow with the repository's functions."""
    data = run["_bytes"]["gcode"]
    actual = run["_settings"][1]
    sc = run["_scan"]
    out = {"methods": {"audit": cite(audit_276_flow.inspect), "export": cite(param_comparison._export),
                       "flow_effect": cite(param_comparison._flow_effect), "status": cite(param_comparison.comparison_business_status)}}
    # tools/audit_276_flow.inspect: outer-wall moves after the first layer
    audit = audit_276_flow.inspect(Path(run["artifacts"]["gcode"]["path"]))
    moves, layers = audit.pop("moves"), audit.pop("layers")
    eligible = [m for m in moves if m["length"] >= 1]
    top_speed, top_flow = max(moves, key=lambda m: m["speed"]), max(eligible, key=lambda m: m["flow"])
    out["audit_276_flow"] = dict(
        audit, layer_count=len(layers), first_z=layers[0], last_z=layers[-1], outer_wall_moves=len(moves),
        peak_outer_wall_speed_mm_s=top_speed["speed"], peak_outer_wall_speed_F_mm_min=top_speed["f"],
        peak_flow_mm3_s=top_flow["flow"], peak_flow_move_length_mm=round(top_flow["length"], 4),
        peak_flow_move_speed_mm_s=round(top_flow["speed"], 3), peak_flow_move_e=top_flow["e"],
        peak_x_axis_speed_mm_s=max(abs(m["vx"]) for m in moves),
        moves_over_command_cap=sum(abs(m["vx"]) > audit["command_cap"] for m in moves),
        min_outer_wall_speed_mm_s=min(m["speed"] for m in moves),
        speed_histogram_top=[[s, n] for s, n in collections.Counter(round(m["speed"], 3) for m in moves).most_common(6)])
    # harness.param_comparison._export: the judge's own reader
    wanted = {key: (",".join(actual[key]) if isinstance(actual.get(key), list) else actual.get(key)) for key in FEISHU["276"]}
    try:
        export_layers, export_moves = param_comparison._export(data, wanted, lambda: False)
        first = export_layers[0]
        wall = [(path, speed, e) for path, speed, _fan, e in export_moves if path[1] == "Outer wall" and path[0] != first]
        diameter = float(actual["filament_diameter"][0])
        span = lambda path: math.hypot(path[4] - path[2], path[5] - path[3])  # noqa: E731
        flows = [speed * e * math.pi * (diameter / 2) ** 2 / span(path) for path, speed, e in wall if span(path) >= 1]
        out["param_comparison_export"] = {
            "layer_count": len(export_layers), "first_z": first, "last_z": export_layers[-1],
            "deposition_moves_total": len(export_moves), "outer_wall_moves_after_first_layer": len(wall),
            "peak_outer_wall_speed_mm_s": round(max(s for _p, s, _e in wall), 3),
            "peak_outer_wall_volumetric_mm3_s": round(max(flows), 3),
            "max_x_component_of_outer_wall_speed_mm_s": round(max(s * abs(path[4] - path[2]) / span(path) for path, s, _e in wall), 3),
            "roles_with_deposition": sorted({path[1] for path, *_ in export_moves})}
    except Exception as exc:  # noqa: BLE001
        out["param_comparison_export"] = {"error": "%s: %s" % (type(exc).__name__, exc)}
    own = [float(m[6]) for m in sc["moves"] if m[1] == "Outer wall" and m[0] > 1 and m[6] is not None]
    out["own_reader"] = {"outer_wall_moves_after_first_layer": len(own),
                         "peak_outer_wall_speed_mm_s": max(own) / 60 if own else None}
    try:
        cap = float(sc["echo"]["filament_max_volumetric_speed"].split(",")[0])   # slot 1, read from the G-code
    except (KeyError, ValueError):
        cap = None
    out["arithmetic"] = {
        "feishu_rectangular_section_speed_at_cap_mm_s (15/(0.20x0.42))": round(15 / (0.20 * 0.42), 3),
        "cap/(h*(w-h*(1-pi/4))*flow_ratio) mm_s": round(audit["rounded_speed_at_cap"], 3),
        "slicer_section_area_mm2": round(audit["rounded_area"], 6), "cap_mm3_s_echo_slot1": cap,
        "echo": {k: sc["echo"].get(k) for k in ("filament_max_volumetric_speed", "filament_flow_ratio", "filament_diameter",
                                                "layer_height", "outer_wall_line_width", "outer_wall_speed",
                                                "machine_max_speed_x", "line_width")}}
    peak = out["audit_276_flow"]["peak_outer_wall_speed_mm_s"]
    out["versus_feishu"] = {
        "requested_outer_wall_speed_mm_s": 700, "peak_outer_wall_speed_mm_s": peak,
        "flow_limit_binding": peak < 700,
        "peak_flow_mm3_s": out["audit_276_flow"]["peak_flow_mm3_s"], "feishu_about_178_mm_s": 178.0,
        "within_5_mm_s_of_178": abs(peak - 178) <= 5,
        "repository_rule": "near_feishu_178_mm_s = abs(outer_wall_peak - 178) <= 5 (harness/param_comparison.py _flow_effect)",
        "max_x_component_speed_mm_s": out["audit_276_flow"]["peak_x_axis_speed_mm_s"], "machine_x_limit_mm_s": 500,
        "never_over_500": out["audit_276_flow"]["peak_x_axis_speed_mm_s"] <= 500,
        "x_limit_intervention_exercised": out["audit_276_flow"]["peak_x_axis_speed_mm_s"] > 500,
        "x_limit_note": "with the outer wall held at about 203 mm/s no move approaches 500 mm/s, so the X limit never acts"}
    return out


def paired_comparison(run: dict, baseline: dict) -> dict:
    """The suite's paired #276 judge (baseline G-code = the fixed e9aa6f88 export) plus its status."""
    verdict = run_judge(run["scenario"], run["_bytes"]["project"], run["_bytes"]["fixture"], run["_bytes"]["gcode"],
                        baseline["_bytes"]["gcode"])
    out = dict(verdict, baseline_run=baseline["run_id"])
    if verdict["accepted"]:
        out["comparison_business_status"] = param_comparison.comparison_business_status(verdict["detail"])
    return out


# --------------------------------------------------------------------------- baseline vs case
def latest(scenario: str, root: Path):
    """tools/feishu_rows_compare.py `latest`: the run of a scenario with the greatest started_at_ns."""
    best = None
    for directory in sorted(root.glob("*")):
        if not directory.is_dir():
            continue
        try:
            scope, proc = read_json(directory / "scope.json"), read_json(directory / "process.json")
        except (OSError, ValueError):
            continue
        if scope.get("scenario") == scenario and proc.get("started_at_ns"):
            if best is None or proc["started_at_ns"] > best[0]:
                best = (proc["started_at_ns"], directory)
    return best[1] if best else None


def runs_of(scenario: str, case_fixture_sha256: str) -> list:
    """Every harvested run of one scenario in both roots, with its fixture digest."""
    out = []
    for label, root in ROOTS:
        for directory in sorted(root.glob("*")):
            fixture = directory / "input" / "fixture.3mf"
            if not (directory.is_dir() and fixture.is_file()):
                continue
            try:
                if read_json(directory / "scope.json").get("scenario") != scenario:
                    continue
                started = read_json(directory / "process.json").get("started_at_ns")
                digest = sha256_file(fixture)
            except (OSError, ValueError):
                continue
            out.append({"root": label, "run_id": directory.name, "started_at_ns": started,
                        "started_local": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(started / 1e9)) if started else None,
                        "fixture_sha256": digest, "same_fixture_bytes_as_case": digest == case_fixture_sha256,
                        "has_gcode": (directory / "exports" / "0001.gcode").is_file()})
    out.sort(key=lambda item: item["started_at_ns"] or 0)
    return out


def find_baseline(run: dict, row: str) -> dict:
    """How a default-parameter baseline of the case's own fixture is located.

    Step 1 is what tools/feishu_rows_compare.py does: the row's fixture suffix
    (tools/feishu_model_fixtures.fixture_for) -> harness.agent_protocol.BASELINES[suffix][0] ->
    the newest run of that scenario. Step 2 runs only when that baseline is another fixture's
    (or the suffix has no registered baseline): the save-only control whose fixture bytes are
    the case's (harness.native_pilots.CONTROLS / native_fixture). Either way the baseline is
    accepted only if its input\\fixture.3mf is byte-identical to the case's - a check
    feishu_rows_compare.py does not make."""
    record = feishu_rows(REPO)[int(row)]
    suffix = fixture_for(record["前置条件"], int(row))
    case_sha = run["artifacts"]["fixture"]["sha256"]
    out = {"feishu_precondition": record["前置条件"], "feishu_steps_2_to_4": " / ".join(record["测试步骤"].split("\n")[1:]),
           "fixture_suffix_of_the_row": suffix, "case_fixture_pin": run["fixture_pin"],
           "case_run_fixture_sha256": case_sha, "steps": []}
    scenarios = []
    if suffix in BASELINES:
        scenarios.append(("step 1: the row's registered baseline", [BASELINES[suffix][0]]))
    else:
        out["steps"].append({"step": "step 1: the row's registered baseline", "result": (
            "KeyError - harness.agent_protocol.BASELINES has no entry for suffix %r, so tools/feishu_rows_compare.py "
            "cannot pair this run" % suffix)})
    controls = sorted(sc for sc in CONTROLS if native_fixture(sc)[1] == case_sha)
    scenarios.append(("step 2: the save-only control whose fixture bytes are the case's", controls))
    out["save_only_controls_of_this_fixture"] = controls
    for name, wanted in scenarios:
        found = [dict(item, scenario=scenario) for scenario in wanted for item in runs_of(scenario, case_sha)]
        per_root = [{"root": label, "newest_run": {scenario: (latest(scenario, root).name if latest(scenario, root) else None)
                                                   for scenario in wanted}} for label, root in ROOTS]
        usable = [item for item in found if item["same_fixture_bytes_as_case"] and item["has_gcode"]]
        step = {"step": name, "scenarios": wanted, "newest_run_per_root": per_root, "runs": found,
                "chosen_baseline_run_id": usable[-1]["run_id"] if usable else None}
        if not usable:
            step["result"] = ("no default-parameter G-code of this exact fixture: the run needed is a %s on fixture %s"
                              % ("/".join(wanted), case_sha[:12]))
        out["steps"].append(step)
        if usable:
            out["chosen_baseline_run_id"] = usable[-1]["run_id"]
            out["chosen_baseline_scenario"] = usable[-1]["scenario"]
            out["chosen_baseline_is_the_rows_registered_baseline"] = name.startswith("step 1")
            out["chosen_baseline_runs"] = [[item["root"], item["run_id"]] for item in usable]
            break
    if not out.get("chosen_baseline_run_id"):
        out["status"] = "UNPROVEN: " + "; ".join(s.get("result", "") for s in out["steps"] if s.get("result"))
    return out


def profile(sc: dict) -> dict:
    """Segmentation-tolerant summaries built from the extruding-move list: extruded length and
    filament per TYPE and per (TYPE, layer), and the length extruded at each F value."""
    by_type = collections.defaultdict(lambda: [0.0, 0.0, 0])
    by_type_layer = collections.defaultdict(lambda: [0.0, 0.0, 0])
    length_by_F = collections.defaultdict(collections.Counter)
    for layer, kind, _x0, _y0, _x1, _y1, feed, e, length in sc["moves"]:
        for cell in (by_type[kind], by_type_layer[(kind, layer)]):
            cell[0] += length
            cell[1] += e or 0.0
            cell[2] += 1
        if feed is not None:
            length_by_F[kind][float(feed)] += length
    return {"by_type": dict(by_type), "by_type_layer": dict(by_type_layer), "length_by_F": {k: dict(v) for k, v in length_by_F.items()}}


def compare_one_type(base: dict, case: dict, tolerance=0.05) -> dict:
    """One TYPE, baseline against case: same amount extruded? same feeds? never faster?"""
    la, lb = base["length_by_F"], case["length_by_F"]
    feeds = sorted(set(la) | set(lb))
    out = {"extruding_moves": [base["by_type"][2], case["by_type"][2]],
           "extruded_length_mm": [round(base["by_type"][0], 3), round(case["by_type"][0], 3)],
           "filament_mm": [round(base["by_type"][1], 4), round(case["by_type"][1], 4)],
           "distinct_F_values": [len(la), len(lb)],
           "same_amount_extruded": (abs(base["by_type"][0] - case["by_type"][0]) <= tolerance
                                    and abs(base["by_type"][1] - case["by_type"][1]) <= tolerance),
           "F_values_identical": sorted(la) == sorted(lb),
           "F_length_identical": sorted(la) == sorted(lb) and all(abs(la[f] - lb[f]) <= tolerance for f in la),
           "F_values_only_in_baseline_mm_min": sorted(set(la) - set(lb)),
           "F_values_only_in_case_mm_min": sorted(set(lb) - set(la)),
           "top_F_by_length_mm": {"baseline": [[f, round(la[f], 2)] for f in sorted(la, key=lambda f: -la[f])[:10]],
                                  "case": [[f, round(lb[f], 2)] for f in sorted(lb, key=lambda f: -lb[f])[:10]]}}
    if not out["F_length_identical"]:
        out["largest_length_change_at_one_F_mm"] = round(max(abs(la.get(f, 0) - lb.get(f, 0)) for f in feeds), 3)
    cumulative_a = cumulative_b = 0.0
    behind = 0.0
    for f in feeds:                       # feeds ascend, so the running sums are the CDFs
        cumulative_a += la.get(f, 0.0)
        cumulative_b += lb.get(f, 0.0)
        behind = max(behind, cumulative_a - cumulative_b)
    out["case_never_faster_in_aggregate"] = behind <= tolerance
    out["largest_cumulative_length_at_or_below_each_F_added_by_the_case_mm"] = round(behind, 3)
    return out


def compare_exports(base: dict, case: dict) -> dict:
    """Baseline export against case export with this script's reader (both files)."""
    a, b = base["_scan"], case["_scan"]
    pa, pb = profile(a), profile(b)
    out = {"baseline_run": base["run_id"], "case_run": case["run_id"],
           "baseline_machine": base["machine"]["attribution"], "case_machine": case["machine"]["attribution"],
           "baseline_gcode_sha256": base["artifacts"]["gcode"]["sha256"], "case_gcode_sha256": case["artifacts"]["gcode"]["sha256"],
           "same_sut_sha256": base["artifacts"]["proof_json"]["sut_sha256"] == case["artifacts"]["proof_json"]["sut_sha256"],
           "same_fixture_sha256": base["artifacts"]["fixture"]["sha256"] == case["artifacts"]["fixture"]["sha256"],
           "layers": [a["layers"], b["layers"]], "layer_z_identical": a["z"] == b["z"],
           "type_counts_identical": a["type_counts"] == b["type_counts"],
           "extruding_moves": [len(a["moves"]), len(b["moves"])], "per_type": {}}
    # geometry and flow, independent of how paths are split into moves
    cells_a, cells_b = pa["by_type_layer"], pb["by_type_layer"]
    off = [list(key) for key in sorted(set(cells_a) | set(cells_b), key=lambda k: (str(k[0]), k[1]))
           if key not in cells_a or key not in cells_b
           or abs(cells_a[key][0] - cells_b[key][0]) > 0.05 or abs(cells_a[key][1] - cells_b[key][1]) > 0.05]
    out["type_layer_cells"] = [len(cells_a), len(cells_b)]
    out["type_layer_cells_whose_length_or_filament_differ"] = len(off)
    out["type_layer_cells_differing_first_10"] = off[:10]
    out["same_paths_and_flow_in_every_type_and_layer"] = not off
    sa, sb = settings_of(base["_bytes"]["project"]), settings_of(case["_bytes"]["project"])
    ea, eb = a["echo"], b["echo"]
    out["saved_settings_differing_keys"] = [
        {"key": k, "baseline": sa.get(k), "case": sb.get(k)} for k in sorted(set(sa) | set(sb)) if sa.get(k) != sb.get(k)]
    out["gcode_echo_differing_keys"] = [
        {"key": k, "baseline": ea.get(k), "case": eb.get(k)} for k in sorted(set(ea) | set(eb)) if ea.get(k) != eb.get(k)]
    for kind in sorted(set(pa["length_by_F"]) | set(pb["length_by_F"])):
        empty = {"by_type": [0.0, 0.0, 0], "length_by_F": {}}
        out["per_type"][kind] = compare_one_type(
            {"by_type": pa["by_type"].get(kind, [0.0, 0.0, 0]), "length_by_F": pa["length_by_F"].get(kind, {})},
            {"by_type": pb["by_type"].get(kind, [0.0, 0.0, 0]), "length_by_F": pb["length_by_F"].get(kind, {})})
    # exact per-move statement, possible only when both files split the paths identically
    n = min(len(a["moves"]), len(b["moves"]))
    mismatches = sum(1 for i in range(n) if a["moves"][i][:6] != b["moves"][i][:6])
    out["move_geometry_sequence_identical"] = mismatches == 0 and len(a["moves"]) == len(b["moves"])
    out["move_geometry_mismatches"] = mismatches
    out["moves_by_type"] = {k: [a["moves_by_type"].get(k, 0), b["moves_by_type"].get(k, 0)]
                            for k in sorted(set(a["moves_by_type"]) | set(b["moves_by_type"]))}
    if out["move_geometry_sequence_identical"]:
        tally = collections.defaultdict(lambda: {"F_equal": 0, "F_slower_in_case": 0, "F_faster_in_case": 0})
        for ma, mb in zip(a["moves"], b["moves"]):
            if ma[6] == mb[6]:
                tally[ma[1]]["F_equal"] += 1
            elif float(mb[6]) < float(ma[6]):
                tally[ma[1]]["F_slower_in_case"] += 1
            else:
                tally[ma[1]]["F_faster_in_case"] += 1
        for kind, counts in tally.items():
            out["per_type"][kind]["per_move"] = counts
    out["per_move_match_available"] = out["move_geometry_sequence_identical"]
    for group, types in (("bridge", BRIDGE_TYPES), ("overhang_wall", OVERHANG_TYPES)):
        ta, tb = feeds_table(a, types), feeds_table(b, types)
        la = collections.Counter()
        lb = collections.Counter()
        for kind in types:
            la.update(pa["length_by_F"].get(kind, {}))
            lb.update(pb["length_by_F"].get(kind, {}))
        out[group + "_extruding_moves"] = [sum(ta.values()), sum(tb.values())]
        out[group + "_F_move_counts"] = [counts_text(ta), counts_text(tb)]
        out[group + "_F_values_mm_min"] = [sorted(ta), sorted(tb)]
        out[group + "_length_mm_by_F"] = [counts_text({f: round(v, 2) for f, v in la.items()}),
                                          counts_text({f: round(v, 2) for f, v in lb.items()})]
        out[group + "_F_values_identical"] = sorted(ta) == sorted(tb)
        out[group + "_F_move_counts_identical"] = dict(ta) == dict(tb)
        out[group + "_extruded_length_mm"] = [round(sum(la.values()), 3), round(sum(lb.values()), 3)]
        out[group + "_F_length_identical"] = sorted(la) == sorted(lb) and all(abs(la[f] - lb[f]) <= 0.05 for f in la)
    out["layer_cooling_slowdown"] = layer_cooling_summary(a, b)
    types = sorted(set(a["feeds_all"]) | set(b["feeds_all"]))
    out["types_whose_F_changed"] = [t for t in types if not out["per_type"].get(t, {}).get("F_length_identical")]
    out["types_whose_F_unchanged"] = [t for t in types if out["per_type"].get(t, {}).get("F_length_identical")]
    out["types_where_case_is_faster_in_aggregate"] = [t for t in types if not out["per_type"].get(t, {}).get("case_never_faster_in_aggregate")]
    out["non_overhang_types_F_unchanged"] = {t: out["per_type"].get(t, {}).get("F_length_identical")
                                             for t in types if t not in OVERHANG_TYPES}
    return out


def _mean_feed_by_layer(sc: dict, types) -> dict:
    """{layer: length-weighted mean F (mm/min)} over the extruding moves of the given TYPEs, after the first layer."""
    acc = collections.defaultdict(lambda: [0.0, 0.0])
    for layer, kind, _x0, _y0, _x1, _y1, feed, _e, length in sc["moves"]:
        if kind in types and layer > 1 and feed is not None:
            acc[layer][0] += length
            acc[layer][1] += length * float(feed)
    return {layer: total / span for layer, (span, total) in acc.items() if span > 0}


def layer_cooling_summary(a: dict, b: dict) -> dict:
    """Layer by layer, how the feeds of the features the overhang speeds do not govern (infill, gap
    fill, surfaces) moved between two exports. `slow_down_for_layer_cooling` scales every feature
    of a layer towards a minimum layer time, so slower walls leave less to scale down."""
    names = set(a["feeds_all"]) | set(b["feeds_all"])
    walls = {t for t in names if "wall" in t.lower() or "bridge" in t.lower()}
    others = {t for t in names if t not in walls and t != "Custom"}
    ia, ib = _mean_feed_by_layer(a, others), _mean_feed_by_layer(b, others)
    wa, wb = _mean_feed_by_layer(a, walls), _mean_feed_by_layer(b, walls)
    rows = [(layer, ib[layer] / ia[layer], wb[layer] / wa[layer] if wa.get(layer) else None)
            for layer in sorted(set(ia) & set(ib)) if ia[layer] > 0]
    higher = [r for r in rows if r[1] > 1.0005]
    lower = [r for r in rows if r[1] < 0.9995]
    return {
        "features_compared": sorted(others), "layers_compared": len(rows),
        "layers_non_wall_feed_unchanged": len(rows) - len(higher) - len(lower),
        "layers_non_wall_feed_higher_in_case": len(higher), "layers_non_wall_feed_lower_in_case": len(lower),
        "non_wall_feed_ratio_range_on_higher_layers": ([round(min(r[1] for r in higher), 4), round(max(r[1] for r in higher), 4)]
                                                        if higher else None),
        "wall_feed_ratio_range_on_higher_layers": ([round(min(r[2] for r in higher), 4), round(max(r[2] for r in higher), 4)]
                                                    if higher and all(r[2] is not None for r in higher) else None),
        "echo_slow_down_for_layer_cooling": [a["echo"].get("slow_down_for_layer_cooling"), b["echo"].get("slow_down_for_layer_cooling")],
        "echo_slow_down_layer_time": [a["echo"].get("slow_down_layer_time"), b["echo"].get("slow_down_layer_time")],
        "echo_slow_down_min_speed": [a["echo"].get("slow_down_min_speed"), b["echo"].get("slow_down_min_speed")],
        "per_layer": [[layer, round(ratio, 4), None if wall is None else round(wall, 4)] for layer, ratio, wall in rows]}


def _in_thumbnail(lines) -> list:
    """[is this line inside a ; THUMBNAIL_BLOCK?] for every line of a G-code file."""
    flags, inside = [], False
    for line in lines:
        if line.startswith("; THUMBNAIL_BLOCK_START"):
            inside = True
        flags.append(inside)
        if line.startswith("; THUMBNAIL_BLOCK_END"):
            inside = False
    return flags


def _line_class(x: str, y, inside) -> str:
    """Why two G-code lines differ. `y` is None for a line present on one side only."""
    if x.startswith("; generated by ") and (y is None or y.startswith("; generated by ")):
        return "header timestamp"
    if inside[0] or inside[1]:
        return "thumbnail image data"
    if "object" in x and y is not None and "object" in y and x.split(" id:")[0] == y.split(" id:")[0]:
        return "object id in '; (stop) printing object ... id:N copy 0'"
    if x.startswith("; estimated printing time") or (y or "").startswith("; estimated printing time"):
        return "estimated printing time"
    if x.startswith("M73 ") or (y or "").startswith("M73 "):
        return "remaining-time estimate (M73)"
    return "OTHER (G-code body)"


def body_line_diff(base: dict, case: dict) -> dict:
    """Classify every differing line of two G-code files (sequence diff; lengths may differ)."""
    import difflib
    la = base["_bytes"]["gcode"].decode("utf-8", errors="replace").split("\n")
    lb = case["_bytes"]["gcode"].decode("utf-8", errors="replace").split("\n")
    out = {"lines": [len(la), len(lb)], "same_line_count": len(la) == len(lb), "differing_line_pairs": 0,
           "differing_lines_a": 0, "differing_lines_b": 0, "classes": {}, "examples": [], "other_differing_lines": []}
    thumb_a, thumb_b = _in_thumbnail(la), _in_thumbnail(lb)      # thumbnail state of every line, whole files
    blocks = [op for op in difflib.SequenceMatcher(None, la, lb, autojunk=False).get_opcodes() if op[0] != "equal"]
    out["differing_blocks"] = len(blocks)
    for _tag, i1, i2, j1, j2 in blocks:
        left, right = la[i1:i2], lb[j1:j2]
        out["differing_lines_a"] += len(left)
        out["differing_lines_b"] += len(right)
        for k in range(max(len(left), len(right))):
            x = left[k] if k < len(left) else ""
            y = right[k] if k < len(right) else None
            if y is None and not x:
                continue
            label = _line_class(x, y, (thumb_a[i1 + k] if k < len(left) else False,
                                       thumb_b[j1 + k] if k < len(right) else False))
            out["classes"][label] = out["classes"].get(label, 0) + 1
            out["differing_line_pairs"] += 1
            if label.startswith("OTHER"):
                out["other_differing_lines"].append({"line_a": i1 + k + 1, "a": x[:160],
                                                     "line_b": j1 + k + 1 if k < len(right) else None, "b": (y or "")[:160]})
            elif len(out["examples"]) < 4:
                out["examples"].append({"line_a": i1 + k + 1, "class": label, "a": x.strip()[:90], "b": (y or "").strip()[:90]})
    out["gcode_body_identical"] = not out["other_differing_lines"]
    out["other_differing_lines_count"] = len(out["other_differing_lines"])
    out["other_differing_lines"] = out["other_differing_lines"][:12]
    return out


def settings_identical(base: dict, case: dict) -> dict:
    sa, sb = settings_of(base["_bytes"]["project"]), settings_of(case["_bytes"]["project"])
    ea, eb = base["_scan"]["echo"], case["_scan"]["echo"]
    return {"saved_project_settings_keys": [len(sa), len(sb)], "saved_project_settings_identical_all_keys": sa == sb,
            "saved_settings_differing_keys": [k for k in sorted(set(sa) | set(sb)) if sa.get(k) != sb.get(k)],
            "gcode_echo_block_keys": [len(ea), len(eb)], "gcode_echo_block_identical_all_keys": ea == eb,
            "gcode_echo_differing_keys": [k for k in sorted(set(ea) | set(eb)) if ea.get(k) != eb.get(k)],
            "proof_3mf_bytes_identical": base["_bytes"]["project"] == case["_bytes"]["project"],
            "gcode_bytes_identical": base["_bytes"]["gcode"] == case["_bytes"]["gcode"]}


# --------------------------------------------------------------------------- printing
def short_f(values) -> str:
    values = list(values)
    if not values:
        return "-"
    if len(values) <= 8:
        return "/".join(("%g" % v) for v in values)
    return "%g..%g (%d distinct)" % (values[0], values[-1], len(values))


def target_text(run: dict) -> tuple:
    """'key=input->saved[]' when the edit changed it, 'key=saved' when it already had that value;
    [] marks a value the app stores as a one-element list."""
    saved, echo = [], []
    for key, entry in run["targets"].items():
        name = SHORT[key]
        if entry["saved"] is None and "note" in entry:
            saved.append("%s=ABSENT" % name)
        else:
            text = "%s%s" % (entry["saved_normalized"], "[]" if entry.get("stored_as_one_element_list") else "")
            saved.append("%s=%s->%s" % (name, entry["input_normalized"], text) if entry["changed_by_edit"] else "%s=%s" % (name, text))
        echo.append("%s=%s" % (name, entry["gcode_echo"] if entry["gcode_echo"] is not None else "not-echoed"))
    return " ".join(saved), " ".join(echo)


def print_types(per_type: dict, limit=5) -> None:
    for kind, v in sorted(per_type.items(), key=lambda kv: -max(kv[1]["extruded_length_mm"])):
        extra = ""
        if "per_move" in v:
            extra = " | per move: equal %d slower %d faster %d" % (
                v["per_move"]["F_equal"], v["per_move"]["F_slower_in_case"], v["per_move"]["F_faster_in_case"])
        print("      %-24s moves %6d/%-6d length %10.2f/%-10.2f F-identical=%-5s never-faster=%-5s%s" % (
            kind, v["extruding_moves"][0], v["extruding_moves"][1], v["extruded_length_mm"][0], v["extruded_length_mm"][1],
            v["F_length_identical"], v["case_never_faster_in_aggregate"], extra))
        print("           F by length baseline: %s" % " ".join("%g:%.1f" % (f, n) for f, n in v["top_F_by_length_mm"]["baseline"][:limit]))
        print("           F by length case     : %s" % " ".join("%g:%.1f" % (f, n) for f, n in v["top_F_by_length_mm"]["case"][:limit]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=str(HERE / "facts.json"))
    parser.add_argument("--verbose", action="store_true", help="print every overhang / bridge section")
    options = parser.parse_args()
    started = time.time()
    facts = {"generated_at_local": time.strftime("%Y-%m-%d %H:%M:%S"), "script": str(Path(__file__).resolve()),
             "command": "set PYTHONDONTWRITEBYTECODE=1 && python -B \"%s\"" % Path(__file__).resolve(),
             "repo": str(REPO), "repo_head": git_head(REPO),
             "roots": [{"label": label, "path": str(root)} for label, root in ROOTS],
             "feishu_rows": {}, "methods": {
                 "judge": cite(verify_business), "judge_param_family": cite(pilot_common.inspect_preserved_settings),
                 "config_echo": cite(config_value_all), "gcode_facts": cite(gcode_facts),
                 "baseline_lookup": "mirror of tools/feishu_rows_compare.py `latest` (a script with module-level main(); not imported)"},
             "row_plan_264_276": {}, "runs": {}, "baselines": {}, "pairs": {}, "cross_run_identity": {}}
    rows = feishu_rows(REPO)
    snapshot = REPO / "docs/runs/evidence/feishu-tblKjIVV8KA53kUQ-2026-11-22/tblKjIVV8KA53kUQ_20261122_024056_171.ndjson"
    for row in ("264", "276"):
        record = rows[int(row)]
        facts["feishu_rows"][row] = dict(
            {k: record.get(k) for k in ("record_id", "用例编号", "用例标题", "前置条件", "测试步骤", "预期结果")},
            snapshot=str(snapshot), snapshot_sha256=sha256_file(snapshot))
    for suffix, items in row_plan(REPO).items():
        for number, scenario in items:
            if number in (264, 276):
                facts["row_plan_264_276"][str(number)] = {"fixture_suffix": suffix, "scenario": scenario}

    runs = facts["runs"]
    for run_id, row, role in RUNS:
        runs[run_id] = load_run(run_id, row, role)
        print("read %-8s %-34s row %-4s %s" % (run_id[:8], runs[run_id]["scenario"], row, role))

    def analyse(run):
        if run["gcode"]["cross_check_vs_tools_gcode_facts"] is None:
            run["gcode"]["cross_check_vs_tools_gcode_facts"] = cross_check_gcode_facts(
                Path(run["artifacts"]["gcode"]["path"]), run["_scan"])
        if run["feishu_row"] == "264" and "row264" not in run:
            run["row264"] = row264_facts(run)

    def cross(a, b):
        facts["cross_run_identity"]["%s vs %s" % (a["run_id"][:8], b["run_id"][:8])] = dict(
            settings_identical(a, b), body=body_line_diff(a, b), a_run=a["run_id"], b_run=b["run_id"],
            a_scenario=a["scenario"], b_scenario=b["scenario"],
            a_machine=a["machine"]["attribution"], b_machine=b["machine"]["attribution"])

    for run in runs.values():
        analyse(run)

    # ---- row 276: the fixed comparison baseline
    first = runs["ec032d7cc54844f1a6f970a6990fa032"]
    quality = runs["eebdf238d72e401b9636b161bad6c465"]
    strength = runs["5359abcadafa48a2bc493ee3acf56114"]
    fixed = runs["e9aa6f88eca940b385bfe531703f644e"]
    facts["baselines"]["276"] = {
        "fixed_baseline_run": param_comparison._BASELINES["276"][0],
        "pinned_gcode_sha256": param_comparison._BASELINES["276"][1],
        "harvested_gcode_sha256": fixed["artifacts"]["gcode"]["sha256"],
        "pinned_digest_matches_harvest": param_comparison._BASELINES["276"][1] == fixed["artifacts"]["gcode"]["sha256"],
        "same_fixture_bytes_as_cases": all(r["artifacts"]["fixture"]["sha256"] == fixed["artifacts"]["fixture"]["sha256"]
                                           for r in (first, quality, strength)),
        "baseline_machine": fixed["machine"]["attribution"], "baseline_sandbox": fixed["machine"]["sandbox"],
        "baseline_ledger_commit": (fixed["machine"]["ledger"].get("ledger_jsonl") or {}).get("commit")}
    for run in (first, quality, strength):
        run["row276"] = row276_facts(run)
        run["paired_with_fixed_baseline"] = paired_comparison(run, fixed)
        facts["pairs"]["%s vs %s" % (run["run_id"][:8], fixed["run_id"][:8])] = compare_exports(fixed, run)
    cross(first, quality)
    cross(strength, quality)

    # ---- row 264: the default-parameter baseline of each case's own fixture
    cube = [runs[k] for k in ("7484bd43c9114b5b8f8d098a6ac978e3", "8e207463943845c2a4564a47efc54d64",
                              "19d6103223264b2c8f21a0b8c5f76d1e")]
    fdmt = runs["b697f7c24c6c49849c05b22c2a8ed1a3"]
    for run in [fdmt] + cube:
        found = find_baseline(run, "264")
        run["baseline_lookup"] = found
        base_id = found.get("chosen_baseline_run_id")
        run["baseline_comparison"] = None
        if not base_id:
            continue
        if base_id not in runs:
            runs[base_id] = load_run(base_id, "264", "default-parameter baseline (found by find_baseline)")
            analyse(runs[base_id])
        base = runs[base_id]
        run["baseline_comparison"] = compare_exports(base, run)
        proc = read_json(Path(base["locations"][0]["dir"]) / "process.json")
        facts["baselines"].setdefault("264", {})[run["run_id"]] = {
            "case_fixture_pin": run["fixture_pin"], "case_scenario": run["scenario"],
            "baseline_run_id": base_id, "baseline_scenario": base["scenario"],
            "baseline_is_the_rows_registered_baseline": found.get("chosen_baseline_is_the_rows_registered_baseline"),
            "baseline_machine": base["machine"]["attribution"],
            "baseline_machine_name_recorded": base["machine"]["machine_name_recorded"],
            "baseline_sandbox": base["machine"]["sandbox"], "baseline_root_read": base["locations"][0]["root"],
            "baseline_started_local": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(proc["started_at_ns"] / 1e9)),
            "baseline_commit_recorded": (base["machine"]["ledger"].get("ledger_jsonl") or {}).get("commit"),
            "same_fixture_bytes": base["artifacts"]["fixture"]["sha256"] == run["artifacts"]["fixture"]["sha256"],
            "same_sut_sha256": base["artifacts"]["proof_json"]["sut_sha256"] == run["artifacts"]["proof_json"]["sut_sha256"],
            "lookup_steps": [{k: v for k, v in step.items() if k != "runs"} for step in found["steps"]]}
    cross(cube[1], cube[0])
    cross(cube[2], cube[0])
    cross(cube[2], cube[1])

    # ---- per case run: the flags each statement of the report rests on
    for run in runs.values():
        if run["role"] != "case":
            continue
        t, jr = run["targets"], run["judge_recompute_without_baseline"]
        per = run["per_row"] = {"expectation_1": {
            "targets_matching_feishu": [k for k, v in t.items() if v["saved_matches_feishu"] is True],
            "targets_not_matching_feishu": [k for k, v in t.items() if v["saved_matches_feishu"] is False],
            "targets_that_cannot_match_key_absent_in_2.4.0": [k for k, v in t.items() if v["saved_matches_feishu"] is None],
            "targets_already_at_the_feishu_value_in_the_fixture (no edit to see)": [k for k, v in t.items() if v["changed_by_edit"] is False],
            "targets_changed_by_the_edit": [k for k, v in t.items() if v["changed_by_edit"] is True],
            "gcode_echo_matches_saved_project": {k: v["gcode_echo_matches_saved_project"] for k, v in t.items()},
            "business_judge_recomputed_accepted": jr["accepted"], "judge_reason": jr["reason"],
            "recorded_detail_equals_recomputed": jr["recorded_detail_equals_recomputed"],
            "unrelated_settings_changed": run["config_diff"]["not_target_not_migration"],
            "gcode_bytes": run["artifacts"]["gcode"]["bytes"], "gcode_layers": run["gcode"]["layers"]}}
        if run["feishu_row"] == "264":
            r, cmp_ = run["row264"], run["baseline_comparison"]
            base = runs[run["baseline_lookup"].get("chosen_baseline_run_id")] if cmp_ else None
            wall_types = [k for k in ("Outer wall", "Inner wall", "Overhang wall", "Bridge") if k in run["gcode"]["type_counts"]]
            per["expectation_2"] = {
                "overhang_wall_sections_F_move_counts": r["overhang_wall"]["F_move_counts"],
                "feishu_F_moves_in_overhang_wall_sections": {k: v["moves_on_overhang_wall_at_exactly_this_F"]
                                                             for k, v in r["feishu_expected_F"].items()},
                "feishu_F_moves_any_type": {k: v["extruding_moves_anywhere_at_exactly_this_F"] for k, v in r["feishu_expected_F"].items()},
                "feishu_F_moves_by_type": {k: v["by_type_at_exactly_this_F"] for k, v in r["feishu_expected_F"].items()},
                "feishu_F_moves_any_type_in_default_baseline": (
                    {k: v["extruding_moves_anywhere_at_exactly_this_F"] for k, v in base["row264"]["feishu_expected_F"].items()}
                    if base else None),
                "feishu_F_length_mm_any_type": {k: v["length_mm_at_exactly_this_F_all_types"] for k, v in r["feishu_expected_F"].items()},
                "feishu_F_length_mm_any_type_in_default_baseline": (
                    {k: v["length_mm_at_exactly_this_F_all_types"] for k, v in base["row264"]["feishu_expected_F"].items()}
                    if base else None),
                "feishu_F_is_the_layer_cooling_floor": {k: v["F_equals_60x_slow_down_min_speed (the layer-cooling floor)"]
                                                        for k, v in r["feishu_expected_F"].items()},
                "layer_cooling_floor_F_mm_min_slot1": r["layer_cooling_floor_F_mm_min_slot1"],
                "lowest_band": r["lowest_band"],
                "distinct_F_values_on_wall_and_bridge_moves": {k: len(run["_scan"]["feeds_all"].get(k, {}).get("other", {}))
                                                               for k in wall_types}}
            per["expectation_3"] = {"baseline_run_id": run["baseline_lookup"].get("chosen_baseline_run_id"),
                                    "lookup_status": run["baseline_lookup"].get("status")}
            if cmp_:
                per["expectation_3"].update({
                    "same_fixture_bytes": cmp_["same_fixture_sha256"], "same_sut": cmp_["same_sut_sha256"],
                    "baseline_machine": cmp_["baseline_machine"], "case_machine": cmp_["case_machine"],
                    "saved_settings_differing_keys": [x["key"] for x in cmp_["saved_settings_differing_keys"]],
                    "gcode_echo_differing_keys": [x["key"] for x in cmp_["gcode_echo_differing_keys"]],
                    "same_paths_and_flow_in_every_type_and_layer": cmp_["same_paths_and_flow_in_every_type_and_layer"],
                    "bridge": {k: cmp_["per_type"].get("Bridge", {}).get(k) for k in (
                        "extruding_moves", "extruded_length_mm", "F_values_identical", "F_length_identical",
                        "F_values_only_in_baseline_mm_min", "F_values_only_in_case_mm_min", "top_F_by_length_mm",
                        "case_never_faster_in_aggregate")},
                    "overhang_wall_sections": {k: cmp_["per_type"].get("Overhang wall", {}).get(k) for k in (
                        "extruding_moves", "extruded_length_mm", "F_length_identical", "top_F_by_length_mm")},
                    "types_whose_F_changed": cmp_["types_whose_F_changed"],
                    "types_whose_F_unchanged": cmp_["types_whose_F_unchanged"],
                    "types_where_case_is_faster_in_aggregate": cmp_["types_where_case_is_faster_in_aggregate"],
                    "non_overhang_types_F_unchanged": cmp_["non_overhang_types_F_unchanged"],
                    "layer_cooling_slowdown": {k: v for k, v in cmp_["layer_cooling_slowdown"].items() if k != "per_layer"}})
        else:
            r = run["row276"]
            pair = facts["pairs"]["%s vs %s" % (run["run_id"][:8], fixed["run_id"][:8])]
            per["expectation_2"] = dict(r["versus_feishu"], arithmetic=r["arithmetic"])
            per["expectation_3"] = {
                "max_x_component_speed_mm_s": r["versus_feishu"]["max_x_component_speed_mm_s"],
                "never_over_500": r["versus_feishu"]["never_over_500"],
                "x_limit_intervention_exercised": r["versus_feishu"]["x_limit_intervention_exercised"],
                "outer_wall_paths_and_flow_same_as_fixed_baseline": pair["per_type"].get("Outer wall", {}).get("same_amount_extruded"),
                "move_geometry_sequence_identical_vs_fixed_baseline": pair["move_geometry_sequence_identical"],
                "types_whose_F_changed_vs_fixed_baseline": pair["types_whose_F_changed"],
                "paired_judge": run["paired_with_fixed_baseline"]}

    # ---- print
    bar = "=" * 132
    print("\n" + bar)
    print("PART A TABLE")
    for run in runs.values():
        saved, echo = target_text(run)
        m = run["machine"]
        machine = m["machine_name_recorded"] or ("non-guest test machine" if m["attribution"].startswith("non-guest") else "guest (not flagged)")
        if run["feishu_row"] == "264":
            ow, br = short_f(run["row264"]["overhang_wall"]["F_values_mm_min"]), short_f(run["row264"]["bridge"]["F_values_mm_min"])
        else:
            ow = br = "n/a"
        print("-" * 132)
        print("%s | %s | %s | %s" % (run["run_id"], machine, run["scenario"], run["role"]))
        print("   roots=%s%s | sandbox=%s | ledger commit=%s | ledger machine=%s" % (
            ",".join(loc["root"] for loc in run["locations"]),
            "" if all(loc["identical_to_first_copy"] for loc in run["locations"]) else " (COPIES DIFFER)", m["sandbox"],
            (m["ledger"].get("ledger_jsonl") or {}).get("commit"), (m["ledger"].get("ledger_jsonl") or {}).get("machine")))
        print("   saved : %s" % saved)
        print("   echo  : %s" % echo)
        print("   layers=%s (z %s..%s) | overhang-wall F: %s | bridge F: %s" % (
            run["gcode"]["layers"], run["gcode"]["z_first"], run["gcode"]["z_last"], ow, br))
        print("   TYPE sections: %s" % json.dumps(run["gcode"]["type_counts"], ensure_ascii=False))
        print("   judge without baseline: accepted=%s reason=%s | recorded detail == recomputed: %s | gcode_facts cross-check all_equal=%s" % (
            run["judge_recompute_without_baseline"]["accepted"], run["judge_recompute_without_baseline"]["reason"],
            run["judge_recompute_without_baseline"]["recorded_detail_equals_recomputed"],
            run["gcode"]["cross_check_vs_tools_gcode_facts"]["all_equal"]))
        d = run["config_diff"]
        print("   config diff input->saved: %d of %d keys differ: %s | OTHER=%d" % (
            d["differing_keys"], d["fixture_keys"], json.dumps(d["by_class"], ensure_ascii=False), len(d["not_target_not_migration"])))
        if "row276" in run:
            a = run["row276"]
            print("   276: layers=%d | peak outer wall %.3f mm/s (F%s) | peak flow %.3f mm3/s | peak |vx| %.3f mm/s | moves over X cap %d" % (
                a["audit_276_flow"]["layer_count"], a["audit_276_flow"]["peak_outer_wall_speed_mm_s"],
                a["audit_276_flow"]["peak_outer_wall_speed_F_mm_min"], a["audit_276_flow"]["peak_flow_mm3_s"],
                a["audit_276_flow"]["peak_x_axis_speed_mm_s"], a["audit_276_flow"]["moves_over_command_cap"]))
            print("   276 judge's reader: %s" % json.dumps(a["param_comparison_export"], ensure_ascii=False))
            print("   276 own reader: %s" % json.dumps(a["own_reader"]))
            print("   276 arithmetic: %s" % json.dumps({k: v for k, v in a["arithmetic"].items() if k != "echo"}, ensure_ascii=False))
            print("   276 echo: %s" % json.dumps(a["arithmetic"]["echo"], ensure_ascii=False))
            p = run["paired_with_fixed_baseline"]
            print("   276 paired with %s: accepted=%s reason=%s | %s" % (
                p["baseline_run"], p["accepted"], p["reason"],
                json.dumps({k: p["detail"][k] for k in (
                    "pair_status", "layer_count", "baseline_outer_wall_peak_mm_s", "outer_wall_peak_mm_s",
                    "outer_wall_peak_mm3_s", "near_feishu_178_mm_s", "x_limit_effect")} if p["accepted"] else {})))
            print("   276 comparison_business_status: %s" % json.dumps(p.get("comparison_business_status"), ensure_ascii=False))
        if "row264" in run:
            r = run["row264"]
            print("   264 overhang-wall F move counts: %s | bridge F move counts: %s" % (
                json.dumps(r["overhang_wall"]["F_move_counts"]), json.dumps(r["bridge"]["F_move_counts"])))
            print("   264 Feishu F on overhang-wall moves: %s | on any extruding move: %s" % (
                json.dumps({k: v["moves_on_overhang_wall_at_exactly_this_F"] for k, v in r["feishu_expected_F"].items()}),
                json.dumps({k: v["extruding_moves_anywhere_at_exactly_this_F"] for k, v in r["feishu_expected_F"].items()})))
            print("   264 Feishu F by type: %s" % json.dumps({k: v["by_type_at_exactly_this_F"] for k, v in r["feishu_expected_F"].items()}))
            print("   264 Feishu F length mm anywhere: %s | is the layer-cooling floor (slow_down_min_speed x 60 = %s): %s" % (
                json.dumps({k: v["length_mm_at_exactly_this_F_all_types"] for k, v in r["feishu_expected_F"].items()}),
                r["layer_cooling_floor_F_mm_min_slot1"],
                json.dumps({k: v["F_equals_60x_slow_down_min_speed (the layer-cooling floor)"] for k, v in r["feishu_expected_F"].items()})))
            print("   264 lowest band: %s" % json.dumps({k: r["lowest_band"][k] for k in (
                "largest_overhang_wall_F_mm_min", "largest_overhang_wall_F_mm_s", "bridge_speed_echo_mm_s",
                "largest_overhang_wall_F_equals_bridge_speed_x60")}))
            print("   264 echo: %s" % json.dumps(r["related_echo"], ensure_ascii=False))
            if run["role"] == "case":
                lk = run["baseline_lookup"]
                print("   264 baseline lookup: row suffix=%r | save-only controls of this fixture=%s | chosen=%s (%s) | is the row's registered baseline=%s" % (
                    lk["fixture_suffix_of_the_row"], lk["save_only_controls_of_this_fixture"], lk.get("chosen_baseline_run_id"),
                    lk.get("chosen_baseline_scenario"), lk.get("chosen_baseline_is_the_rows_registered_baseline")))
                for step in lk["steps"]:
                    if "result" in step:
                        print("      %s -> %s" % (step["step"], step["result"]))
                    for item in step.get("runs", []):
                        print("      %-12s %s run %s started %s same-fixture=%s gcode=%s" % (
                            step["step"][:6], item["root"], item["run_id"], item["started_local"],
                            item["same_fixture_bytes_as_case"], item["has_gcode"]))
                c = run["baseline_comparison"]
                if c:
                    print("   264 vs baseline %s [%s] (case [%s]; same fixture %s, same sut %s): layers %s | extruding moves %s" % (
                        c["baseline_run"], c["baseline_machine"], c["case_machine"], c["same_fixture_sha256"], c["same_sut_sha256"],
                        c["layers"], c["extruding_moves"]))
                    print("      same paths and flow in every (type, layer): %s (cells %s, differing %d) | move sequences identical: %s" % (
                        c["same_paths_and_flow_in_every_type_and_layer"], c["type_layer_cells"],
                        c["type_layer_cells_whose_length_or_filament_differ"], c["move_geometry_sequence_identical"]))
                    print("      saved settings differing keys: %s" % [x["key"] for x in c["saved_settings_differing_keys"]])
                    print("      gcode echo differing keys: %s" % [x["key"] for x in c["gcode_echo_differing_keys"]])
                    print("      BRIDGE sections  F values baseline %s | case %s | F-identical=%s | length by F baseline %s | case %s" % (
                        short_f(c["bridge_F_values_mm_min"][0]), short_f(c["bridge_F_values_mm_min"][1]),
                        c["bridge_F_length_identical"], json.dumps(c["bridge_length_mm_by_F"][0]) if len(c["bridge_length_mm_by_F"][0]) <= 14 else "(see json)",
                        json.dumps(c["bridge_length_mm_by_F"][1]) if len(c["bridge_length_mm_by_F"][1]) <= 14 else "(see json)"))
                    print("      OVERHANG sections F values baseline %s | case %s | F-identical=%s | moves %s" % (
                        short_f(c["overhang_wall_F_values_mm_min"][0]), short_f(c["overhang_wall_F_values_mm_min"][1]),
                        c["overhang_wall_F_length_identical"], c["overhang_wall_extruding_moves"]))
                    print_types(c["per_type"])
                    lc = c["layer_cooling_slowdown"]
                    print("      layer cooling: slow_down_for_layer_cooling=%s slow_down_layer_time=%s slow_down_min_speed=%s (baseline | case)" % (
                        lc["echo_slow_down_for_layer_cooling"], lc["echo_slow_down_layer_time"], lc["echo_slow_down_min_speed"]))
                    print("      non-wall feeds per layer: compared %d | unchanged %d | higher in case %d | lower in case %d | ratio on higher layers %s | wall ratio there %s" % (
                        lc["layers_compared"], lc["layers_non_wall_feed_unchanged"], lc["layers_non_wall_feed_higher_in_case"],
                        lc["layers_non_wall_feed_lower_in_case"], lc["non_wall_feed_ratio_range_on_higher_layers"],
                        lc["wall_feed_ratio_range_on_higher_layers"]))
                    print("      types whose F changed: %s" % c["types_whose_F_changed"])
                    print("      types whose F unchanged: %s" % c["types_whose_F_unchanged"])
                    print("      types where the case is faster in aggregate: %s" % c["types_where_case_is_faster_in_aggregate"])
                if options.verbose:
                    for section in r["sections_overhang_and_bridge"]:
                        print("      #%-5d %-13s layer %3d z %-6s moves %4d F %s" % (
                            section["i"], section["type"], section["layer"], section["z"], section["extruding_moves"],
                            section["F_values_mm_min"]))
    print(bar)
    print("CROSS-RUN IDENTITY")
    for key, value in facts["cross_run_identity"].items():
        print("   %s [%s vs %s]: saved settings identical (all %d keys)=%s | echo block identical (all %d keys)=%s" % (
            key, value["a_scenario"], value["b_scenario"], value["saved_project_settings_keys"][0],
            value["saved_project_settings_identical_all_keys"], value["gcode_echo_block_keys"][0],
            value["gcode_echo_block_identical_all_keys"]))
        print("      machines: %s  vs  %s" % (value["a_machine"], value["b_machine"]))
        print("      g-code lines %s differing lines a/b=%s classes=%s | G-code body identical=%s" % (
            value["body"]["lines"], [value["body"]["differing_lines_a"], value["body"]["differing_lines_b"]],
            json.dumps(value["body"]["classes"], ensure_ascii=False), value["body"]["gcode_body_identical"]))
        for item in value["body"]["other_differing_lines"][:6]:
            print("         a line %s: %r | b line %s: %r" % (item["line_a"], item["a"][:76], item["line_b"], item["b"][:76]))
    print(bar)
    print("BASELINE 276: %s" % json.dumps(facts["baselines"]["276"], ensure_ascii=False))
    print("BASELINE 264:")
    for rid, value in facts["baselines"].get("264", {}).items():
        print("   %s: %s" % (rid[:8], json.dumps({k: v for k, v in value.items() if k != "lookup_steps"}, ensure_ascii=False)))
    for key, pair in facts["pairs"].items():
        print("PAIR %s: layers %s | same paths+flow every (type,layer)=%s (cells differing %d) | move sequences identical=%s | extruding moves %s" % (
            key, pair["layers"], pair["same_paths_and_flow_in_every_type_and_layer"],
            pair["type_layer_cells_whose_length_or_filament_differ"], pair["move_geometry_sequence_identical"],
            pair["extruding_moves"]))
        print("      saved settings differ=%s | echo differ=%s" % (
            [x["key"] for x in pair["saved_settings_differing_keys"]], [x["key"] for x in pair["gcode_echo_differing_keys"]]))
        print_types(pair["per_type"])
        print("      types whose F changed: %s | unchanged: %s | case faster in aggregate: %s" % (
            pair["types_whose_F_changed"], pair["types_whose_F_unchanged"], pair["types_where_case_is_faster_in_aggregate"]))

    for run in runs.values():
        for private in ("_scan", "_bytes", "_settings"):
            run.pop(private, None)
    Path(options.out).write_text(json.dumps(facts, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("%s\nwrote %s (%d bytes) in %.1f s" % (bar, options.out, os.path.getsize(options.out), time.time() - started))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
