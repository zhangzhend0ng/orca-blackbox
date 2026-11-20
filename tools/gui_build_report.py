"""Summarize explicitly selected Windows and macOS GUI runs for one build request."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.agent_layer_verify import analyze_gcode
from harness.agent_protocol import LAYER_FIXTURE, LAYER_FIXTURE_SHA256
from harness.project_3mf import _archive, inspect_project


def require(condition, message):
    if not condition:
        raise ValueError(message)


def path_label(path):
    path = path.resolve()
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def check_slice(path, name, sha256, origin):
    wanted, count = ("0.4", 68) if name == "baseline" else ("0.24", 112)
    facts = analyze_gcode(path.read_bytes(), layer_height=wanted)
    require(facts["sha256"] == sha256, f"{name} G-code digest mismatch")
    require(facts["layer_count"] == count, f"{name} layer count mismatch")
    return {**facts, "artifact": path_label(path), "origin": origin}


def check_project(path, sha256, height="0.24"):
    fixture = (ROOT / LAYER_FIXTURE).read_bytes()
    require(hashlib.sha256(fixture).hexdigest() == LAYER_FIXTURE_SHA256, "Repository fixture changed")
    facts = inspect_project(path.read_bytes(), fixture, layer_height=height)
    require(facts["sha256"] == sha256, "Saved project digest mismatch")
    return {**facts, "artifact": path_label(path)}


def mac_slices(row, folder, result, negative):
    guest = result["guest"]
    for name, phase in (("baseline", "baseline"), ("edited", "reopen")):
        reported = result.get("slices", {}).get(name)
        injected = negative and name == "edited"
        if not reported and not injected:
            row["missing"].append(f"{name}_slice")
            continue
        expected_file = name + ".gcode"
        path = folder / expected_file
        receipt = guest["slice_receipts"][name]
        project_digest = guest["source_before"] if name == "baseline" else guest["saved_sha256"]
        require(receipt["source"] == "open_process_plate" and receipt["phase"] == phase
                and receipt["pid"] == guest["phases"][phase]["pid"]
                and receipt["project_sha256"] == project_digest and receipt["size"] == path.stat().st_size
                and receipt["export_enabled_before"] is False and receipt["export_enabled_after"] is True,
                f"Mac {name} plate provenance or slice transition mismatch")
        if injected:
            actual = analyze_gcode(path.read_bytes(), layer_height="0.32")
            require(actual["sha256"] == receipt["sha256"], "Injected plate digest mismatch")
            row["observed_rejected_slice"] = {**actual, "artifact": path_label(path), "origin": "gui_plate_temporary"}
        else:
            require(reported["artifact"] == expected_file and reported["origin"] == "gui_plate_temporary"
                    and receipt["sha256"] == reported["sha256"], f"Unexpected Mac {name} artifact")
            actual = check_slice(path, name, receipt["sha256"], reported["origin"])
            for key in ("layer_count", "first_z", "last_z", "positive_xy_e_moves"):
                require(actual[key] == reported[key], f"Mac {name} {key} differs from artifact")
            row["slices"][name] = actual


def macos(row, folder, result, candidate, negative):
    guest = result.get("guest", {})
    row.update(run_id=result["run_id"], candidate=result.get("candidate"),
               source_verdict=result.get("verdict"), sut=guest.get("sut"), fixture_sha256=guest.get("source_before"),
               started_at=result.get("started_at"), finished_at=result.get("finished_at"),
               gui_phases=guest.get("phases", {}), native_save_as=result.get("native_save_as"),
               gui_gcode_export=result.get("gui_gcode_export"))
    if row["scope"] == "current":
        require(row["candidate"] == candidate, "Mac run belongs to a different build request")
        kind = "wrong_layer_control" if negative else "layer_comparison"
        require(result.get("test_kind") == kind, f"Expected Mac run kind {kind}")
    if result.get("verdict") != "SHADOW" and not negative:
        row.update(status="NON_GREEN", failure_stage=result.get("failure_stage", "unknown"),
                   error=result.get("error", "Source run did not pass"))
        if result.get("slices"):
            mac_slices(row, folder, result, False)
        return

    require(guest.get("ok") is True and guest.get("run_id") == row["run_id"], "Mac worker identity or result mismatch")
    require(guest.get("cleanup_verified") is True, "Mac cleanup unverified")
    require(guest.get("source_before") == guest.get("source_after") == LAYER_FIXTURE_SHA256, "Mac fixture mismatch")
    if row["sut"]:
        require(row["sut"].get("version") and row["sut"].get("build")
                and re.fullmatch("[0-9a-f]{64}", row["sut"].get("executable_sha256", "")), "Mac SUT identity incomplete")
    else:
        row["missing"].append("actual_sut")

    phases = row["gui_phases"]
    require(phases["reopen"]["pid"] != phases["edit"]["pid"]
            and phases["edit"]["layers"] == ["0.4", "0.4"], "Mac edit/reopen lineage mismatch")
    height = "0.32" if negative else "0.24"
    require(phases["reopen"]["layers"] == [height, "0.4"], "Unexpected Mac reopen fields")
    project = folder / "layer-024-copy.3mf"
    if negative:
        raw = project.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == guest["saved_sha256"], "Injected project digest mismatch")
        config = json.loads(_archive(raw, lambda: False)["Metadata/project_settings.config"])
        require([config["layer_height"], config["initial_layer_print_height"]] == [height, "0.4"],
                "Injected value missing from saved project")
        row["project"] = {"artifact": path_label(project), "sha256": guest["saved_sha256"],
                          "layer_height": height, "initial_layer_print_height": "0.4"}
    else:
        row["project"] = check_project(project, guest["saved_sha256"])

    if result.get("slices") or negative:
        require(len({phases[phase]["pid"] for phase in ("baseline", "edit", "reopen")}) == 3
                and phases["baseline"]["layers"] == ["0.4", "0.4"], "Mac baseline process mismatch")
    mac_slices(row, folder, result, negative)

    if negative:
        require(result.get("verdict") == "NON_GREEN" and result.get("failure_stage") == "verify.saved_project"
                and "project_layer_config" in result.get("error", ""), "Control did not reject the injected layer")
        require("baseline" in row["slices"] and row["sut"], "Negative control lacks its baseline or SUT")
        row.update(status="EXPECTED_FAILURE", failure_stage=result["failure_stage"], error=result["error"],
                   injected_layer=height, expected_layer="0.24")


def windows(row, folder, result, candidate, baseline):
    binding_path = folder / "binding.json"
    binding = read_json(binding_path) if binding_path.is_file() else {}
    attempt = result.get("verdict") in ("BLOCKED", "NON_GREEN") and "candidate_id" in result
    manifest = result if attempt else read_json(folder / "manifest.json")
    run_id = manifest["run_id"]
    scenario = "uia_replay_save" if baseline else "uia_replay_layer"
    row.update(run_id=run_id, started_at=manifest.get("started_at"),
               source_verdict=result.get("verdict") if attempt else result.get("release_verdict"))
    if binding:
        row.update(candidate=binding.get("candidate_id"), fixture_sha256=binding.get("fixture_sha256"),
                   sut={"version": binding.get("sut_version"), "build": binding.get("file_version") or binding.get("sut_version"),
                        "executable_sha256": binding.get("sut_sha256"), "dll_sha256": binding.get("dll_sha256")},
                   binding=path_label(binding_path),
                   preflight_at=binding.get("at_utc"))
        require(binding["run_id"] == run_id, "Windows preflight run mismatch")
        if row["scope"] == "current" and "scenario" in binding:
            require(binding["scenario"] == scenario, "Windows binding scenario differs from requested phase")
    if attempt:
        require((not binding or binding.get("candidate_id") == result.get("candidate_id"))
                and (row["scope"] != "current" or result["candidate_id"] == candidate), "Windows attempt binding mismatch")
        if row["scope"] == "current" and "scenario" in result:
            require(result["scenario"] == scenario, "Windows attempt scenario differs from requested phase")
        stage = result["failure_stage"]
        require(bool(result["error"]) and isinstance(stage, str) and bool(stage.strip()), "Incomplete Windows failure")
        row.update(status=result["verdict"], candidate=result["candidate_id"], scenario=result.get("scenario"),
                   failure_stage=stage, error=result["error"], identity_basis="installed_preflight" if binding else None,
                   gui_started=result.get("gui_started", False if stage in ("guest.preflight", "guest.host_guard") else None))
        return
    if (folder / "process.json").is_file():
        process = read_json(folder / "process.json")
        require(process["run_id"] == run_id, "Windows process receipt mismatch")
        if process.get("finished_at_ns"):
            row["finished_at"] = datetime.fromtimestamp(process["finished_at_ns"] / 1e9, timezone.utc).isoformat()
    if row["scope"] == "current":
        require(binding.get("run_id") == run_id and binding.get("candidate_id") == candidate,
                "Windows result needs a matching candidate and run binding")
        row["candidate"] = candidate
    if result.get("verified_pass") is not True or row["source_verdict"] != "SHADOW":
        row.update(status="NON_GREEN", failure_stage=result.get("failure_stage") or result.get("execution_status"),
                   error=result.get("reasons"))
        return
    require(result.get("cleanup_confirmed") is True, "Windows cleanup unverified")
    if row["scope"] == "current":
        stamp = binding.get("post_verified_at")
        if not stamp:
            row["missing"].append("post_verified_at")
        else:
            post = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            require(post.utcoffset() is not None, "Windows postcheck time needs an explicit UTC offset")
            for earlier in (binding.get("at_utc"), row.get("finished_at")):
                if earlier:
                    require(post >= datetime.fromisoformat(earlier.replace("Z", "+00:00")),
                            "Windows postcheck precedes preflight or completion")
            row["post_verified_at"] = stamp

    if manifest["case_id"] == "m3d_param_reslice":
        # Historical layer comparison contract exports twice within one process.
        require(row["scope"] == "historical", "Current results must include an independently reopened project")
        artifacts = folder / "artifacts"
        fixture = artifacts / "input" / "fixture.3mf"
        row["fixture_sha256"] = hashlib.sha256(fixture.read_bytes()).hexdigest()
        require(row["fixture_sha256"] == LAYER_FIXTURE_SHA256, "Windows fixture mismatch")
        receipts = [json.loads(line) for line in (artifacts / "operation_receipts.ndjson").read_text().splitlines()]
        exports = [r for r in receipts if r["method"] == "export_gcode"]
        require(len(exports) == 2, "Windows run does not have two GUI export receipts")
        for index, name in enumerate(("baseline", "edited")):
            receipt = exports[index]
            relative = f"exports/{index + 1:04d}.gcode"
            require(receipt["run_id"] == run_id and receipt["details"]["path"] == relative,
                    "Windows GUI export receipt mismatch")
            row["slices"][name] = check_slice(artifacts / relative, name, receipt["details"]["sha256"], "gui_export")
        row["missing"].extend(["actual_sut", "saved_project_and_independent_reopen"])
        return

    require(manifest["case_id"] == "m3g_export_3mf", "Unsupported Windows case")
    proof = read_json(folder / "proof.json")
    setup = read_json(folder / "setup.json")
    require(proof["run_id"] == setup["run_id"] == run_id and setup["scenario"] == scenario
            and proof["contract_sha256"] == manifest["contract_sha256"], "Windows proof identity mismatch")
    require(setup["app_pid"] == proof["old_pid"] != proof["reopened_pid"] and proof["reopened_closed"] is True,
            "Independent Windows reopen missing")
    require(re.fullmatch("[0-9a-f]{64}", proof["sut_sha256"]), "Invalid Windows SUT digest")
    row["sut"] = {"version": binding.get("sut_version"), "build": binding.get("file_version") or binding.get("sut_version"),
                  "executable_sha256": proof["sut_sha256"], "dll_sha256": binding.get("dll_sha256")}
    if binding:
        require(binding["run_id"] == run_id and binding["sut_sha256"] == proof["sut_sha256"],
                "Installed Windows executable differs from the run proof")
        row["identity_basis"] = "installed_preflight_matched_to_run_proof"
        row["fixture_sha256"] = binding.get("fixture_sha256")
        require(row["fixture_sha256"] == LAYER_FIXTURE_SHA256, "Windows input fixture mismatch")
    else:
        row["missing"].append("input_fixture_digest")
    if not row["sut"]["version"]:
        row["missing"].append("installed_version")
    row["gui_phases"] = {"edit_pid": proof["old_pid"], "reopen_pid": proof["reopened_pid"]}
    row["project"] = check_project(folder / "projects/0001.3mf", proof["project_sha256"], "0.4" if baseline else "0.24")
    name = "baseline" if baseline else "edited"
    row["slices"][name] = check_slice(folder / "exports/0001.gcode", name, proof["gcode_sha256"], "gui_export")
    if baseline:
        row["baseline_input"] = "unmodified_settings_saved_copy"
    else:
        row["missing"].append("baseline_slice")


def platform_row(platform, path, scope, candidate, negative=False, baseline=False):
    row = {"platform": platform, "scope": scope, "status": "NOT_RUN", "run_id": None,
           "sut": None, "fixture_sha256": None, "slices": {}, "missing": [], "failure_stage": None}
    if path is None:
        row["scope"] = "not_run"
        return row
    # A failed Windows postcheck (for example build drift) takes precedence over the inner run.
    if platform == "windows" and path.name == "result.json" and (path.parent / "attempt.json").is_file():
        path = path.parent / "attempt.json"
    row.update(status="INCOMPLETE", result=path_label(path))
    row["diagnostics"] = [path_label(path.parent / name) for name in
                          ("worker.log", "ssh.log", "native_worker.log", "proof.json", "agent_final.png", "proof_final.png",
                           "runner_startup_failure.log")
                          if (path.parent / name).is_file()]
    try:
        result = read_json(path)
        if platform == "windows":
            windows(row, path.parent, result, candidate, baseline)
        else:
            macos(row, path.parent, result, candidate, negative)
        if row["status"] == "INCOMPLETE" and not row["missing"]:
            row["status"] = "SHADOW"
    except (ValueError, OSError, KeyError, TypeError, AttributeError, zipfile.BadZipFile) as error:
        row.update(status="INVALID_EVIDENCE", failure_stage="report.validate_evidence", error=str(error))
    return row


def attach_windows_baseline(edited, baseline):
    edited["baseline_run"] = baseline
    if baseline["status"] != "SHADOW":
        if edited["status"] == "INCOMPLETE" and baseline["status"] in ("NON_GREEN", "INVALID_EVIDENCE", "BLOCKED"):
            edited.update(status=baseline["status"], failure_stage=baseline["failure_stage"],
                          error=baseline.get("error"))
        return
    if edited["status"] != "INCOMPLETE" or edited["missing"] != ["baseline_slice"]:
        return
    same_build = (edited["sut"] == baseline["sut"] and edited["fixture_sha256"] == baseline["fixture_sha256"]
                  and edited["run_id"] != baseline["run_id"])
    if not same_build:
        edited.update(status="INVALID_EVIDENCE", failure_stage="report.bind_windows_pair",
                      error="Windows baseline and edited runs must be distinct and match installed build and fixture")
        return
    edited["slices"]["baseline"] = baseline["slices"]["baseline"]
    edited.update(missing=[], status="SHADOW")


def build_report(args):
    platforms = {}
    history = []
    for platform in ("windows", "macos"):
        platforms[platform] = platform_row(platform, getattr(args, platform), "current", args.candidate)
        for path in getattr(args, "historical_" + platform):
            history.append(platform_row(platform, path, "historical", args.candidate))
    if args.windows_baseline:
        baseline = platform_row("windows", args.windows_baseline, "current", args.candidate, baseline=True)
        attach_windows_baseline(platforms["windows"], baseline)
    control = None
    if args.negative_control:
        control = platform_row("macos", args.negative_control, "current", args.candidate, negative=True)
        mac = platforms["macos"]
        if control["status"] == "EXPECTED_FAILURE":
            if mac["status"] != "SHADOW":
                control.update(status="UNPAIRED_CONTROL", failure_stage="report.bind_control",
                               error="No verified current macOS positive run to pair with the control")
            elif (mac["run_id"] == control["run_id"] or mac["fixture_sha256"] != control["fixture_sha256"]
                  or mac["sut"]["version"] != control["sut"]["version"] or mac["sut"]["build"] != control["sut"]["build"]
                  or mac["sut"]["executable_sha256"] != control["sut"]["executable_sha256"]):
                control.update(status="INVALID_EVIDENCE", failure_stage="report.bind_control",
                               error="Control requires a distinct run on the same macOS executable and fixture")
    statuses = [row["status"] for row in platforms.values()]
    if any(s in ("NON_GREEN", "INVALID_EVIDENCE", "BLOCKED") for s in statuses) or (control and control["status"] != "EXPECTED_FAILURE"):
        status = "NON_GREEN"
    elif statuses == ["SHADOW", "SHADOW"]:
        status = "SHADOW"
    else:
        status = "INCOMPLETE"
    versions = {p: (row["sut"] or {}).get("version") for p, row in platforms.items()}
    comparison = "UNKNOWN"
    if all(versions.values()):
        comparison = "SAME_VERSION" if versions["windows"] == versions["macos"] else "DIFFERENT_VERSIONS"
        if status == "SHADOW" and comparison == "DIFFERENT_VERSIONS":
            status = "INCOMPLETE"
    return {"schema_version": 1, "candidate": args.candidate, "generated_at": datetime.now(timezone.utc).isoformat(),
            "installed_versions": versions, "version_comparison": comparison,
            "status": status, "platforms": platforms, "negative_control": control, "historical": history}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True, help="Unique request label used by the platform runs")
    parser.add_argument("--output", required=True, type=Path, help="Destination JSON file")
    for name in ("windows", "macos"):
        parser.add_argument("--" + name, type=Path, help="Current candidate result.json")
        parser.add_argument("--historical-" + name, type=Path, action="append", default=[],
                            help="Historical result.json, retained separately; repeatable")
    parser.add_argument("--windows-baseline", type=Path,
                        help="Separate uia_replay_save baseline result bound to the same candidate and Windows binary")
    parser.add_argument("--negative-control", type=Path, help="Current wrong-layer control result.json")
    args = parser.parse_args()
    if not args.candidate.strip():
        parser.error("--candidate must not be blank")
    if args.windows_baseline and not args.windows:
        parser.error("--windows-baseline requires --windows")
    report = build_report(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # A report must never replace an input receipt or a previously generated report.
    with args.output.open("x", encoding="utf-8") as out:
        json.dump(report, out, indent=2, ensure_ascii=False)
        out.write("\n")
    print(f"{report['status']} {args.output}")
    return 0 if report["status"] == "SHADOW" else 1


if __name__ == "__main__":
    sys.exit(main())
