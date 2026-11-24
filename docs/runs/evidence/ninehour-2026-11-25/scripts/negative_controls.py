#!/usr/bin/env python3
"""Part B - negative controls of the suite's business judges, on COPIES in this directory.

    set PYTHONDONTWRITEBYTECODE=1
    python -B C:\\coil\\vm_setup\\ninehour_1125\\recompute\\negative_controls.py [--out negative_controls.json] [--keep]

For every case run of tonight's batch the saved project (proof/0001.3mf) and the export
(exports/0001.gcode) are copied under scratch_negative_controls\\<run>_<control>\\ as proof.3mf and
0001.gcode, mutated there (the project by rewriting Metadata/project_settings.config inside the zip,
every other member byte-identical), and given to the judges the suite uses:

  business  harness.native_pilots.verify_business(scenario, project, fixture, gcode) - the call
            behind checks.business in result.json (harness/native_save_session.py:315,
            verify_script_business). Row 264: the param-family judge that
            harness.param_case_lib.make_verify builds. Row 276: make_comparison_verify WITHOUT a
            baseline, exactly as the guest ran it (pair_status "baseline_required").
  paired    row 276 only: the host-side pairing of tools/native_save_demo.py:373-375 -
            verify_business(..., baseline_gcode=<fixed e9aa6f88 export>) and then
            harness.param_comparison.comparison_business_status.
  full      harness.native_save_session.verify_saved over a whole copy of the run directory in which
            proof.json's two sha256 values and projects/0001.3mf were made consistent with the
            mutated files, i.e. a run whose files really were these. Not available for a run whose
            harvest has no manifest.json.

A control is a hole when `business` (or, for row 276, `paired`) ACCEPTS it. `full` tells whether
the bindings around the business judge would have caught it anyway. Every input given to a judge
is recorded by sha256. Nothing under the two checkouts is written; the originals are only read.
The full verifier's run-directory copies are deleted again unless --keep is given.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import io
import json
import shutil
import sys
import time
import zipfile
from pathlib import Path

sys.dont_write_bytecode = True          # belt and braces next to `python -B`
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import facts as F  # noqa: E402  (run table and readers of Part A; imports repository code read-only)

from harness import native_save_session, param_comparison  # noqa: E402
from harness.native_pilots import verify_business  # noqa: E402
from harness.runtime_ports import ExecutionOutcome, VerificationSnapshot  # noqa: E402

SETTINGS = F.SETTINGS_MEMBER
SCRATCH = HERE / "scratch_negative_controls"
CASE_RUNS = [run_id for run_id, _row, role in F.RUNS if role == "case"]
ROW = {run_id: row for run_id, row, _role in F.RUNS}
# exports of other runs used as substitute G-code (all read, never written)
FIXED_276 = "e9aa6f88eca940b385bfe531703f644e"          # the #276 comparison baseline (harness.param_comparison._BASELINES)
DEFAULT = {"cube": "245d51e21eb746d898f8b5fac3281303",   # default-parameter slice of the plain cube (uia_param_save_only)
           "fdmt": "0cccce4a3b3f40798bcab64c8a815680"}  # default-parameter slice of the FDM test (uia_param_fdmt_save_only)
OTHER = {"cube": "b697f7c24c6c49849c05b22c2a8ed1a3",     # an export of the other model
         "fdmt": "7484bd43c9114b5b8f8d098a6ac978e3",
         "std": "7484bd43c9114b5b8f8d098a6ac978e3"}
FIXTURE_OF = {"ec032d7cc54844f1a6f970a6990fa032": "std", "eebdf238d72e401b9636b161bad6c465": "std",
              "5359abcadafa48a2bc493ee3acf56114": "std", "7484bd43c9114b5b8f8d098a6ac978e3": "cube",
              "8e207463943845c2a4564a47efc54d64": "cube", "19d6103223264b2c8f21a0b8c5f76d1e": "cube",
              "b697f7c24c6c49849c05b22c2a8ed1a3": "fdmt"}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load(run_id: str) -> dict:
    """Everything a judge gets, read from the harvest; nothing is written."""
    where = F.resolve(run_id)
    d = where["dir"]
    run = {"run_id": run_id, "dir": d, "locations": where["locations"], "row": ROW[run_id],
           "fixture_kind": FIXTURE_OF[run_id], "scenario": F.read_json(d / "scope.json")["scenario"],
           "fixture": (d / "input" / "fixture.3mf").read_bytes(),
           "project": (d / "proof" / "0001.3mf").read_bytes(),
           "gcode": (d / "exports" / "0001.gcode").read_bytes()}
    run["saved"] = F.settings_of(run["project"])
    run["fixture_settings"] = F.settings_of(run["fixture"])
    run["has_manifest"] = (d / "manifest.json").is_file()
    return run


def gcode_of(run_id: str) -> bytes:
    return (F.resolve(run_id)["dir"] / "exports" / "0001.gcode").read_bytes()


# --------------------------------------------------------------------------- mutations (copies only)
def edited_settings(settings: dict, edits: dict) -> dict:
    """Apply edits to a copy of the settings. A plain value replaces the key's value (keeping the
    one-element-list shape the app uses for edited scalars); ("slot", i, v) replaces element i of
    a per-extruder list; ("remove",) deletes the key."""
    out = json.loads(json.dumps(settings))
    for key, spec in edits.items():
        current = out.get(key)
        if isinstance(spec, tuple) and spec[:1] == ("slot",):
            out[key] = [str(spec[2]) if i == spec[1] else value for i, value in enumerate(current)]
        elif isinstance(spec, tuple) and spec[:1] == ("remove",):
            out.pop(key, None)
        elif isinstance(current, list) and len(current) == 1:
            out[key] = [str(spec)]
        else:
            out[key] = spec
    return out


def build_project(project: bytes, edits: dict) -> bytes:
    """A new 3MF: every member byte-identical except Metadata/project_settings.config."""
    with zipfile.ZipFile(io.BytesIO(project)) as source:
        raw = source.read(SETTINGS)
        text = json.dumps(edited_settings(json.loads(raw.decode("utf-8-sig")), edits), ensure_ascii=False, indent=4)
        if b"\r\n" in raw:
            text = text.replace("\n", "\r\n")
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as target:
            for item in source.infolist():
                data = text.encode("utf-8") if item.filename == SETTINGS else source.read(item.filename)
                clone = zipfile.ZipInfo(item.filename, date_time=item.date_time)
                clone.compress_type, clone.external_attr = item.compress_type, item.external_attr
                target.writestr(clone, data)
    return out.getvalue()


def split_gcode(gcode: bytes):
    """(before, config block incl. its last newline, after)."""
    start = gcode.index(b"; CONFIG_BLOCK_START")
    stop = gcode.index(b"\n", gcode.index(b"; CONFIG_BLOCK_END")) + 1
    return gcode[:start], gcode[start:stop], gcode[stop:]


def transplant(moves_from: bytes, echo_from: bytes) -> bytes:
    """The executable part of the first export with the config block of the second."""
    before, _block, after = split_gcode(moves_from)
    return before + split_gcode(echo_from)[1] + after


def rewrite_echo(gcode: bytes, values: dict) -> bytes:
    """Replace '; key = value' lines of the config block; every move untouched."""
    before, block, after = split_gcode(gcode)
    lines = block.split(b"\n")
    for key, value in values.items():
        prefix = ("; %s = " % key).encode()
        hits = [i for i, line in enumerate(lines) if line.startswith(prefix)]
        if len(hits) != 1:
            raise SystemExit("expected exactly one echo line for %s, found %d" % (key, len(hits)))
        lines[hits[0]] = prefix + str(value).encode()
    return before + b"\n".join(lines) + after


def bump(text: str, step: float) -> str:
    return "%g" % (float(text) + step)


def controls(run: dict) -> list:
    """The mutations offered to the judges, as functions of the run's own files."""
    row, saved, fixture = run["row"], run["saved"], run["fixture_settings"]
    cur = lambda key: F.normalize(saved.get(key))  # noqa: E731
    default = lambda key: F.normalize(fixture.get(key))  # noqa: E731
    joined = lambda key: ",".join(fixture[key]) if isinstance(fixture.get(key), list) else fixture.get(key)  # noqa: E731
    kind = run["fixture_kind"]
    list_of, add = [], None

    def add(cid, title, edits=None, project=None, gcode=None, expect="REJECTED", files=None):
        list_of.append({"id": cid, "title": title, "edits": edits or {}, "project": project, "gcode": gcode,
                        "expected": expect, "files": files or {}})

    add("1", "untouched saved project and export (must be accepted)", expect="ACCEPTED")
    if row == "264":
        add("2", "one target wrong by one step: overhang_3_4_speed 20 -> 25", {"overhang_3_4_speed": "25"})
        add("2b", "one target wrong by one step: overhang_1_4_speed 40 -> 45", {"overhang_1_4_speed": "45"})
        add("2c", "enable_overhang_speed switched off: 1 -> 0", {"enable_overhang_speed": "0"})
        add("3", "one target left at the fixture default: overhang_2_4_speed 30 -> %s" % default("overhang_2_4_speed"),
            {"overhang_2_4_speed": default("overhang_2_4_speed")})
        add("3b", "one target unset: overhang_3_4_speed removed from the config", {"overhang_3_4_speed": ("remove",)})
        echo_defaults = {key: default(key) for key in F.FEISHU["264"] if key in saved and key != "overhang_totally_speed"}
        targets = [key for key in F.FEISHU["264"] if key in saved]
    else:
        add("2", "one target wrong by one step: filament_max_volumetric_speed slot 1: 15 -> 20",
            {"filament_max_volumetric_speed": ("slot", 0, 20)})
        add("2b", "one target wrong by one step: outer_wall_speed 700 -> 750", {"outer_wall_speed": "750"})
        add("3", "one target left at the fixture default: outer_wall_speed -> %s" % default("outer_wall_speed"),
            {"outer_wall_speed": default("outer_wall_speed")})
        add("3b", "one target left at the fixture default: filament_max_volumetric_speed slot 1 -> %s"
            % fixture["filament_max_volumetric_speed"][0], {"filament_max_volumetric_speed": ("slot", 0, fixture["filament_max_volumetric_speed"][0])})
        echo_defaults = {key: joined(key) for key in ("outer_wall_speed", "filament_max_volumetric_speed")}
        targets = list(F.FEISHU["276"])
    add("4a", "targets correct + unrelated top_surface_speed %s -> %s" % (cur("top_surface_speed"), bump(cur("top_surface_speed"), 10)),
        {"top_surface_speed": bump(cur("top_surface_speed"), 10)})
    add("4b", "targets correct + unrelated retraction_length slot 1 %s -> %s"
        % (saved["retraction_length"][0], bump(saved["retraction_length"][0], 0.4)),
        {"retraction_length": ("slot", 0, bump(saved["retraction_length"][0], 0.4))})
    add("4c", "targets correct + unrelated wall_loops %s -> %s" % (saved["wall_loops"], bump(saved["wall_loops"], 1)),
        {"wall_loops": bump(saved["wall_loops"], 1)})
    add("5", "the input fixture presented as the saved result (nothing edited)", project="fixture")
    fixed = FIXED_276 if row == "276" else DEFAULT[kind]
    add("6", "targets correct, G-code replaced by the %s G-code %s"
        % ("fixed baseline" if row == "276" else "default-parameter export of the same fixture", fixed[:8]), gcode=fixed)
    add("6b", "targets correct, G-code replaced by an export of ANOTHER model (%s)" % OTHER[kind][:8], gcode=OTHER[kind])
    add("6c", "targets correct, G-code truncated to its first 2000 bytes", gcode=("truncate", 2000))
    add("6d", "targets correct, G-code config block rewritten to the fixture defaults of the target keys, moves untouched",
        gcode=("echo", echo_defaults))
    add("6e", "targets correct, G-code = moves of the default export %s with this run's config block" % fixed[:8],
        gcode=("transplant", fixed))
    dirty = list(saved["different_settings_to_system"])
    add("7a", "dirty list without the target keys (their values correct)",
        {"different_settings_to_system": [";".join(k for k in dirty[0].split(";") if k and k not in targets)] + dirty[1:]},
        expect="ACCEPTED (values are right; the dirty list is app-maintained metadata)")
    add("7b", "dirty list with an unrelated key added (its value unchanged)",
        {"different_settings_to_system": [";".join(filter(None, [dirty[0], "top_surface_speed"]))] + dirty[1:]})
    if run["has_manifest"]:
        manifest = F.read_json(run["dir"] / "manifest.json")
        tampered = dict(manifest, case_id="param_999_bogus", executor="agent_mcp", contract_sha256="0" * 64,
                        metadata={"note": "altered by negative_controls.py"})
        add("m1", "project untouched; manifest.json case_id / executor / contract_sha256 / metadata altered "
            "(run_id and started_at_ns kept)", expect="REJECTED if the verifier reads the manifest", files={"manifest.json": tampered})
        add("m2", "project untouched; manifest.json started_at_ns moved 1 h later than the run", expect="REJECTED",
            files={"manifest.json": dict(manifest, started_at_ns=manifest["started_at_ns"] + 3600 * 10**9)})
        scope = F.read_json(run["dir"] / "scope.json")
        add("m3", "project untouched; scope.json scenario renamed", expect="REJECTED",
            files={"scope.json": dict(scope, scenario=scope["scenario"] + "_x")})
    return list_of


# --------------------------------------------------------------------------- judges
def summarized(detail) -> dict:
    keep = ("case_id", "pair_status", "layer_count", "last_z", "first_z", "schedule_error", "schedule_asserted",
            "gcode_sha256", "baseline_run", "baseline_outer_wall_peak_mm_s", "outer_wall_peak_mm_s",
            "outer_wall_peak_mm3_s", "near_feishu_178_mm_s", "x_limit_effect", "other_settings_preserved", "scene_preserved")
    return {key: detail[key] for key in keep if isinstance(detail, dict) and key in detail}


def judge_business(run: dict, project: bytes, gcode: bytes) -> dict:
    """The call behind result.json's checks.business (harness/native_save_session.py:315)."""
    try:
        detail = verify_business(run["scenario"], project, run["fixture"], gcode)
    except Exception as exc:  # noqa: BLE001 - the judges signal through _InvalidEvidence(ValueError)
        return {"verdict": "REJECTED", "reason": str(exc), "exception": type(exc).__name__}
    return {"verdict": "ACCEPTED", "reason": None, "detail": summarized(detail)}


def judge_paired(run: dict, project: bytes, gcode: bytes, baseline: bytes) -> dict:
    """tools/native_save_demo.py:373-375: the fixed baseline, then comparison_business_status."""
    try:
        detail = verify_business(run["scenario"], project, run["fixture"], gcode, baseline_gcode=baseline)
        status = param_comparison.comparison_business_status(detail)
    except Exception as exc:  # noqa: BLE001
        return {"verdict": "REJECTED", "reason": str(exc), "exception": type(exc).__name__}
    return {"verdict": "ACCEPTED", "reason": None, "detail": summarized(detail),
            "business_status": status["business_status"], "unmet_expectations": status["unmet_expectations"]}


def judge_full(run: dict, tag: str, replacements: dict, keep: bool) -> dict:
    """harness.native_save_session.verify_saved over a scratch copy of the whole run directory."""
    if not run["has_manifest"]:
        return {"verdict": "NOT RUN", "reason": "manifest.json is not in this run's harvest; verify_saved reads snapshot.manifest"}
    target = SCRATCH / "full" / ("%s_%s" % (run["run_id"][:8], tag))
    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(run["dir"], target, copy_function=shutil.copyfile)
    try:
        for rel, data in replacements.items():
            path = target / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data if isinstance(data, bytes) else json.dumps(data, sort_keys=True).encode("utf-8"))
        # a run whose files really were these would carry a consistent receipt
        proof = F.read_json(target / "proof.json")
        if "proof/0001.3mf" in replacements:
            proof["project_sha256"] = sha256(replacements["proof/0001.3mf"])
            (target / "projects" / "0001.3mf").write_bytes(replacements["proof/0001.3mf"])
        if "exports/0001.gcode" in replacements:
            proof["gcode_sha256"] = sha256(replacements["exports/0001.gcode"])
        (target / "proof.json").write_bytes(json.dumps(proof, sort_keys=True).encode("utf-8"))
        manifest = F.read_json(target / "manifest.json")
        snapshot = VerificationSnapshot(native_save_session.native_contract("script", run["scenario"]), run["run_id"],
                                        target, manifest, ExecutionOutcome("completed"))
        try:
            outcome = native_save_session.verify_saved(snapshot, cancelled=lambda: False)
        except Exception as exc:  # noqa: BLE001
            return {"verdict": "RAISED", "reason": "%s: %s" % (type(exc).__name__, exc)}
        business, path = outcome.checks["business"], outcome.checks["path"]
        return {"verdict": "ACCEPTED" if business.status == "pass" else "REJECTED",
                "reason": None if business.status == "pass" else business.detail[:200],
                "path_check": path.status, "evidence_complete": outcome.evidence_complete,
                "execution_compliant": outcome.execution_compliant}
    finally:
        if not keep and target.exists():
            shutil.rmtree(target)


# --------------------------------------------------------------------------- main
def cell(entry: dict) -> str:
    if entry["verdict"] == "ACCEPTED":
        text = "ACCEPTED"
        if entry.get("business_status"):
            text += "(%s)" % entry["business_status"]
        return text
    if entry["verdict"] == "NOT RUN":
        return "not-run"
    return "REJECTED: %s" % (entry["reason"] or "")[:74]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=str(HERE / "negative_controls.json"))
    parser.add_argument("--keep", action="store_true", help="keep the scratch copies fed to the full verifier")
    options = parser.parse_args()
    started = time.time()
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)                    # this script's own scratch directory only
    SCRATCH.mkdir(parents=True)
    entries = []
    for run_id in CASE_RUNS:
        run = load(run_id)
        baseline = gcode_of(FIXED_276) if run["row"] == "276" else None
        for control in controls(run):
            # the copies (and only the copies) are changed here
            project = (run["fixture"] if control["project"] == "fixture"
                       else build_project(run["project"], control["edits"]) if control["edits"] else run["project"])
            gcode = run["gcode"]
            if isinstance(control["gcode"], str):
                gcode = gcode_of(control["gcode"])
            elif isinstance(control["gcode"], tuple) and control["gcode"][0] == "echo":
                gcode = rewrite_echo(run["gcode"], control["gcode"][1])
            elif isinstance(control["gcode"], tuple) and control["gcode"][0] == "transplant":
                gcode = transplant(gcode_of(control["gcode"][1]), run["gcode"])
            elif isinstance(control["gcode"], tuple) and control["gcode"][0] == "truncate":
                gcode = run["gcode"][:control["gcode"][1]]
            elif isinstance(control["gcode"], bytes):
                gcode = control["gcode"]
            # the copies (and only the copies) are changed, and kept under scratch_negative_controls\\<run>_<control>\\
            folder = SCRATCH / ("%s_%s" % (run_id[:8], control["id"]))
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "proof.3mf").write_bytes(project)
            gcode_untouched = gcode == run["gcode"]
            # the untouched export (7 MB for the FDM test) is copied once per run, under control 1
            gcode_copy = SCRATCH / ("%s_1" % run_id[:8]) / "0001.gcode"
            if not gcode_untouched or control["id"] == "1":
                gcode_copy = folder / "0001.gcode"
                gcode_copy.write_bytes(gcode)
            common = {"run_id": run_id, "scenario": run["scenario"], "feishu_row": run["row"], "control": control["id"],
                      "mutation": control["title"], "expected": control["expected"],
                      "project_sha256": sha256(project), "gcode_sha256": sha256(gcode),
                      "project_is_harvested_proof": project == run["project"], "gcode_is_harvested_export": gcode_untouched,
                      "copy_dir": str(folder), "gcode_copy": str(gcode_copy),
                      "harvested_export": str(run["dir"] / "exports" / "0001.gcode")}
            (folder / "control.json").write_text(json.dumps(common, ensure_ascii=False, indent=1), encoding="utf-8")
            business = judge_business(run, project, gcode)
            entries.append(dict(common, judge="business (as result.json)", **business))
            if run["row"] == "276":
                entries.append(dict(common, judge="paired (host-side, fixed baseline + comparison_business_status)",
                                    **judge_paired(run, project, gcode, baseline)))
            files = dict(control["files"])
            if not common["project_is_harvested_proof"]:
                files["proof/0001.3mf"] = project
            if not common["gcode_is_harvested_export"]:
                files["exports/0001.gcode"] = gcode
            entries.append(dict(common, judge="full verifier (verify_saved, receipt made consistent)",
                                **judge_full(run, control["id"], files, options.keep)))
        print("judged %s (%s): %d controls" % (run_id[:8], run["scenario"], len(controls(run))))

    # ---- table: one line per control, the runs of a group collapsed when they agree
    groups = [("264 cube", "cube", "264"), ("264 fdmt", "fdmt", "264"), ("276", "std", "276")]
    judges = ["business (as result.json)", "paired (host-side, fixed baseline + comparison_business_status)",
              "full verifier (verify_saved, receipt made consistent)"]
    holes, lines = [], []
    for title, kind, row in groups:
        run_ids = [r for r in CASE_RUNS if FIXTURE_OF[r] == kind and ROW[r] == row]
        by = collections.defaultdict(dict)
        for entry in entries:
            if entry["run_id"] in run_ids:
                by[(entry["control"], entry["mutation"])][entry["run_id"][:8] + " " + entry["judge"].split(" (")[0]] = entry
        lines.append("=" * 150)
        lines.append("ROW %s  runs %s  (A = ACCEPTED, R = REJECTED; 'business' is the judge behind result.json's checks.business)"
                     % (title, " ".join(r[:8] for r in run_ids)))
        for (control, mutation), table in by.items():
            expected = next(e["expected"] for e in table.values())
            lines.append("--- control %s: %s   [expected: %s]" % (control, mutation, expected))
            for judge in judges:
                name = judge.split(" (")[0]
                cells = [(r[:8], table.get(r[:8] + " " + name)) for r in run_ids]
                if all(c is None for _r, c in cells):
                    continue
                if all(c is not None and c["verdict"] == "ACCEPTED" for _r, c in cells):
                    text = "ACCEPTED x%d%s" % (len(cells), "".join(sorted("(%s)" % c["business_status"] for _r, c in cells if c.get("business_status"))))
                else:
                    seen = collections.OrderedDict()
                    for r, c in cells:
                        seen.setdefault("not-run" if c is None else cell(c), []).append(r)
                    text = " | ".join("%s [%s]" % (verdict, ",".join(rs)) for verdict, rs in seen.items())
                lines.append("      %-10s %s" % (name, text))
                if name in ("business", "paired"):
                    for r, c in cells:
                        if c is not None and c["verdict"] == "ACCEPTED" and not expected.startswith("ACCEPTED"):
                            holes.append((title, r, name, control, mutation, c.get("business_status")))
    report = {"generated_at_local": time.strftime("%Y-%m-%d %H:%M:%S"), "script": str(Path(__file__).resolve()),
              "command": "set PYTHONDONTWRITEBYTECODE=1 && python -B \"%s\"" % Path(__file__).resolve(),
              "repo": str(F.REPO), "repo_head": F.git_head(F.REPO),
              "methods": {"business": F.cite(verify_business), "paired_status": F.cite(param_comparison.comparison_business_status),
                          "full": F.cite(native_save_session.verify_saved),
                          "param_family_values": F.cite(F.pilot_common.inspect_preserved_settings)},
              "scratch": str(SCRATCH), "entries": entries,
              "accepted_where_rejection_was_expected": [
                  {"group": h[0], "run_id_prefix": h[1], "judge": h[2], "control": h[3], "mutation": h[4], "business_status": h[5]}
                  for h in holes]}
    Path(options.out).write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("\n".join(lines))
    print("=" * 150)
    print("accepted where rejection was expected: %d entry(ies); written to %s (%d bytes) in %.1f s"
          % (len(holes), options.out, Path(options.out).stat().st_size, time.time() - started))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
