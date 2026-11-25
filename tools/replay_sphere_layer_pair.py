"""Replay #254's four logged field edits, two saved profiles and two GUI exports."""
import ast
from decimal import Decimal
from datetime import datetime
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re

from harness.agent_protocol import MODEL_FIXTURES
from harness.model_move_pilot import geometry_unchanged
from harness.pilot_param_layer_pair import verify_business
from harness.project_3mf import _settings
from tools.replay_evidence_files import verified_part


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/feishu_std_sphere.3mf"
FIELDS = ("layer_height", "initial_layer_print_height")
OFF = (Decimal("0.24"), Decimal("0.30"))
TARGET = (Decimal("0.20"), Decimal("0.25"))


def _four_edits(edits):
    if not isinstance(edits, list) or len(edits) != 4:
        return False
    previous = list(TARGET)
    for edit, index, wanted in zip(edits, (0, 1, 0, 1), OFF + TARGET):
        if (edit["field"] != FIELDS[index] or Decimal(edit["before"]) != previous[index]
                or Decimal(edit["submitted"]) != wanted):
            return False
        previous[index] = wanted
        if list(map(Decimal, edit["pair"])) != previous:
            return False
    return True


def _off_target(project, original):
    config = _settings(project, lambda: False)
    return tuple(Decimal(config[k]) for k in FIELDS) == OFF and geometry_unchanged(project, original)


def _plate_source(stage, log, record, project_hash, gcode_hash, require_private):
    # Older GUI runs opened the native export menu. Its dispatch is recorded
    # inside each slice stage of the receipt-hashed log. A missing analysis
    # field alone cannot opt a newer run back into this format.
    phase = re.escape(stage + "_reopen_slice_export")
    matches = re.findall(rf"^\[m7x249\] started {phase} at ([^\r\n]+)\s+(.*?)"
                         rf"^\[m7x249\] finished {phase} in (\d+\.\d+)s", log, re.M | re.S)
    if len(matches) != 1:
        return False
    timestamp, trace, duration = matches[0]
    if record is None:
        return (not require_private and "[m7] Export menu:" in trace
                and "Export G-code..." in trace and "[topbar] WM_COMMAND(" in trace)
    pids = re.findall(r"^\[launcher\] pid=(\d+) hwnd=", trace, re.M)
    pid = record["pid"]
    if type(pid) is not int or pid <= 0 or pids != [str(pid)]:
        return False
    rel = PureWindowsPath(record["plate"])
    if (rel.anchor or len(rel.parts) != 5 or ".." in rel.parts or ":" in record["plate"]
            or rel.parts[0] != "snapmaker_orca_model" or rel.parts[3] != "Metadata"
            or f"#{pid}#" not in rel.parts[2] or not re.fullmatch(rf"\.{pid}\.[^/\\]+\.gcode", rel.name)):
        return False
    started, modified = record["slice_started_ns"], record["modified_ns"]
    phase_start = int(datetime.fromisoformat(timestamp).timestamp() * 1e9)
    # GUI stage duration is printed to the nearest millisecond.
    phase_end = phase_start + round(float(duration) * 1e9) + 1_000_000
    return (type(started) is int and type(modified) is int
            and phase_start - 1_000_000 <= started <= modified <= phase_end
            and record["sha256"] == gcode_hash and record["project_sha256"] == project_hash)


def _preview_evidence(paths):
    import cv2
    import numpy as np
    from harness import anchors

    masks, colored_fractions = [], []
    for path in paths:
        frame = cv2.imread(str(path))
        if frame is None:
            raise ValueError(f"unreadable preview: {path.name}")
        masks.append(np.ptp(anchors.viewport_crop(frame), axis=2) > anchors.SPREAD_COLORED)
        colored_fractions.append(anchors.has_colored_content(frame))
    if masks[0].shape != masks[1].shape:
        raise ValueError("preview dimensions differ")
    union = np.logical_or(*masks).sum()
    overlap = float(np.logical_and(*masks).sum() / union) if union else 0.0
    return overlap, colored_fractions


def replay(directory: Path, prefix: str) -> dict:
    manifest = json.loads((directory / f"{prefix}-object_artifacts.json").read_text(encoding="utf-8-sig"))
    def artifact(name):
        return verified_part(directory, prefix, manifest, name)

    original = FIXTURE.read_bytes()
    if hashlib.sha256(original).hexdigest() != MODEL_FIXTURES["_sphere"][1]:
        raise ValueError("sphere fixture hash differs from native contract")
    analysis = json.loads(artifact("analysis.json").read_text(encoding="utf-8-sig"))
    log = (directory / f"{prefix}-case.log").read_text(encoding="utf-8-sig")
    marker = "[m7x254] "
    recorded = [ast.literal_eval(line[len(marker):]) for line in log.splitlines()
                if line.startswith(marker + "{'field':")]
    edits = analysis["edits"]
    checks = {"four_edits_match_receipt_log": _four_edits(edits) and edits == recorded,
              "baseline_schedule": False, "target_schedule": False, "schedules_match": False}
    report = {"checks": checks, "historical_failure": analysis.get("failure"), "edits": edits}
    names = {entry["part"] for entry in manifest}
    require_private = any(key in analysis for key in ("baseline_plate", "target_plate"))
    if require_private:
        checks["distinct_plate_processes"] = (analysis.get("baseline_plate", {}).get("pid") is not None
            and analysis.get("baseline_plate", {}).get("pid") != analysis.get("target_plate", {}).get("pid")
            and "target_plate" in analysis)
    for stage in ("baseline", "target"):
        if stage == "target" and not {"sphere-edited.3mf", "off-target.3mf"} <= names:
            report["missing_projects"] = sorted({"sphere-edited.3mf", "off-target.3mf"} - names)
            continue
        model = original if stage == "baseline" else artifact("sphere-edited.3mf").read_bytes()
        if stage == "target":
            off = artifact("off-target.3mf").read_bytes()
            checks["off_target_project"] = _off_target(off, original)
            checks["off_target_matches_save_readback"] = tuple(map(Decimal, analysis["off_target_saved"])) == OFF
            checks["target_project_rejected_as_off_target"] = not _off_target(model, original)
            checks["sphere_geometry_and_placement_preserved"] = geometry_unchanged(model, original)
        if stage + ".gcode" not in names:
            report[stage + "_error"] = "missing harvested export"
            continue
        gcode = artifact(stage + ".gcode").read_bytes()
        checks[stage + "_slice_source"] = _plate_source(
            stage, log, analysis.get(stage + "_plate"), hashlib.sha256(model).hexdigest(),
            hashlib.sha256(gcode).hexdigest(), require_private)
        try:
            observed = verify_business(model, original, gcode)
        except ValueError as exc:
            report[stage + "_error"] = str(exc)
        else:
            report[stage] = observed
            checks[stage + "_schedule"] = True
            if stage in analysis:
                checks[stage + "_matches_recorded_result"] = observed == analysis[stage]
    if "baseline" in report and "target" in report:
        checks["schedules_match"] = all(report["baseline"][k] == report["target"][k] for k in
                                        ("first_z", "last_z", "layer_count", *FIELDS))
    stages = ("baseline", "target")
    if not all(stage + "-preview.png" in names for stage in stages):
        checks["preview_overlap"] = False
        return report
    overlap, fractions = _preview_evidence([artifact(name + "-preview.png") for name in stages])
    report["preview_overlap"] = overlap
    checks["preview_overlap"] = overlap >= 0.9
    checks["preview_readbacks_match"] = all(fraction > 0 and
        abs(fraction - analysis[name + "_preview"]["colored_fraction"]) < 1e-9
        for name, fraction in zip(stages, fractions))
    if "colored_preview_overlap" in analysis:
        checks["preview_overlap_matches_readback"] = abs(overlap - analysis["colored_preview_overlap"]) < 1e-9
    return report
