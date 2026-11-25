"""Recompute #250 attachment and local subtraction from harvested files."""

import json
from math import isclose
from pathlib import Path
import sys

from tools.replay_evidence_files import verified_part

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from negative_part_oracle import measure_difference, project_boxes

FIXTURE = ROOT / "fixtures" / "agent_layer_cube.3mf"
MEASUREMENT_LINE = "[m7x250] geometric difference: "


def _matches_logged_geometry(recorded: dict, measured: dict) -> bool:
    # Roundoff in the accumulated path lengths may vary across Python builds.
    for key in ("pass", "body_box", "cutter_box", "removed_region", "retained_region"):
        if recorded[key] != measured[key]:
            return False
    for phase in ("baseline", "negative"):
        for key, value in measured[phase].items():
            logged = recorded[phase][key]
            if isinstance(value, float):
                if not isclose(value, logged, rel_tol=0, abs_tol=1e-9):
                    return False
            elif logged != value:
                return False
    return True


def replay(directory: Path, prefix: str) -> dict:
    """Replay the archived default cube run after the driver verifies its log."""
    manifest = json.loads((directory / f"{prefix}-object_artifacts.json").read_text(encoding="utf-8-sig"))
    snapshot, baseline, negative = (
        verified_part(directory, prefix, manifest, name)
        for name in ("negative-project.3mf", "baseline.gcode", "negative.gcode")
    )
    fixture = project_boxes(FIXTURE)
    if fixture.keys() != {"normal_part"}:
        raise ValueError("the #250 default fixture must contain exactly one normal part")
    boxes = project_boxes(snapshot)
    body = fixture["normal_part"]
    if boxes.keys() != {"normal_part", "negative_part"} or boxes["normal_part"] != body:
        raise ValueError("saved #250 project must attach a negative part to the unchanged fixture body")

    cutter = boxes["negative_part"]
    measurements = measure_difference(baseline, negative, body, cutter)
    unchanged = measure_difference(baseline, baseline, body, cutter)
    log = (directory / f"{prefix}-case.log").read_text(encoding="utf-8-sig")
    recorded = [line.removeprefix(MEASUREMENT_LINE) for line in log.splitlines()
                if line.startswith(MEASUREMENT_LINE)]
    # An interrupted run can still have both exports. Retain its recomputed
    # measurements even when the guest never printed its final comparison.
    matches_log = len(recorded) == 1 and _matches_logged_geometry(json.loads(recorded[0]), measurements)

    return {
        "checks": {
            "manifest_sizes_and_sha256_match": True,
            "negative_attached_to_unchanged_fixture_body": True,
            "local_subtraction_with_retained_extrusion": measurements["pass"],
            "unchanged_baseline_rejected": unchanged["pass"] is False,
            "recomputed_geometry_matches_case_log": matches_log,
        },
        "geometry": measurements,
        "unchanged_baseline_control": unchanged,
        "gui_checks_outside_replay": ["native submenu and file chooser", "distinct canvas color"],
    }
