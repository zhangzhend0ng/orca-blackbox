"""Export a reviewable regression script from a harvested ZCode SHADOW run."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from harness.agent_protocol import valid_run_id
from harness.native_matrix import REPLAY_SOURCES, UIA_SAVE_SCENARIO
from harness.native_pilots import TRIALS, native_fixture, verify_business
from harness.native_save_session import NATIVE_SUT_SHA256, verify_layer_saved, verify_unchanged_saved
from harness.native_uia_replay import compile_recipe, recipe_path
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
    scenario = summary["scenario"]
    if scenario not in REPLAY_SOURCES.values():
        raise ValueError("replay_source_scenario_unsupported")
    if (any(item["run_id"] != run_id for item in (summary, host, process, teardown, setup, scope, proof))
            or any(item["scenario"] != scenario for item in (host, setup, scope))
            or summary["actor"] != "zcode" or not host["toolset_verified"]
            or (host["provider_id"], host["model_id"]) != ("new-provider", "glm-5.3-flash")
            or setup["tab_clicked"] != "Quality"
            or scope["app_pid"] != setup["app_pid"] or scope["app_pid"] != proof["old_pid"]
            or scope["output_path"] != proof["output_path"] or proof["sut_sha256"] != NATIVE_SUT_SHA256
            or not grade(scenario, host, result, process, teardown, trace,
                         coordinator_exit=summary["actor_exit"])):
        raise ValueError("replay_source_not_proven")
    fixture_path, fixture_hash = native_fixture(scenario)
    files = (REPO / fixture_path, evidence / "proof/0001.3mf", evidence / "exports/0001.gcode")
    expected = (fixture_hash, proof["project_sha256"], proof["gcode_sha256"])
    fixture, project, gcode = (path.read_bytes() for path in files)
    if any(hashlib.sha256(raw).hexdigest() != digest for raw, digest in zip((fixture, project, gcode), expected)):
        raise ValueError("replay_source_artifact_digest")
    if scenario in TRIALS:
        verify_business(scenario, project, fixture, gcode)
    elif scenario == UIA_SAVE_SCENARIO:
        if type(setup.get("dialog_hwnd")) is not int or setup["dialog_hwnd"] != scope.get("dialog_hwnd"):
            raise ValueError("replay_source_initial_dialog")
        verify_unchanged_saved(project, fixture, gcode, cancelled=lambda: False)
    else:
        verify_layer_saved(project, fixture, gcode, cancelled=lambda: False)
    return compile_recipe(raw, run_id=run_id, source_sha=summary["source_sha"], app_pid=scope["app_pid"],
                          main_hwnd=scope["hwnd"], output_path=scope["output_path"], scenario=scenario,
                          dialog_hwnd=scope.get("dialog_hwnd"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    recipe = record(args.run_id)
    replay = next(k for k, source in REPLAY_SOURCES.items() if source == recipe["scenario"])
    output = args.output or recipe_path(replay)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(recipe, stream, indent=2)
        stream.write("\n")
    print(f"Recorded {len(recipe['steps'])} operations in {output}")


if __name__ == "__main__":
    main()
