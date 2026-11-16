"""Three fixed project persistence challenges over real MCP/GUI; no model."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.v3_layer_fault_probe import FaultProbeModel, _run_probe

FAULTS = ("save_before_edit", "missing_reopen", "missing_slice")


class ProjectFaultModel(FaultProbeModel):
    case_id = "m3g_export_3mf"
    source_prefix = "fault_probe_project_"
    sequences = {
        "save_before_edit": ("save_project", "edit", "reopen_project", "slice", "export_gcode", "finish"),
        "missing_reopen": ("edit", "save_project", "observe", "slice", "export_gcode", "finish"),
        "missing_slice": ("edit", "save_project", "reopen_project", "observe", "export_gcode", "finish"),
    }


def run_probe(run_id, guest_root, fault):
    return _run_probe(run_id, guest_root, ProjectFaultModel(fault, run_id))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--guest-root", default=r"C:\coil\orca-blackbox-v3-r1")
    parser.add_argument("--fault", required=True, choices=FAULTS)
    args = parser.parse_args(argv)
    print(json.dumps(run_probe(args.run_id, args.guest_root, args.fault), sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "project_fault_probe_stopped", "error_type": type(exc).__name__,
                          "ai_trial": False, "release_eligible": False}), file=sys.stderr)
        raise SystemExit(2)
