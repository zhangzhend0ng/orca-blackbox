"""Export a reviewable regression script from a harvested ZCode SHADOW run."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from harness.agent_protocol import LAYER_FIXTURE, LAYER_FIXTURE_SHA256, valid_run_id
from harness.native_matrix import UIA_LAYER_SCENARIO
from harness.native_save_session import NATIVE_SUT_SHA256, verify_layer_saved
from harness.native_uia_replay import RECORDING, compile_recipe
from tools.zcode_matrix import grade, load


def record(run_id):
    valid_run_id(run_id)
    artifacts = REPO / "artifacts"
    evidence = artifacts / "windows_mcp_harvest" / run_id
    host = load(artifacts / "windows_mcp_host" / run_id / "host.json")
    summary = load(artifacts / "native_save_demo" / run_id / "summary.json")
    result, process, teardown, setup, scope, proof = (
        load(evidence / f"{name}.json") for name in ("result", "process", "teardown", "setup", "scope", "proof"))
    trace_path = evidence / "native_trace.ndjson"
    if trace_path.stat().st_size > 256000:
        raise ValueError("replay_source_trace_size")
    raw = trace_path.read_bytes()
    trace = [json.loads(line) for line in raw.splitlines()]
    if (any(item["run_id"] != run_id for item in (summary, host, process, teardown, setup, scope, proof))
            or any(item["scenario"] != UIA_LAYER_SCENARIO for item in (summary, host, setup, scope))
            or summary["actor"] != "zcode" or not host["toolset_verified"]
            or (host["provider_id"], host["model_id"]) != ("new-provider", "glm-5.3-flash")
            or setup["tab_clicked"] != "Quality"
            or scope["app_pid"] != setup["app_pid"] or scope["app_pid"] != proof["old_pid"]
            or scope["output_path"] != proof["output_path"] or proof["sut_sha256"] != NATIVE_SUT_SHA256
            or not grade(UIA_LAYER_SCENARIO, host, result, process, teardown, trace,
                         coordinator_exit=summary["actor_exit"])):
        raise ValueError("replay_source_not_proven")
    files = (REPO / LAYER_FIXTURE, evidence / "proof/0001.3mf", evidence / "exports/0001.gcode")
    expected = (LAYER_FIXTURE_SHA256, proof["project_sha256"], proof["gcode_sha256"])
    fixture, project, gcode = (path.read_bytes() for path in files)
    if any(hashlib.sha256(raw).hexdigest() != digest for raw, digest in zip((fixture, project, gcode), expected)):
        raise ValueError("replay_source_artifact_digest")
    verify_layer_saved(project, fixture, gcode, cancelled=lambda: False)
    return compile_recipe(raw, run_id=run_id, source_sha=summary["source_sha"], app_pid=scope["app_pid"],
                          main_hwnd=scope["hwnd"], output_path=scope["output_path"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id")
    parser.add_argument("--output", type=Path, default=RECORDING)
    args = parser.parse_args()
    recipe = record(args.run_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(recipe, stream, indent=2)
        stream.write("\n")
    print(f"Recorded {len(recipe['steps'])} operations in {args.output}")


if __name__ == "__main__":
    main()
