"""Offline negative controls for the Mac walls oracle (task A6).

verify_walls_differential() in runner/macos_project_copy.py accepted run
306d3efe against the committed control baseline after the Windows-track
oracle had rejected run ffe0c6e4. A criterion only counts if it also
rejects: this tool hands the UNCHANGED function the real saved projects and
constructed ones and records PASS / REJECT + error code for each.

Purely offline: no GUI, no Orca launch, no SSH. A constructed project is a
copy whose Metadata/project_settings.config entry is rewritten and
repacked; such files are written only to a temp directory and reach
results.json as digests plus their planted changes.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
from datetime import datetime, timezone
import hashlib
import inspect
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from harness import pilot_common
from harness.agent_protocol import LAYER_FIXTURE, LAYER_FIXTURE_SHA256
from harness.gcode_check import config_value_all
from runner import macos_project_copy as oracle

SETTINGS = "Metadata/project_settings.config"
EVIDENCE = REPO / "docs/runs/evidence/mac-walls-a6-negative-controls-2026-11-23"
A5_EVIDENCE = REPO / "docs/runs/evidence/mac-walls-a5-2026-11-23"
RUNS = REPO / "artifacts/mac_project_copy"
MAC_RUNS = {"A": ("306d3efe6882427e806afaaf9e2ad7f1", "wall-3-copy.3mf", "walls_run_306d3efe_result.json"),
            "C": ("ffe0c6e45c2c456b94e904ded891c1ac", "wall-3-copy.3mf", "walls_run_ffe0c6e4_nongreen_result.json")}
# Layer-goal SHADOW run of the same Mac build: another real save, used only as a swapped baseline (G12-G14).
LAYER_RUN = ("0a24557a0c5f49809b14ad6a52d47c5e", "layer-024-copy.3mf")
# Build on record for the win11-test guest (docs/runs/gui-layer-candidate-2026-11-20.md); not re-measured here.
OTHER_BUILD = {"version": "2.4.0", "executable_sha256": "5c48644d7da18b50636ceeee4ef9fd2eaf6d4e8ac05bd88752f40e3717fc47bf"}
DIGEST_MISMATCH = "Committed walls control baseline digest mismatch"
FOREIGN_BASELINE = "Walls control baseline was recorded on a different Orca build"
TARGET, ADDITION, MANIFEST, UNRELATED = ("pilot_wall_loops_target", "mac_walls_unknown_addition",
                                         "pilot_dirty_manifest_out_of_scope", "mac_walls_unrelated_setting_changed")
CODES = (DIGEST_MISMATCH, FOREIGN_BASELINE, TARGET, ADDITION, MANIFEST, UNRELATED)
MANIFEST_KEY, EDIT_KEY, CONTROL_EDIT_KEY = "different_settings_to_system", "wall_loops", "initial_layer_print_height"
# Five ordinary process parameters: one float, two ints, one percent, one vector-migrated key.
FIVE = {"layer_height": "0.24", "top_shell_layers": "5", "bottom_shell_layers": "4",
        "sparse_infill_density": "30%", "travel_speed": ["400"]}
TEMPLATE_GCODE = {"machine_start_gcode", "machine_end_gcode", "change_filament_gcode", "machine_pause_gcode"}
PHASES = ("baseline", "edit", "reopen")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def brief(value, limit=96):
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else f"{text[:limit]}...(len {len(text)}, sha256 {digest(text.encode())[:12]})"


def describe(path, raw):
    shown = ("(in-memory construction)" if path is None else
             path.relative_to(REPO).as_posix() if path.is_relative_to(REPO) else str(path))
    return {"path": shown, "sha256": digest(raw), "bytes": len(raw)}


def entry(raw, name=SETTINGS):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        return archive.read(name)


def settings_of(raw):
    return json.loads(entry(raw))


def settings_diff(base_raw, raw):
    before, after = settings_of(base_raw), settings_of(raw)
    with zipfile.ZipFile(io.BytesIO(base_raw)) as first, zipfile.ZipFile(io.BytesIO(raw)) as second:
        others = (first.namelist() == second.namelist()
                  and all(first.read(name) == second.read(name) for name in first.namelist() if name != SETTINGS))
    return {"added": sorted(set(after) - set(before)), "removed": sorted(set(before) - set(after)),
            "changed": sorted(key for key in before if key in after and before[key] != after[key]),
            "other_entries_identical": others}


def rewrite(base_raw, values=None, drop=()):
    """Copy a 3mf replacing only Metadata/project_settings.config, repacked with the original entry metadata."""
    settings = json.loads(entry(base_raw))
    for key in drop:
        del settings[key]
    settings.update(values or {})
    original = entry(base_raw)
    newline = "\r\n" if b"\r\n" in original else "\n"
    text = (json.dumps(settings, indent=4, ensure_ascii=False).replace("\n", newline) + newline).encode("utf-8")
    with zipfile.ZipFile(io.BytesIO(base_raw)) as source:
        entries = [(copy.copy(info), text if info.filename == SETTINGS else source.read(info.filename))
                   for info in source.infolist()]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as target:
        for info, data in entries:
            target.writestr(info, data)
    return buffer.getvalue()


def manifest_value(settings, add=(), remove=()):
    keys = [key for key in settings[MANIFEST_KEY][0].split(";") if key and key not in remove]
    keys += [key for key in add if key not in keys]
    return [";".join(keys), *settings[MANIFEST_KEY][1:]]


def judge(fixture_raw, raw, sut, root=None):
    """One call of the unchanged criterion; root only redirects where the baseline is read from."""
    committed = oracle.ROOT
    outcome = {"verdict": "PASS", "exception": None, "code": None, "detail": None, "error": None}
    if root is not None:
        oracle.ROOT = root
    try:
        oracle.verify_walls_differential(raw, fixture_raw, sut)
    except Exception as error:  # every outcome is recorded, none is hidden
        message = str(error)
        code = next((known for known in CODES if message == known or message.startswith(known + ":")), None)
        outcome = {"verdict": "REJECT", "exception": type(error).__name__, "code": code,
                   "detail": message[len(code) + 1:] if code and ":" in message else None, "error": message}
    finally:
        oracle.ROOT = committed
    return outcome


def as_expected(outcome, expect):
    return all(outcome[field] == value for field, value in expect.items())


def rejects(code, detail=None, **extra):
    return {"verdict": "REJECT", "code": code, **({"detail": detail} if detail is not None else {}), **extra}


def line_of(path, needle):
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if needle in line:
            return f"{path.relative_to(REPO).as_posix()}:{number}"
    raise SystemExit(f"marker not found in {path}: {needle}")


def old_oracle(fixture_raw, raw):
    """The Windows-track oracle that rejected run ffe0c6e4, on the same bytes."""
    try:
        pilot_common.inspect_preserved_settings(settings_of(raw), settings_of(fixture_raw), allowed_changes={EDIT_KEY: "3"})
    except ValueError as error:
        return {"verdict": "REJECT", "error": str(error)}
    return {"verdict": "PASS", "error": None}


def migration_kind(before, after, key):
    if isinstance(before, str) and isinstance(after, list) and after == [before]:
        return "vector_migration_scalar_to_1_element_list"
    if key in TEMPLATE_GCODE:
        return "machine_template_gcode_refresh"
    return {"version": "schema_version", "print_settings_id": "preset_rename",
            "filename_format": "filename_template_placeholder"}.get(key, "default_value_change")


def exemption_rows(fixture_raw, control_raw, raw):
    fixture, control, saved = settings_of(fixture_raw), settings_of(control_raw), settings_of(raw)
    rows = [{"key": key, "clause": "added_key_equal_to_control", "kind": "new_schema_key", "fixture": None,
             "saved": brief(saved[key]), "control": brief(control[key])}
            for key in sorted(set(saved) - set(fixture))]
    rows += [{"key": key, "clause": "changed_key_equal_to_control",
              "kind": migration_kind(fixture[key], saved[key], key), "fixture": brief(fixture[key]),
              "saved": brief(saved[key]), "control": brief(control[key])}
             for key in fixture if key not in (EDIT_KEY, MANIFEST_KEY) and saved[key] != fixture[key]]
    return rows


def echo_form(value):
    return ",".join(str(item).replace("\n", "\\n") for item in (value if isinstance(value, list) else [value]))


def echo_lines(raw):
    return [number for number, line in enumerate(raw.decode("utf-8").splitlines(), 1)
            if line.startswith(f"; {EDIT_KEY} =")]


def config_block(raw):
    lines = raw.decode("utf-8").split("\n")
    return lines[lines.index("; CONFIG_BLOCK_START") + 1:lines.index("; CONFIG_BLOCK_END")]


def config_echo(raw):
    """key -> echoed values, from the slicer's '; key = value' lines inside its config block.

    The slicer writes a double quote inside a value as \\" ; that escaping is undone here."""
    found = {}
    for line in config_block(raw):
        match = re.match(r"^; (\S+) = (.*)$", line)
        if match:
            found.setdefault(match.group(1), []).append(match.group(2).replace('\\"', '"'))
    return found


def config_echo_diff(before_raw, after_raw):
    """What the slicer itself echoed as configuration, before vs after the edit (a channel independent of the project file)."""
    before, after = config_block(before_raw), config_block(after_raw)
    if len(before) != len(after):
        return {"same_block_length": False, "baseline_lines": len(before), "edited_lines": len(after)}
    differing = [{"block_line": number, "baseline": first, "edited": second}
                 for number, (first, second) in enumerate(zip(before, after), 1) if first != second]
    old, new = config_echo(before_raw), config_echo(after_raw)
    changed = sorted(key for key in set(old) | set(new) if old.get(key) != new.get(key))
    return {"same_block_length": True, "block_lines": len(before), "keys_echoed": len(old),
            "differing_lines": len(differing), "difference": differing, "keys_whose_echo_changed": changed,
            "only_wall_loops_and_its_manifest_entry_differ": changed == sorted([EDIT_KEY, MANIFEST_KEY])}


def echo_agreement(raw, settings, keys):
    """Does the slice's own configuration echo carry the same value the saved project holds for these keys?"""
    echoed = {key: values for key in keys if (values := config_echo(raw).get(key))}
    agree = [key for key in echoed if echoed[key] == [echo_form(settings[key])]]
    return {"keys_checked": len(keys), "keys_echoed": len(echoed), "keys_agree": len(agree),
            "disagreeing": sorted(set(echoed) - set(agree)), "not_echoed": sorted(set(keys) - set(echoed))}


def load_run(spec):
    run_id, copy_name, *committed = spec
    run_dir = RUNS / run_id
    result_raw = (run_dir / "result.json").read_bytes()
    result = json.loads(result_raw)
    guest = result["guest"]
    raw = (run_dir / copy_name).read_bytes()
    if not digest(raw) == guest["saved_sha256"] == guest["slice_receipts"]["edited"]["project_sha256"]:
        raise SystemExit(f"run {run_id}: saved project is not the bytes its receipt and slice were bound to")
    facts = {"result": result, "guest": guest, "raw": raw, "dir": run_dir, "copy": copy_name, "result_raw": result_raw,
             "sut": {key: guest["sut"][key] for key in ("version", "executable_sha256")}}
    if committed:
        facts["committed_copy_identical"] = (A5_EVIDENCE / committed[0]).read_bytes() == result_raw
    return facts


def provenance(facts):
    guest, run_dir = facts["guest"], facts["dir"]
    edited, baseline = (run_dir / "edited.gcode").read_bytes(), (run_dir / "baseline.gcode").read_bytes()
    readback = {phase: guest["phases"][phase]["wall"] for phase in PHASES}
    receipt = guest["slice_receipts"]["edited"]
    try:
        plate = oracle.verify_plate(run_dir, "edited", receipt, guest["phases"]["reopen"]["pid"], guest["saved_sha256"], "0.4", 68)
        plate = {"verdict": "PASS", "layer_count": plate["layer_count"], "origin": plate["origin"]}
    except ValueError as error:
        plate = {"verdict": "REJECT", "error": str(error)}
    return {"readback": readback, "readback_pids": {phase: guest["phases"][phase]["pid"] for phase in PHASES},
            "gcode_echo_edited": config_value_all(edited, EDIT_KEY), "gcode_echo_edited_lines": echo_lines(edited),
            "gcode_echo_baseline": config_value_all(baseline, EDIT_KEY), "gcode_echo_baseline_lines": echo_lines(baseline),
            "edited_gcode": describe(run_dir / "edited.gcode", edited),
            "baseline_gcode": describe(run_dir / "baseline.gcode", baseline),
            "edited_receipt": {key: receipt[key] for key in ("phase", "pid", "source", "size", "sha256", "project_sha256")},
            "edited_gcode_digest_equals_receipt": digest(edited) == receipt["sha256"],
            "slicer_config_echo_before_vs_after": config_echo_diff(baseline, edited),
            "saved_artifact_replay": {"reopened_fields_2_3_3": [readback[phase] for phase in PHASES] == ["2", "3", "3"],
                                      "edited_plate": plate,
                                      "echo_is_exactly_3": set(config_value_all(edited, EDIT_KEY)) == {"3"}}}


def git(*args):
    return subprocess.run(["git", "-C", str(REPO), *args], check=True, capture_output=True).stdout


def main():
    parser = argparse.ArgumentParser(description="Offline negative controls for verify_walls_differential (task A6)")
    parser.add_argument("--out", type=Path, default=EVIDENCE / "results.json")
    args = parser.parse_args()
    work = Path(tempfile.mkdtemp(prefix="orca-bb-walls-a6."))
    criterion_path = REPO / "runner/macos_project_copy.py"
    worker = REPO / "runner/macos/project_copy.py"
    fixture_path, control_path, meta_path = (REPO / LAYER_FIXTURE, REPO / "runner/macos/walls_control.3mf",
                                             REPO / "runner/macos/walls_control.json")
    fixture_raw, control_raw, meta_text = fixture_path.read_bytes(), control_path.read_bytes(), meta_path.read_text()
    meta = json.loads(meta_text)
    bindings = {"fixture_equals_LAYER_FIXTURE_SHA256": digest(fixture_raw) == LAYER_FIXTURE_SHA256,
                "control_equals_metadata_digest": digest(control_raw) == meta["control_saved_sha256"]}
    if not all(bindings.values()):
        raise SystemExit("Repository fixture or committed control digest mismatch")
    committed_before = (digest(control_raw), digest(meta_text.encode()))
    saves = {name: load_run(spec) for name, spec in MAC_RUNS.items()}
    layer = load_run(LAYER_RUN)
    mac = saves["A"]["sut"]
    if not mac == saves["C"]["sut"] == layer["sut"] == meta["sut"]:
        raise SystemExit("Runs, control and criterion metadata do not name the same Orca build")
    fixture, control = settings_of(fixture_raw), settings_of(control_raw)
    run_a = settings_of(saves["A"]["raw"])
    clean_manifest = manifest_value(fixture)
    walls_manifest = manifest_value(fixture, add=[EDIT_KEY])
    # What an open-without-edit Save of this build would hold: the control minus its own edit.
    migration_only = rewrite(control_raw, {CONTROL_EDIT_KEY: fixture[CONTROL_EDIT_KEY], MANIFEST_KEY: clean_manifest})
    bases = {"fixture": (fixture_path, fixture_raw), "control": (control_path, control_raw),
             "A": (saves["A"]["dir"] / saves["A"]["copy"], saves["A"]["raw"]),
             "C": (saves["C"]["dir"] / saves["C"]["copy"], saves["C"]["raw"]), "migration_only": (None, migration_only)}
    reserialization = {name: entry(rewrite(raw)) == entry(raw) for name, (_, raw) in bases.items()}
    controls = []

    def record(cid, title, expect, required, note, info, sut, root, raw):
        outcome = judge(fixture_raw, raw, sut, root)
        controls.append({"id": cid, "title": title, "required": required, "expect": expect, "note": note, "input": info,
                         "sut": sut, "baseline": "redirected temp copy" if root else "committed",
                         "outcome": outcome, "as_expected": as_expected(outcome, expect)})
        return outcome

    def real(cid, title, name, expect, *, sut=None, root=None, required=False, note=""):
        path, raw = bases[name]
        return record(cid, title, expect, required, note,
                      {"kind": "real" if path is not None else "constructed_in_memory", "file": describe(path, raw)},
                      sut or mac, root, raw)

    def constructed(cid, title, name, values=None, expect=None, *, drop=(), root=None, required=True, note=""):
        values = dict(values or {})
        base_path, base_raw = bases[name]
        base = settings_of(base_raw)
        if any(key in base and base[key] == value for key, value in values.items()):
            raise SystemExit(f"{cid}: a planted value equals the base; the control would be vacuous")
        raw = rewrite(base_raw, values, drop)
        path = work / f"{cid}.3mf"
        path.write_bytes(raw)
        diff = settings_diff(base_raw, raw)
        planted = sorted([*(key for key in values if base.get(key) != values[key]), *drop])
        info = {"kind": "constructed", "file": describe(path, raw), "base": {"id": name, **describe(base_path, base_raw)},
                "planted": {key: [brief(base.get(key)), brief(value)] for key, value in values.items()},
                "removed": list(drop), "settings_diff": diff,
                "construction_verified": (sorted(diff["added"] + diff["changed"] + diff["removed"]) == planted
                                          and diff["other_entries_identical"])}
        return record(cid, title, expect, required, note, info, mac, root, raw)

    # A, B, C: the real files.
    real("A", "saved project of run 306d3efe (the SHADOW run)", "A", {"verdict": "PASS"}, required=True)
    real("B", "committed control baseline judged as if it were the saved project", "control", rejects(TARGET), required=True)
    constructed("B2", "hardened B: baseline + wall_loops=3, manifest untouched", "control", {EDIT_KEY: "3"}, rejects(MANIFEST),
                note="the baseline alone only trips the wall_loops gate; this reaches the differential")
    constructed("B3", "hardened B: baseline + wall_loops=3 + manifest recording only wall_loops", "control",
                {EDIT_KEY: "3", MANIFEST_KEY: walls_manifest}, rejects(UNRELATED, CONTROL_EDIT_KEY),
                note="the control's own edit key is never exempted")
    real("C", "saved project of first run ffe0c6e4 (recorded NON_GREEN under the old oracle)", "C", {"verdict": "PASS"},
         note="report-only by the task: either outcome is acceptable; PASS is the prediction from the key-level diff")

    # D: an unrelated parameter without the walls edit (literal), then riding along with wall_loops=3.
    constructed("D", "control copy, initial_layer_print_height 0.44 -> 0.5, wall_loops still 2", "control",
                {CONTROL_EDIT_KEY: "0.5"}, rejects(TARGET),
                note="rejected by the wall_loops gate; the same kind of change riding along with wall_loops=3 is D2-D4")
    constructed("D2", "A + initial_layer_print_height 0.4 -> 0.44 (the control's own edit value)", "A",
                {CONTROL_EDIT_KEY: "0.44"}, rejects(UNRELATED, CONTROL_EDIT_KEY))
    constructed("D3", "A + line_width 0.82 -> 0.9 (plain key outside the migration)", "A", {"line_width": "0.9"},
                rejects(UNRELATED, "line_width"))
    constructed("D4", "A + inner_wall_speed ['150'] -> ['160'] (migrated key, third value)", "A",
                {"inner_wall_speed": ["160"]}, rejects(UNRELATED, "inner_wall_speed"))
    constructed("D5", "A + unknown key", "A", {"z_fake_key": "1"}, rejects(ADDITION, "z_fake_key"))
    constructed("D6", "A + project_schema_version '1' -> '2' (one of the 24 added keys)", "A",
                {"project_schema_version": "2"}, rejects(ADDITION, "project_schema_version"))
    constructed("D7", "A - top_shell_layers (key deleted)", "A", drop=["top_shell_layers"], expect=rejects(None, exception="KeyError"),
                note="rejected, but uncoded: run() would record the bare key name as the error")
    constructed("D8", "A + manifest also listing layer_height (value unchanged)", "A",
                {MANIFEST_KEY: manifest_value(run_a, add=["layer_height"])}, rejects(MANIFEST))
    constructed("D9", "A + manifest without mixed_filament_definitions", "A",
                {MANIFEST_KEY: manifest_value(run_a, remove=["mixed_filament_definitions"])}, rejects(MANIFEST))
    constructed("D10", "A + top_shell_layers '3' -> 3 (int)", "A", {"top_shell_layers": 3}, rejects(UNRELATED, "top_shell_layers"))
    constructed("D11", "fixture + wall_loops=3 + travel_speed -> ['400'] (no migration at all)", "fixture",
                {EDIT_KEY: "3", "travel_speed": ["400"]}, rejects(UNRELATED, "travel_speed"))
    constructed("D12", "A - different_settings_to_system (manifest key deleted)", "A", drop=[MANIFEST_KEY],
                expect=rejects(None, exception="KeyError"), note="rejected, but uncoded (same path as D7)")

    # E: wall_loops=3 plus five other parameters.
    constructed("E", "control copy + wall_loops=3 + five other parameters (manifest untouched)", "control",
                {EDIT_KEY: "3", **FIVE}, rejects(UNRELATED, "bottom_shell_layers"),
                note="first violation only: bottom_shell_layers sorts before the manifest key")
    constructed("E2", "control copy with its own edit undone + wall_loops=3 + manifest + five other parameters",
                "migration_only", {EDIT_KEY: "3", MANIFEST_KEY: walls_manifest, **FIVE}, rejects(UNRELATED, "bottom_shell_layers"))
    constructed("E3", "A + the same five other parameters", "A", dict(FIVE), rejects(UNRELATED, "bottom_shell_layers"))
    for number, (key, value) in enumerate(sorted(FIVE.items()), 4):
        constructed(f"E{number}", f"A + {key} alone", "A", {key: value}, rejects(UNRELATED, key))
    order = sorted(FIVE)
    for number, gone in enumerate(range(1, len(order)), 9):
        constructed(f"E{number}", "control copy, own edit undone + wall_loops=3 + manifest + the five parameters minus "
                    + ", ".join(order[:gone]), "migration_only",
                    {EDIT_KEY: "3", MANIFEST_KEY: walls_manifest, **{key: FIVE[key] for key in order[gone:]}},
                    rejects(UNRELATED, order[gone]), note="peeling: removing the reported violator uncovers the next one")

    # F: wall_loops=4 and other wrong target values.
    constructed("F", "control copy + wall_loops=4", "control", {EDIT_KEY: "4"}, rejects(TARGET))
    constructed("F2", "A with wall_loops 3 -> 4", "A", {EDIT_KEY: "4"}, rejects(TARGET))
    constructed("F3", "A with wall_loops '03'", "A", {EDIT_KEY: "03"}, rejects(TARGET))
    constructed("F4", "A with wall_loops 3 (int)", "A", {EDIT_KEY: 3}, rejects(TARGET))
    constructed("F5", "A without the wall_loops key", "A", drop=[EDIT_KEY], expect=rejects(TARGET))

    # G: build identity and a replaced baseline file.
    real("G1", "A judged as the win11-test build on record (2.4.0, other executable)", "A", rejects(FOREIGN_BASELINE),
         sut=OTHER_BUILD, required=True)
    real("G2", "A judged with only the version changed", "A", rejects(FOREIGN_BASELINE),
         sut={**mac, "version": OTHER_BUILD["version"]}, required=True)
    real("G3", "A judged with only the executable digest changed", "A", rejects(FOREIGN_BASELINE),
         sut={**mac, "executable_sha256": OTHER_BUILD["executable_sha256"]}, required=True)
    real("G4", "2.3.6 fixture (an older build's save) judged under the Mac build identity", "fixture", rejects(TARGET),
         required=True, note="identity assumed equal, so the content gate decides")
    constructed("G5", "fixture + wall_loops=3 (2.3.6 schema, no migration) under the Mac build identity", "fixture",
                {EDIT_KEY: "3"}, {"verdict": "PASS"}, required=False,
                note="boundary: the criterion does not require the migration signature when the identity is presented as equal")

    def swapped(name, control_bytes, **changes):
        root = work / f"baseline-{name}"
        (root / "runner/macos").mkdir(parents=True)
        (root / "runner/macos/walls_control.3mf").write_bytes(control_bytes)
        (root / "runner/macos/walls_control.json").write_text(json.dumps({**meta, **changes}, indent=1) + "\n")
        return root

    plain = swapped("fixture-plain", fixture_raw)
    redigested = swapped("fixture-redigested", fixture_raw, control_saved_sha256=digest(fixture_raw))
    foreign = swapped("fixture-foreign", fixture_raw, control_saved_sha256=digest(fixture_raw), sut=OTHER_BUILD)
    poisoned = swapped("poisoned", saves["A"]["raw"], control_saved_sha256=digest(saves["A"]["raw"]))
    layer_root = swapped("layer-run", layer["raw"], control_saved_sha256=digest(layer["raw"]))
    real("G6", "baseline file replaced by the 2.3.6 fixture, metadata untouched; A judged", "A", rejects(DIGEST_MISMATCH),
         root=plain, required=True, note="a swapped file alone trips the digest, not the identity lock")
    real("G7", "baseline replaced and re-digested (2.3.6 fixture), SUT unchanged; A judged", "A", rejects(ADDITION),
         root=redigested, required=True,
         note="not an identity rejection: the json's SUT is untouched, the content decides; the named key is whichever "
              "added key comes first in set order")
    real("G8", "baseline replaced, re-digested and re-attributed to the 2.4.0 build; A judged", "A", rejects(FOREIGN_BASELINE),
         root=foreign, required=True)
    real("G9", "poisoned baseline (A's own project); an open-without-edit save judged", "migration_only", rejects(TARGET),
         root=poisoned, required=True)
    constructed("G10", "poisoned baseline (A's own project); A + five other parameters judged", "A", dict(FIVE),
                rejects(UNRELATED, "bottom_shell_layers"), root=poisoned)
    constructed("G11", "poisoned baseline (A's own project); A + initial_layer_print_height 0.44 judged", "A",
                {CONTROL_EDIT_KEY: "0.44"}, rejects(UNRELATED, CONTROL_EDIT_KEY), root=poisoned)
    real("G12", "baseline replaced by another save of the same build (layer SHADOW run 0a24557a, re-digested); A judged",
         "A", {"verdict": "PASS"}, root=layer_root, required=False, note="boundary: same build, same migration noise")
    constructed("G13", "same swapped layer baseline; A + layer_height 0.24 (the swapped baseline's own edit)", "A",
                {"layer_height": "0.24"}, {"verdict": "PASS"}, root=layer_root, required=False,
                note="boundary: a real edit carried by the baseline on a key other than the json's control_edit_key "
                     "becomes an exempt value")
    constructed("G14", "same swapped layer baseline; A + layer_height 0.3 (any other value)", "A", {"layer_height": "0.3"},
                rejects(UNRELATED, "layer_height"), root=layer_root)

    # X: no unrelated change anywhere; these map what is exempted and check the constructions themselves.
    constructed("X1", "A with the migrated key version put back to 2.3.6", "A", {"version": "2.3.6"}, {"verdict": "PASS"},
                required=False, note="boundary: a migrated key left at the fixture value needs no exemption")
    constructed("X2", "fixture + wall_loops=3 + travel_speed -> ['500'] (exactly the migration value)", "fixture",
                {EDIT_KEY: "3", "travel_speed": control["travel_speed"]}, {"verdict": "PASS"}, required=False,
                note="boundary: a change landing exactly on the migration value is exempt")
    constructed("X3", "A with the manifest entry for wall_loops removed", "A", {MANIFEST_KEY: clean_manifest},
                {"verdict": "PASS"}, required=False, note="boundary: the manifest clause is an upper bound")
    constructed("X4", "control minus its own edit plus the walls edit (config rebuilt from the baseline)", "control",
                {CONTROL_EDIT_KEY: fixture[CONTROL_EDIT_KEY], EDIT_KEY: "3", MANIFEST_KEY: walls_manifest}, {"verdict": "PASS"},
                note="positive control for the constructions: the baseline's migration plus the walls edit alone must pass")
    rebuilt = next(item for item in controls if item["id"] == "X4")
    rebuilt["settings_identical_to_run_A"] = settings_of((work / "X4.3mf").read_bytes()) == run_a
    rebuilt["as_expected"] = rebuilt["as_expected"] and rebuilt["settings_identical_to_run_A"]

    if committed_before != (digest(control_path.read_bytes()), digest(meta_path.read_text().encode())) \
            or oracle.ROOT != REPO:
        raise SystemExit("The committed baseline changed or the redirect was not undone")
    off = [item["id"] for item in controls if item["as_expected"] is not True]
    required_off = [item["id"] for item in controls if item["required"] and item["as_expected"] is not True]

    # Baseline hygiene: three independent saves of one build agree on everything but their own edit.
    def triangle(name):
        saved = settings_of(saves[name]["raw"])
        added = sorted(set(control) - set(fixture))
        changed_control = {key for key in fixture if control[key] != fixture[key]} - {MANIFEST_KEY}
        changed_saved = {key for key in fixture if saved[key] != fixture[key]} - {MANIFEST_KEY}
        return {"added_keys_identical_to_control": sorted(set(saved) - set(fixture)) == added
                and all(saved[key] == control[key] for key in added),
                "removed_keys": sorted(set(fixture) - set(saved)),
                "changed_only_in_control": sorted(changed_control - changed_saved),
                "changed_only_in_run": sorted(changed_saved - changed_control),
                "shared_changed_keys": len(changed_control & changed_saved),
                "shared_changed_all_same_value": all(saved[key] == control[key] for key in changed_control & changed_saved),
                "manifest_run": saved[MANIFEST_KEY][0], "manifest_control": control[MANIFEST_KEY][0],
                "manifest_fixture": fixture[MANIFEST_KEY][0]}

    rows = exemption_rows(fixture_raw, control_raw, saves["A"]["raw"])
    migration_keys = sorted(row["key"] for row in rows if row["clause"] == "changed_key_equal_to_control")
    vector_keys = [key for key in migration_keys if run_a[key] == [fixture[key]] and type(fixture[key]) is str]
    baseline_gcode = (saves["A"]["dir"] / "baseline.gcode").read_bytes()
    a, c = saves["A"], saves["C"]
    a_code, c_code = ((facts["dir"] / "edited.gcode").read_bytes().split(b"\n") for facts in (a, c))
    without_line_2 = lambda lines: b"\n".join(lines[:1] + lines[2:])  # noqa: E731 - line 2 is the generation timestamp
    with zipfile.ZipFile(io.BytesIO(a["raw"])) as archive:
        a_entries = {info.filename: entry(a["raw"], info.filename) for info in archive.infolist()}
    with zipfile.ZipFile(io.BytesIO(c["raw"])) as archive:
        c_entries = {info.filename: entry(c["raw"], info.filename) for info in archive.infolist()}
    outcome_of = lambda cid: next(item["outcome"] for item in controls if item["id"] == cid)  # noqa: E731

    results = {
        "task": "mac-author A6: negative controls for verify_walls_differential",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "python": sys.version.split()[0],
        "hash_seed": os.environ.get("PYTHONHASHSEED"),
        "method": ("offline call of the unchanged criterion with (saved project, repository fixture, SUT identity); "
                   "constructed projects = copy + rewritten Metadata/project_settings.config + repack, temp dir only; "
                   "'redirected temp copy' = module ROOT pointed at a temp copy of runner/macos/walls_control.* "
                   "for that one call, committed files untouched; no GUI, no Orca launch; the criterion raises at the "
                   "first violation only, so a control names one offending key even when several were planted"),
        "criterion": {"path": criterion_path.relative_to(REPO).as_posix(),
                      "function": line_of(criterion_path, "def verify_walls_differential"),
                      "file_sha256": digest(criterion_path.read_bytes()),
                      "function_sha256": digest(inspect.getsource(oracle.verify_walls_differential).encode()),
                      "last_commit_touching_it": git("log", "-1", "--format=%H", "--", "runner/macos_project_copy.py").decode().strip(),
                      "working_tree_equals_head": git("show", "HEAD:runner/macos_project_copy.py") == criterion_path.read_bytes(),
                      "baseline_last_commit": git("log", "-1", "--format=%H", "--", "runner/macos/walls_control.3mf",
                                                  "runner/macos/walls_control.json").decode().strip()},
        "inputs": {"fixture": describe(fixture_path, fixture_raw), "control": describe(control_path, control_raw),
                   "control_metadata": describe(meta_path, meta_text.encode()),
                   "A": describe(a["dir"] / a["copy"], a["raw"]), "A_result": describe(a["dir"] / "result.json", a["result_raw"]),
                   "C": describe(c["dir"] / c["copy"], c["raw"]), "C_result": describe(c["dir"] / "result.json", c["result_raw"]),
                   "L": describe(layer["dir"] / layer["copy"], layer["raw"]),
                   "L_result": describe(layer["dir"] / "result.json", layer["result_raw"]),
                   "mac_sut": mac, "other_build_on_record": OTHER_BUILD,
                   "bindings": {**bindings, "saved_equals_receipt_and_slice_project": {"A": True, "C": True, "L": True},
                                "committed_A5_result_copy_identical": {name: saves[name]["committed_copy_identical"] for name in saves}},
                   "note": "artifacts/ is gitignored: the A/C/L inputs exist only on this host; their digests are in the "
                           "committed A5 result JSONs"},
        "construction": {"temp_dir": str(work), "reserialization_identical_without_edits": reserialization,
                         "all_constructions_verified": all(item["input"].get("construction_verified", True) for item in controls)},
        "controls": controls,
        "summary": {letter: {"pass": [item["id"] for item in controls if item["id"][0] == letter and item["outcome"]["verdict"] == "PASS"],
                             "rejected": sum(item["id"][0] == letter and item["outcome"]["verdict"] == "REJECT" for item in controls),
                             "all_as_predicted": all(item["as_expected"] for item in controls if item["id"][0] == letter)}
                    for letter in "ABCDEFGX"},
        "conclusion": {"form": "NOT_ALL_REJECTED" if required_off else "B/D/E/F_ALL_REJECTED",
                       "required_controls_off_prediction": required_off,
                       "other_controls_off_prediction": [cid for cid in off if cid not in required_off],
                       "C_under_the_new_criterion": outcome_of("C")["verdict"]},
        "task_letters": {letter: {"control": letter, "outcome": outcome_of(letter)} for letter in "ABCDEF"} | {
            "G": {"other_build_save_available": False,
                  "identity_presented_differently": {cid: outcome_of(cid) for cid in ("G1", "G2", "G3", "G8")},
                  "baseline_file_replaced_by_the_2.3.6_fixture": {cid: outcome_of(cid) for cid in ("G6", "G7")}}},
        "control_baseline_hygiene": {"vs_run_A": triangle("A"), "vs_run_C": triangle("C"),
                                     "vector_migrated_keys": len(vector_keys),
                                     "vector_migrated_keys_equal_windows_track_list": vector_keys == sorted(pilot_common._VECTOR_MIGRATIONS),
                                     "added_keys_matching_windows_track_defaults": sorted(
                                         key for key in pilot_common._ADDED_DEFAULTS if control.get(key) == pilot_common._ADDED_DEFAULTS[key]),
                                     "windows_track_added_defaults": sorted(pilot_common._ADDED_DEFAULTS),
                                     "un_edited_baseline_gcode_echo_agrees_with_saved_migration": echo_agreement(
                                         baseline_gcode, run_a, migration_keys)},
        "question_1_exemptions": {"rows": rows, "by_kind": dict(sorted(Counter(row["kind"] for row in rows).items())),
                                  "closure": {"fixture_keys": len(fixture), "exempt_added": len(rows) - len(migration_keys),
                                              "exempt_changed": len(migration_keys),
                                              "keys_rejecting_any_change": len(fixture) - len(migration_keys) - 2,
                                              "keys_with_their_own_rule": [EDIT_KEY, MANIFEST_KEY]}},
        "question_2_provenance": {
            "readback_2_3_3": {"channel": "GUI, read on the Mac by the worker; not read from any file",
                               "nature": "a matched-reading gate: the worker polls until the reading equals the wanted value "
                                         "(30 s) and fails otherwise, so a recorded value is a reading that matched",
                               "edit": [line_of(worker, 'desktop.act(pid, field, "AXValue", desktop.string("3"))'),
                                        line_of(worker, 'require(desktop.text(field, "AXValue") == "3"'),
                                        line_of(worker, "return desktop.text(field, \"AXValue\")")],
                               "baseline_and_reopen": [line_of(worker, 'wanted = "2" if phase == "baseline" else "3"'),
                                                       line_of(worker, "return digits if digits == wanted else None"),
                                                       line_of(worker, 'entry["wall"] = wait_for(wanted_read,')],
                               "screen_ocr": [line_of(worker, "def screen_capture"), line_of(worker, "/usr/sbin/screencapture"),
                                              line_of(worker, "def screen_ocr"), line_of(worker, "/usr/bin/swift"),
                                              line_of(worker, "def ocr_wall_read")],
                               "host_assertion": line_of(criterion_path, 'walls_seen != ["2", "3", "3"]')},
            "gcode_echo": {"channel": "direct file read on the host; the file is the slicer's temporary plate G-code "
                                     "(not a GUI export: gui_gcode_export is NOT_TESTED)",
                           "plate_identified_by_open_descriptor": [line_of(worker, "def open_plate"), line_of(worker, "/usr/sbin/lsof")],
                           "plate_read_and_receipt": [line_of(worker, "def slice_plate"),
                                                      line_of(worker, 'with path.open("rb") as stream:')],
                           "host_read": line_of(criterion_path, 'config_value_all((output / "edited.gcode").read_bytes(), "wall_loops")'),
                           "host_lineage_check": line_of(criterion_path, "def verify_plate")},
            "run_A": provenance(a), "run_C": provenance(c)},
        "run_C_vs_A": {"project_settings_config_identical": a_entries[SETTINGS] == c_entries[SETTINGS],
                       "entries_differing": sorted(name for name in a_entries if a_entries[name] != c_entries[name]),
                       "differing_entry_difference": "only <metadata key=\"source_file\">: each run's staging temp directory",
                       "edited_gcode": {"line_1_identical": a_code[0] == c_code[0],
                                        "line_2": [a_code[1].decode(), c_code[1].decode()],
                                        "identical_except_line_2": without_line_2(a_code) == without_line_2(c_code),
                                        "sha256_without_line_2": digest(without_line_2(a_code))},
                       "old_oracle": {name: old_oracle(fixture_raw, facts["raw"]) for name, facts in saves.items()},
                       "new_criterion": {name: outcome_of(name) for name in "AC"},
                       "recorded": {"A": {"verdict": a["result"]["verdict"]},
                                    "C": {"verdict": c["result"]["verdict"], "failure_stage": c["result"]["failure_stage"],
                                          "error": c["result"]["error"]},
                                    "host_checks_never_reached_in_C": ["verify.reopened_fields", "verify.edited_slice",
                                                                       "wall_loops gcode echo"]},
                       "note": "C is not re-verdicted: its recorded NON_GREEN stands; this only states what the new criterion returns for its bytes"},
        "integrity": {"committed_baseline_unchanged_after_run": True, "module_root_restored": oracle.ROOT == REPO,
                      "git_status_runner": git("status", "--porcelain", "--", "runner/macos", "runner/macos_project_copy.py").decode()},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for item in controls:
        outcome = item["outcome"]
        flag = {True: "ok  ", False: "FAIL"}[item["as_expected"]]
        print(f"{flag} {item['id']:4} {'req ' if item['required'] else 'info'} {outcome['verdict']:6} "
              f"{outcome['code'] or outcome['exception'] or ''}{':' + outcome['detail'] if outcome['detail'] else ''}")
    print(f"{results['conclusion']['form']}  required off-prediction: {required_off or 'none'}  "
          f"other off-prediction: {results['conclusion']['other_controls_off_prediction'] or 'none'}  temp dir: {work}")
    return 1 if off else 0


if __name__ == "__main__":
    sys.exit(main())
