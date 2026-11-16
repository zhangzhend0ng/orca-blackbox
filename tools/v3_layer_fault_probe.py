"""Fixed HOST fault sequences over real MCP/GUI; these are not AI trials.

The coordinator alone starts/harvests the guest. Collision injection is a
separate trusted CreateNew experiment, acknowledged while this port has no
outstanding RPC. Host completion never establishes NON_GREEN or cleanup.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import time

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools import v3_agent_host as host
from harness.agent_model import _action
from runner.agent_bridge import decode_json, validate_identity

CASE = "m3d_param_reslice"
FAULTS = ("wrong_parameter", "missing_reslice", "export_collision")
COLLISION_PATH = "exports/0002.gcode"
COLLISION_BYTES = b"orca-v3-export-collision-v1\n"
COLLISION_SHA256 = hashlib.sha256(COLLISION_BYTES).hexdigest()
_SEQUENCES = {
    "wrong_parameter": ("slice", "export_gcode", "edit", "slice", "export_gcode", "finish"),
    "missing_reslice": ("slice", "export_gcode", "edit", "observe", "export_gcode", "finish"),
    "export_collision": ("slice", "export_gcode", "edit", "slice", "export_gcode", "finish"),
}


def _once(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, allow_nan=False)
        stream.write("\n")


class FaultProbeModel:
    """ModelPort-shaped deterministic controller. It never calls a model."""
    case_id = CASE

    def __init__(self, fault: str, run_id: str):
        if type(fault) is not str or fault not in FAULTS:
            raise ValueError("unknown_fault")
        if type(run_id) is not str or re.fullmatch(r"[0-9a-f]{32}", run_id) is None:
            raise ValueError("invalid_run_id")
        self.fault, self.run_id = fault, run_id
        self.source = "fault_probe_" + fault
        self.actions, self.observations = [], set()

    def _collision_ack(self, root, deadline):
        request = {"schema_version": 1, "run_id": self.run_id, "fault": self.fault,
            "source": self.source, "operation": "create_new", "path": COLLISION_PATH,
            "content_ascii": COLLISION_BYTES.decode("ascii"), "sha256": COLLISION_SHA256,
            "size_bytes": len(COLLISION_BYTES)}
        _once(root / "fault_injection_request.json", request)
        print(json.dumps({"awaiting_trusted_injection": self.source, "run_id": self.run_id,
                          "request": str(root / "fault_injection_request.json")}), flush=True)
        expected = {"schema_version": 1, "run_id": self.run_id, "fault": self.fault,
            "path": COLLISION_PATH, "sha256": COLLISION_SHA256,
            "size_bytes": len(COLLISION_BYTES), "created_new": True}
        end = min(deadline, time.monotonic() + 60)
        path = root / "fault_injection_ack.json"
        while time.monotonic() < end:
            if path.exists():
                if path.is_symlink():
                    raise ValueError("injection_ack_link")
                with path.open("rb") as stream:
                    raw = stream.read(4097)
                if len(raw) > 4096:
                    raise ValueError("injection_ack_size")
                actual = decode_json(raw)
                # Equality alone permits bool/int coercion. Require exact types too.
                if (type(actual) is not dict or actual != expected or set(actual) != set(expected)
                        or any(type(actual[key]) is not type(value) for key, value in expected.items())):
                    raise ValueError("injection_ack_identity")
                _once(root / "fault_injection_accepted.json", expected)
                return
            time.sleep(.1)
        raise TimeoutError("injection_ack_deadline")

    def next_action(self, image, observation, history, remaining_calls, output_dir, deadline):
        if time.monotonic() >= deadline:
            raise TimeoutError("fault_probe_deadline")
        if history != self.actions or len(self.actions) >= len(_SEQUENCES[self.fault]):
            raise ValueError("fault_sequence_changed")
        if type(remaining_calls) is not int or remaining_calls <= 0:
            raise ValueError("fault_probe_budget")
        if (type(observation) is not dict or set(observation) != {"id", "window"}
                or type(observation["window"]) is not dict
                or observation["window"] != {"width": 1920, "height": 1032}
                or any(type(value) is not int for value in observation["window"].values())):
            raise ValueError("fault_probe_uncalibrated_window")
        index = len(self.actions) + 1
        ident = observation.get("id")
        if (type(ident) is not str or ident != f"{self.run_id}_{index:04d}"
                or ident in self.observations):
            raise ValueError("fault_probe_stale_observation")
        root = host.REPO / "artifacts" / "v3_host" / self.run_id
        image, output_dir = Path(image), Path(output_dir)
        if (image.parent != root or image.name != f"observation_{index:04d}.png"
                or image.is_symlink() or output_dir != root / f"model_{index:04d}"):
            raise ValueError("fault_probe_path_identity")
        if not 8 <= image.stat().st_size <= host.MAX_IMAGE_BYTES:
            raise ValueError("fault_probe_image")
        raw = image.read_bytes()
        if not 8 <= len(raw) <= host.MAX_IMAGE_BYTES or not raw.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("fault_probe_image")
        output_dir.mkdir(exist_ok=False)
        tool = _SEQUENCES[self.fault][index - 1]
        if self.fault == "export_collision" and index == 5:
            self._collision_ack(root, deadline)
        action = {"tool": tool, "observation_id": ident,
            "x": 298 if tool == "edit" else None,
            "y": (794 if self.fault == "wrong_parameter" else 764) if tool == "edit" else None,
            "text": "0.24" if tool == "edit" else None}
        action = _action(action, ident, 1920, 1032, case_id=CASE)
        if time.monotonic() >= deadline:
            raise TimeoutError("fault_probe_deadline")
        _once(output_dir / "summary.json", {"source": self.source, "model_inference": False,
            "ai_trial": False, "image_sha256": hashlib.sha256(raw).hexdigest(),
            "observation_id": ident, "action": action, "created_at_ns": time.time_ns()})
        self.observations.add(ident)
        self.actions.append(dict(action))
        return action


def run_probe(run_id, guest_root, fault):
    validate_identity(guest_root, run_id)
    model = FaultProbeModel(fault, run_id)
    root = host.REPO / "artifacts" / "v3_host" / run_id
    if root.exists():
        raise FileExistsError("fault_probe_requires_new_run")
    report = {"schema_version": 1, "run_id": run_id, "case_id": CASE, "fault": fault,
        "source": model.source, "ai_trial": False, "model_inference": False,
        "expected_release_verdict": "NON_GREEN", "release_eligible": False,
        "observed_release_verdict": None, "cleanup_confirmed": None,
        "disposition": "awaiting_independent_guest_evidence"}
    try:
        result = host.run_host(run_id, guest_root, model, CASE)
        report.update(host_finished=result["finished"], host_error_type=None)
        return report
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        report.update(host_finished=False, host_error_type=type(exc).__name__)
        raise
    finally:
        # run_host's own report proves it created this run. A rejected old run
        # or failed preflight must never receive an additional evidence file.
        original_error = sys.exc_info()[0] is not None
        try:
            owned = root / "host_run.json"
            if owned.is_file():
                with owned.open("rb") as stream:
                    raw = stream.read(65537)
                if len(raw) > 65536:
                    raise ValueError("host_report_size")
                prior = decode_json(raw)
                if type(prior) is dict and prior.get("run_id") == run_id and prior.get("model_source") == model.source:
                    _once(root / "fault_probe.json", report)
        except (OSError, ValueError, RuntimeError, KeyError, TypeError) as evidence_error:
            if not original_error:
                raise
            print(json.dumps({"status": "fault_probe_report_failed",
                              "error_type": type(evidence_error).__name__}), file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--guest-root", default=r"C:\coil\orca-blackbox-v3-r1")
    parser.add_argument("--fault", choices=FAULTS, required=True)
    args = parser.parse_args(argv)
    report = run_probe(args.run_id, args.guest_root, args.fault)
    print(json.dumps(report, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "fault_probe_stopped", "error_type": type(exc).__name__,
                          "ai_trial": False, "release_eligible": False}), file=sys.stderr)
        raise SystemExit(2)
