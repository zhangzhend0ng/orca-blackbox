"""Per-run receipts for the nine-hour run, built from synthetic harvest directories.

Each helper rebuilds one of the real layouts file for file under tmp_path: the
guest harvest (runner/hv_harvest.ps1 plus the tools/native_save_demo.py summary),
the fa706g3 harvest (fa_run.py: native_run.log and execution_host.json, no
summary, no teardown.json) and the Mac runner result (runner/macos_project_copy.py).
Nothing starts a GUI, a VM or the network."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import ninehour_receipts as receipts  # noqa: E402


GUEST, FA, MAC, HALF = "a1" * 16, "b2" * 16, "c3" * 16, "d4" * 16
SHA = "636a7330e9ee2b7dc7a78d36b11940eaa56ea78b"
STARTED = 1_795_541_672_067_666_200
SECTIONS = ("identity", "verdicts", "seconds", "stages", "artifacts")
HEADER = ("| machine | label | scenario | run (first 8 characters) | commit (first 7 characters) | verdict | pass "
          "| comparison | cleanup | guest s | host s | action s | stage sum | stages with ok=0 |")
PASSING = {"release_verdict": "SHADOW", "verified_pass": True, "cleanup_confirmed": True,
           "execution_status": "completed", "mode": "script_shadow", "checks": {}}
OFFLINE = "summary.offline-pairing.json"
UNVERIFIED = {"status": "unverified", "business_status": "UNVERIFIED", "unmet_expectations": ["comparison_baseline"],
              "reason": "comparison_baseline: the fixed baseline export was not in the checkout yet"}
PAIRING = {"status": "paired", "comparison_checked": True, "business_status": "SHADOW",
           "unmet_expectations": ["outer_wall_near_178_mm_s", "machine_x_limit_intervention"],
           "detail": {"row": "276", "pair_status": "checked", "outer_wall_peak_mm_s": 202.956}}


def put_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def put_bytes(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def lines(*rows):
    """A worker log with CRLF line endings, as the guest writes it."""
    return "".join(row + "\r\n" for row in rows).encode()


def guest_harvest(root):
    run = root / "artifacts" / "windows_mcp_harvest" / GUEST
    project = put_bytes(run / "proof/0001.3mf", b"synthetic saved project")
    gcode = put_bytes(run / "exports/0001.gcode", b"synthetic exported gcode")
    put_json(run / "result.json", PASSING)
    put_json(run / "process.json", {"run_id": GUEST, "started_at_ns": STARTED,
                                    "finished_at_ns": STARTED + 189_960_451_000, "exit_code": 0, "active_processes": 0})
    put_json(run / "native_worker.json", {"run_id": GUEST, "scenario": "compare_276_quality",
                                          "script_action_elapsed_ns": 76_422_000_000, "script_steps": ["edit", "save"],
                                          "error": None})
    (run / "native_worker.log").write_bytes(lines(
        "[profile] seeded C:\\coil\\orca-blackbox-v3-r1\\artifacts\\profile",
        "[flow276] tab.Quality ok=1 seconds=1.5",
        "[param-phrase] 'Layer height' found down at y=765 span=None",
        "[flow276] locate.Layer height ok=1 seconds=0.25",
        "[flow276] edit_readback.Layer height ok=1 seconds=2.5",
        "[flow276] field.Layer height ok=1 seconds=2.75",
        "[flow276] tab.Speed ok=1 seconds=3.5",
        "[flow276] save ok=1 seconds=4",
        "[flow276] tab.Quality ok=1 seconds=1.25",
        "[winutil] SendMessageTimeoutW(msg=0x201) to hwnd 0x11a1186 did not complete"))
    put_json(run / "proof.json", {"run_id": GUEST, "project_sha256": project, "gcode_sha256": gcode, "old_pid": 4484})
    put_json(run / "teardown.json", {"run_id": GUEST, "active_processes": 0, "cleanup_confirmed": True,
                                     "token_exists": False})
    put_json(root / "artifacts" / "native_save_demo" / GUEST / "summary.json", {
        "run_id": GUEST, "source_sha": SHA, "actor": "script", "scenario": "compare_276_quality", "actor_exit": 0,
        "result": {"verified_pass": True}, "host_wall_seconds": 222.8279999999795, "harvest_seconds": 2.0,
        "comparison": {"status": "paired", "business_status": "SHADOW",
                       "unmet_expectations": ["outer_wall_near_178_mm_s"], "reason": None}})
    return run


def physical_harvest(root):
    run = root / "artifacts" / "windows_mcp_harvest" / FA
    project = put_bytes(run / "proof/0001.3mf", b"synthetic fa project")
    gcode = put_bytes(run / "exports/0001.gcode", b"synthetic fa gcode")
    put_json(run / "result.json", PASSING)
    put_json(run / "process.json", {"run_id": FA, "started_at_ns": STARTED,
                                    "finished_at_ns": STARTED + 231_998_426_000, "exit_code": 0, "active_processes": 0})
    put_json(run / "native_worker.json", {"run_id": FA, "scenario": "uia_param_overhang_speeds",
                                          "script_action_elapsed_ns": 123_000_000_000, "error": None})
    (run / "native_worker.log").write_bytes("\n".join((   # LF, no final newline
        "[flow264] checkbox.Detect overhang ok=1 seconds=1.125",
        "[flow264] locate.Overhang speed ok=0 seconds=0.5",
        "[flow264] field.Overhang speed ok=0 seconds=0.5",
        "[flow264] field.Gap ok=0 seconds=0.75",
        "[flow264] field.Standalone ok=1 seconds=0.5",
        "[flow264] save ok=1 seconds=2.25")).encode())
    put_json(run / "proof.json", {"run_id": FA, "project_sha256": project, "gcode_sha256": gcode})
    (run / "native_run.log").write_text("[host_guard] real execution on a NON-GUEST test machine\n", encoding="utf-8")
    # Written by harness/runtime.py with indent=1.
    (run / "execution_host.json").write_text(json.dumps({
        "schema_version": 1, "hyper_v_guest": False, "flag": "ORCA_BB_ALLOW_TESTBOX", "machine": "FA706G3",
        "note": "ran on a non-guest test machine that opted in; not guest evidence"}, indent=1), encoding="utf-8")
    return run


def mac_result(run_id, **changes):
    result = {"run_id": run_id, "verdict": "SHADOW", "candidate": "mac-author-20261125-01", "goal": "walls",
              "test_kind": "walls_comparison", "started_at": "2026-11-23T13:33:19.233332+08:00",
              "finished_at": "2026-11-23T05:35:16.149544+00:00", "slices": {}, "native_save_as": "NOT_TESTED",
              "gui_gcode_export": "NOT_TESTED",
              "guest": {"ok": True, "run_id": run_id, "cleanup_verified": True, "phases": {
                  "baseline": {"pid": 25404, "window": "baseline", "layers": ["0.4", "0.4"], "wall": "2"},
                  "edit": {"pid": 25754, "window": "wall-3-copy", "layers": ["0.4", "0.4"], "wall": "3"},
                  "reopen": {"pid": 26039, "window": "wall-3-copy", "layers": ["0.4", "0.4"], "wall": "3"}}},
              "wall_loops_gcode_echo": ["3"]}
    result.update(changes)
    return result


def mac_harvest(root):
    return put_json(root / "artifacts" / "mac_project_copy" / MAC / "result.json", mac_result(MAC)).parent


def mac_evidence_copy(root):
    """A committed copy: the result files were renamed, and probe results sit beside them."""
    folder = root / "docs" / "runs" / "evidence" / "mac-walls-a5-2026-11-25"
    put_json(folder / f"walls_run_{MAC[:8]}_result.json", mac_result(MAC))
    failing = mac_result("ffe0c6e45c2c456b94e904ded891c1ac", verdict="NON_GREEN", failure_stage="verify.saved_project",
                         error="pilot_config_unknown_addition " + "x" * 400)
    del failing["wall_loops_gcode_echo"]
    put_json(folder / "walls_run_ffe0c6e4_nongreen_result.json", failing)
    put_json(folder / "edit_probe16_result.json", {"ok": True, "verdict": "edited", "guest": {"ok": True},
                                                  "entry": {"pid": 19952}})
    return folder


def guest_run(root):
    return root / "artifacts" / "windows_mcp_harvest" / GUEST


def unverified_summary(root):
    """The host summary of a #276 run that ended unverified: its fixed baseline was not yet in the checkout."""
    path = root / "artifacts" / "native_save_demo" / GUEST / "summary.json"
    return put_json(path, {**json.loads(path.read_text(encoding="utf-8")), "comparison": UNVERIFIED})


def offline_pairing(root, **changes):
    """What the orchestrator writes next to summary.json after re-doing the pairing on the host."""
    record = {"run_id": GUEST, "scenario": "compare_276_quality", "source_sha": SHA,
              "paired_offline_at": "2026-11-25 01:57:02", "in_flight_status": "unverified", "comparison": PAIRING}
    record.update(changes)
    return put_json(root / "artifacts" / "native_save_demo" / GUEST / OFFLINE, record)


def half_harvested(root):
    """The process was killed and only part of the run directory reached the host."""
    run = root / "artifacts" / "windows_mcp_harvest" / HALF
    put_json(run / "result.json", {**PASSING, "release_verdict": "NON_GREEN", "verified_pass": False,
                                   "cleanup_confirmed": False, "execution_status": "timeout"})
    put_json(run / "process.json", {"run_id": HALF, "started_at_ns": STARTED})
    put_json(run / "teardown.json", {"run_id": HALF, "active_processes": 1})
    return run


HARVESTS = {"guest": guest_harvest, "fa706g3": physical_harvest, "mac": mac_harvest,
            "half-harvested": half_harvested, "mac-evidence": mac_evidence_copy}


def leaves(node, path=""):
    """(dotted path, value) of every value that is not an object."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from leaves(value, f"{path}.{key}" if path else key)
    else:
        yield path, node


def snapshot(folder):
    return {str(path.relative_to(folder)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(folder.rglob("*")) if path.is_file()}


def test_guest_run_receipt_gives_exact_seconds_and_never_adds_a_parent_to_its_children(tmp_path):
    run = guest_harvest(tmp_path)
    receipt = receipts.receipts_for(run)[0]
    assert receipt["identity"] == {"run_id": GUEST, "source_commit": SHA, "scenario": "compare_276_quality",
                                   "goal": None, "machine": "guest", "machine_inferred": "guest", "label": None,
                                   "execution_host": None}
    assert receipt["verdicts"] == {
        "release_verdict": "SHADOW", "verified_pass": True, "cleanup_confirmed": True,
        "execution_status": "completed", "mode": "script_shadow",
        "comparison": {"status": "paired", "business_status": "SHADOW",
                       "unmet_expectations": ["outer_wall_near_178_mm_s"], "reason": None},
        "comparison_source": "summary.json", "paired_offline_at": None,
        "verdict": None, "failure_stage": None, "error": None, "guest_phases": None, "wall_loops_gcode_echo": None}
    assert receipt["seconds"] == {"guest": 189.960451, "host_wall": 222.8279999999795, "harvest": 2.0,
                                  "script_action": 76.422, "mac_wall": None}
    stages = receipt["stages"]
    assert [stage["stage"] for stage in stages["list"]] == [
        "tab.Quality", "locate.Layer height", "edit_readback.Layer height", "field.Layer height", "tab.Speed",
        "save", "tab.Quality"]
    assert stages["list"][1] == {"stage": "locate.Layer height", "ok": 1, "seconds": 0.25, "line": 4}
    assert stages["stage_sum_ok"] == 13.0        # 1.5 + 0.25 + 2.5 + 3.5 + 4 + 1.25: field.Layer height is the parent
    assert stages["parents"] == ["field.Layer height"] and stages["ok0"] == [] and stages["tags"] == ["flow276"]
    project = hashlib.sha256(b"synthetic saved project").hexdigest()
    gcode = hashlib.sha256(b"synthetic exported gcode").hexdigest()
    assert receipt["artifacts"] == {
        "proof_run_id": GUEST, "project_sha256": project, "project_sha256_recomputed": project,
        "gcode_sha256": gcode, "gcode_sha256_recomputed": gcode, "artifact_hashes_match": True,
        "teardown_active_processes": 0}
    assert receipt["missing"] == [] and receipt["warnings"] == []
    assert receipt["sources"]["seconds.guest"] == "process.json#finished_at_ns - started_at_ns"
    assert receipt["sources"]["seconds.script_action"] == "native_worker.json#script_action_elapsed_ns"
    assert receipt["sources"]["identity.source_commit"] == f"native_save_demo/{GUEST}/summary.json#source_sha"
    assert receipt["sources"]["verdicts.comparison.status"] == f"native_save_demo/{GUEST}/summary.json#comparison.status"
    assert receipt["sources"]["artifacts.gcode_sha256_recomputed"] == "exports/0001.gcode#sha256"
    assert "verdicts.guest_phases" not in receipt["sources"]     # Mac fields do not apply to a Windows run


def test_physical_run_is_recognised_by_its_own_files_and_what_it_lacks_is_listed(tmp_path):
    run = physical_harvest(tmp_path)
    receipt = receipts.receipts_for(run)[0]
    assert receipt["identity"]["machine"] == "fa706g3" and receipt["identity"]["machine_inferred"] == "fa706g3"
    assert receipt["sources"]["identity.machine"] == "inferred: native_run.log exists"
    assert receipt["identity"]["execution_host"] == {"hyper_v_guest": False, "machine": "FA706G3",
                                                     "flag": "ORCA_BB_ALLOW_TESTBOX"}
    assert receipt["identity"]["scenario"] == "uia_param_overhang_speeds" and receipt["identity"]["source_commit"] is None
    assert receipt["seconds"] == {"guest": 231.998426, "host_wall": None, "harvest": None, "script_action": 123.0,
                                  "mac_wall": None}
    assert receipt["verdicts"]["comparison"] is None and receipt["verdicts"]["verified_pass"] is True
    stages = receipt["stages"]
    assert stages["stage_sum_ok"] == 3.875        # 1.125 + 2.25 + 0.5: ok=0 stages and the parent are left out
    assert stages["parents"] == ["field.Overhang speed"]    # field.Gap has no listed child, so it is not a parent
    assert stages["ok0"] == ["locate.Overhang speed", "field.Overhang speed", "field.Gap"]
    assert receipt["artifacts"]["artifact_hashes_match"] is True
    assert receipt["artifacts"]["teardown_active_processes"] is None
    assert receipt["missing"] == ["teardown.json"] and receipt["warnings"] == []


def test_mac_run_receipt_converts_iso_timestamps_with_offsets_and_keeps_phase_order(tmp_path):
    run = mac_harvest(tmp_path)
    receipt = receipts.receipts_for(run)[0]
    assert receipt["identity"] == {"run_id": MAC, "source_commit": None, "scenario": None, "goal": "walls",
                                   "machine": "mac", "machine_inferred": "mac", "label": None, "execution_host": None}
    assert receipt["seconds"] == {"guest": None, "host_wall": None, "harvest": None, "script_action": None,
                                  "mac_wall": 116.916212}
    assert receipt["verdicts"]["verdict"] == "SHADOW" and receipt["verdicts"]["failure_stage"] is None
    assert receipt["verdicts"]["error"] is None and receipt["verdicts"]["release_verdict"] is None
    assert list(receipt["verdicts"]["guest_phases"]) == ["baseline", "edit", "reopen"]
    assert receipt["verdicts"]["guest_phases"]["edit"] == {"pid": 25754, "layers": ["0.4", "0.4"], "wall": "3"}
    assert receipt["verdicts"]["wall_loops_gcode_echo"] == ["3"]
    assert receipt["missing"] == []
    assert receipt["sources"]["seconds.mac_wall"] == "result.json#finished_at - started_at"
    assert receipt["sources"]["verdicts.guest_phases.edit.pid"] == "result.json#guest.phases.edit.pid"
    assert receipt["sources"]["verdicts.error"] == "result.json#error"
    assert "seconds.guest" not in receipt["sources"]      # a Mac run has no process.json: nothing is missing


def test_mac_evidence_copy_is_recognised_by_schema_not_by_file_name(tmp_path):
    folder = mac_evidence_copy(tmp_path)
    built = receipts.receipts_for(folder)
    assert [receipt["identity"]["run_id"] for receipt in built] == [MAC, "ffe0c6e45c2c456b94e904ded891c1ac"]
    assert all(receipt["identity"]["machine"] == "mac" for receipt in built)
    failed = built[1]
    assert failed["verdicts"]["verdict"] == "NON_GREEN" and failed["verdicts"]["failure_stage"] == "verify.saved_project"
    assert failed["verdicts"]["error"] == ("pilot_config_unknown_addition " + "x" * 400)[:300]
    assert len(failed["verdicts"]["error"]) == 300
    assert failed["verdicts"]["wall_loops_gcode_echo"] is None and failed["missing"] == []


def test_mac_result_without_phases_reports_the_gap_instead_of_crashing(tmp_path):
    """Only reachable if the schema check is ever loosened; a missing block must still not raise."""
    run = put_json(tmp_path / MAC / "result.json", {"run_id": MAC, "verdict": "NON_GREEN", "guest": {"ok": False}}).parent
    data = json.loads((run / "result.json").read_text(encoding="utf-8"))
    receipt = receipts.build_mac(run, "result.json", data, None, None, None)
    assert receipt["verdicts"]["guest_phases"] is None and receipt["verdicts"]["verdict"] == "NON_GREEN"
    assert "result.json#guest.phases" in receipt["missing"]


def test_half_harvested_run_gives_nulls_never_zero_and_lists_what_is_missing(tmp_path):
    run = half_harvested(tmp_path)
    receipt = receipts.receipts_for(run)[0]
    assert receipt["identity"]["machine"] is None
    assert receipt["verdicts"]["release_verdict"] == "NON_GREEN" and receipt["verdicts"]["verified_pass"] is False
    assert receipt["seconds"] == {"guest": None, "host_wall": None, "harvest": None, "script_action": None,
                                  "mac_wall": None}
    assert receipt["stages"] == {"list": None, "stage_sum_ok": None, "ok0": None, "parents": None, "tags": None}
    assert receipt["artifacts"] == {
        "proof_run_id": None, "project_sha256": None, "project_sha256_recomputed": None, "gcode_sha256": None,
        "gcode_sha256_recomputed": None, "artifact_hashes_match": None, "teardown_active_processes": 1}
    assert receipt["missing"] == ["process.json#finished_at_ns", "native_worker.json", "native_worker.log",
                                  "proof.json", "proof/0001.3mf", "exports/0001.gcode"]


def test_log_without_stage_lines_gives_an_empty_list_and_a_null_sum(tmp_path):
    run = guest_harvest(tmp_path)
    (run / "native_worker.log").write_bytes(lines("[profile] seeded", "[panel] click_tab(Quality) poll0 strat0: '|= layer'"))
    receipt = receipts.receipts_for(run)[0]
    assert receipt["stages"] == {"list": [], "stage_sum_ok": None, "ok0": [], "parents": [], "tags": []}
    assert receipt["missing"] == []


@pytest.mark.parametrize(("damage", "expected"), [
    ("gcode", False), ("project", False), ("digest", False), ("absent", None)])
def test_changed_artifact_hash_and_absent_artifact_are_told_apart(tmp_path, damage, expected):
    run = guest_harvest(tmp_path)
    if damage == "gcode":
        (run / "exports/0001.gcode").write_bytes(b"tampered")
    elif damage == "project":
        (run / "proof/0001.3mf").write_bytes(b"tampered")
    elif damage == "digest":
        proof = json.loads((run / "proof.json").read_text(encoding="utf-8"))
        put_json(run / "proof.json", {**proof, "gcode_sha256": "0" * 64})
    else:
        (run / "exports/0001.gcode").unlink()
    receipt = receipts.receipts_for(run)[0]
    assert receipt["artifacts"]["artifact_hashes_match"] is expected
    assert ("exports/0001.gcode" in receipt["missing"]) is (damage == "absent")


def test_unverified_in_flight_comparison_is_replaced_by_the_offline_pairing(tmp_path):
    guest_harvest(tmp_path)
    unverified_summary(tmp_path)
    offline_pairing(tmp_path)
    receipt = receipts.receipts_for(guest_run(tmp_path))[0]
    assert receipt["verdicts"]["comparison"] == {
        "status": "paired", "business_status": "SHADOW",
        "unmet_expectations": ["outer_wall_near_178_mm_s", "machine_x_limit_intervention"], "reason": None}
    assert receipt["verdicts"]["comparison_source"] == OFFLINE
    assert receipt["verdicts"]["paired_offline_at"] == "2026-11-25 01:57:02"
    assert receipt["sources"]["verdicts.comparison.status"] == f"native_save_demo/{GUEST}/{OFFLINE}#comparison.status"
    assert receipt["sources"]["verdicts.paired_offline_at"] == f"native_save_demo/{GUEST}/{OFFLINE}#paired_offline_at"
    assert receipt["sources"]["seconds.host_wall"] == f"native_save_demo/{GUEST}/summary.json#host_wall_seconds"
    assert receipt["missing"] == [] and receipt["malformed"] == [] and receipt["warnings"] == []
    assert receipts.markdown([receipt]).splitlines()[2].split(" | ")[7] == "paired/SHADOW (offline)"


def test_offline_pairing_is_not_opened_while_the_in_flight_comparison_is_paired(tmp_path, capsys):
    """The orchestrator writes the file for every compare run it re-pairs, paired ones included: it must change nothing."""
    guest_harvest(tmp_path)
    path = offline_pairing(tmp_path, comparison=UNVERIFIED)
    path.write_text('{"run_id": "x", "compar', encoding="utf-8")      # damaged on purpose: it must not even be opened
    assert receipts.main([str(guest_run(tmp_path).parent), "--runs", GUEST]) == 0
    capsys.readouterr()
    receipt = receipts.receipts_for(guest_run(tmp_path))[0]
    assert receipt["verdicts"]["comparison"] == {
        "status": "paired", "business_status": "SHADOW", "unmet_expectations": ["outer_wall_near_178_mm_s"],
        "reason": None}
    assert receipt["verdicts"]["comparison_source"] == "summary.json"
    assert receipt["verdicts"]["paired_offline_at"] is None and "verdicts.paired_offline_at" not in receipt["sources"]
    assert receipt["malformed"] == [] and receipt["warnings"] == []
    assert receipts.markdown([receipt]).splitlines()[2].split(" | ")[7] == "paired/SHADOW"


def test_offline_pairing_is_not_opened_while_the_summary_has_no_comparison_block(tmp_path, capsys):
    """A scenario that is never paired (uia_param_*) has no comparison block to replace."""
    guest_harvest(tmp_path)
    path = tmp_path / "artifacts" / "native_save_demo" / GUEST / "summary.json"
    summary = json.loads(path.read_text(encoding="utf-8"))
    del summary["comparison"]
    put_json(path, summary)
    offline_pairing(tmp_path).write_text("{", encoding="utf-8")         # damaged on purpose: it must not be opened
    assert receipts.main([str(guest_run(tmp_path).parent), "--runs", GUEST]) == 0
    capsys.readouterr()
    receipt = receipts.receipts_for(guest_run(tmp_path))[0]
    assert receipt["verdicts"]["comparison"] is None
    assert receipt["verdicts"]["comparison_source"] == "summary.json"
    assert receipt["missing"] == [f"native_save_demo/{GUEST}/summary.json#comparison"]
    assert receipt["malformed"] == [] and receipt["warnings"] == []


def test_unverified_in_flight_comparison_without_an_offline_pairing_is_reported_as_it_is(tmp_path):
    guest_harvest(tmp_path)
    unverified_summary(tmp_path)
    receipt = receipts.receipts_for(guest_run(tmp_path))[0]
    assert receipt["verdicts"]["comparison"] == UNVERIFIED
    assert receipt["verdicts"]["comparison_source"] == "summary.json"
    assert receipt["verdicts"]["paired_offline_at"] is None
    assert receipt["missing"] == [] and receipt["malformed"] == [] and receipt["warnings"] == []


@pytest.mark.parametrize(("damage", "reason"), [
    ("truncated", "invalid JSON"),
    ("no-comparison", "comparison: expected dict, got NoneType"),
    ("another-run", "run_id is " + "e5" * 16),
    ("wrong-type", "comparison.status: expected str, got int"),
])
def test_malformed_offline_pairing_falls_back_to_the_in_flight_block(tmp_path, capsys, damage, reason):
    guest_harvest(tmp_path)
    unverified_summary(tmp_path)
    path = offline_pairing(tmp_path)
    if damage == "truncated":
        path.write_text('{"run_id": "x", "compar', encoding="utf-8")
    elif damage == "no-comparison":
        put_json(path, {"run_id": GUEST, "paired_offline_at": "2026-11-25 01:57:02"})
    elif damage == "another-run":
        put_json(path, {"run_id": "e5" * 16, "comparison": PAIRING})
    else:
        put_json(path, {"run_id": GUEST, "comparison": {**PAIRING, "status": 1}})
    assert receipts.main([str(guest_run(tmp_path).parent), "--runs", GUEST]) == 2
    out, err = capsys.readouterr()
    receipt = receipts.receipts_for(guest_run(tmp_path))[0]
    assert receipt["verdicts"]["comparison"] == UNVERIFIED            # the in-flight block stays
    assert receipt["verdicts"]["comparison_source"] == "summary.json"
    assert receipt["verdicts"]["paired_offline_at"] is None
    assert len(receipt["malformed"]) == 1
    assert receipt["malformed"][0].startswith(f"native_save_demo/{GUEST}/{OFFLINE}: ") and reason in receipt["malformed"][0]
    assert receipt["missing"] == []
    assert str(path) in err and reason in err       # reported like any other damaged file ...
    assert GUEST[:8] in out                        # ... while the receipt is still listed


def test_physical_run_takes_its_commit_from_the_ledger_and_shows_it_in_the_table(tmp_path, capsys):
    physical_harvest(tmp_path)
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(json.dumps({"machine": "fa706g3", "scenario": "uia_param_overhang_speeds", "run_id": FA,
                                  "label": "base-2", "commit": "636a733"}) + "\n", encoding="utf-8")
    windows = tmp_path / "artifacts" / "windows_mcp_harvest"
    assert receipts.main([str(windows), "--runs", FA, "--ledger", str(ledger)]) == 0
    row = capsys.readouterr().out.splitlines()[2]
    assert row.split(" | ")[1:5] == ["base-2", "uia_param_overhang_speeds", FA[:8], "636a733"]
    receipt = receipts.receipts_for(windows / FA, ledger=receipts.load_ledger(ledger), ledger_path=ledger)[0]
    assert receipt["identity"]["source_commit"] == "636a733"
    assert receipt["sources"]["identity.source_commit"] == f"{ledger}:1#commit"


def test_ledger_joins_by_run_id_and_the_last_line_wins(tmp_path):
    guest, physical, mac = guest_harvest(tmp_path), physical_harvest(tmp_path), mac_harvest(tmp_path)
    ledger = tmp_path / "ledger.jsonl"
    rows = [{"machine": "win11-test", "scenario": "compare_276_quality", "label": "base-q1", "run_id": GUEST,
             "commit": "1111111"},
            {"machine": "win11-test", "scenario": "compare_276_quality", "label": "base-q2", "run_id": GUEST,
             "commit": "2222222"},
            {"machine": "fa706g3", "scenario": "uia_param_overhang_speeds", "label": "", "run_id": FA},
            {"machine": "mac", "scenario": "walls", "label": "mac-walls-1", "run_id": MAC, "commit": "636a733"}]
    ledger.write_text("\n".join(json.dumps(row) for row in rows) + "\n\n", encoding="utf-8")
    entries = receipts.load_ledger(ledger)

    first, second, third = (receipts.receipts_for(run, ledger=entries, ledger_path=ledger)[0]
                            for run in (guest, physical, mac))
    assert first["identity"]["label"] == "base-q2" and first["sources"]["identity.label"] == f"{ledger}:2#label"
    assert first["identity"]["source_commit"] == SHA          # the host summary outranks the ledger
    assert second["identity"]["label"] is None                # fa_run.py writes "" when no label was set
    assert second["identity"]["source_commit"] is None and f"{ledger}:3#commit" in second["missing"]
    assert third["identity"]["label"] == "mac-walls-1" and third["identity"]["source_commit"] == "636a733"
    assert third["sources"]["identity.source_commit"] == f"{ledger}:4#commit"
    without = receipts.receipts_for(guest)[0]
    assert without["identity"]["label"] is None and without["sources"]["identity.label"] == "no --ledger given"


def test_machine_override_is_recorded_without_hiding_what_the_files_say(tmp_path):
    run = physical_harvest(tmp_path)
    receipt = receipts.receipts_for(run, machine="guest")[0]
    assert receipt["identity"]["machine"] == "guest" and receipt["identity"]["machine_inferred"] == "fa706g3"
    assert receipt["sources"]["identity.machine"] == "--machine guest"
    assert f"native_save_demo/{FA}/summary.json" in receipt["missing"]     # a guest run is expected to have one
    assert any("--machine guest" in warning and "fa706g3" in warning for warning in receipt["warnings"])


def test_table_keeps_the_column_order_and_marks_what_is_not_available(tmp_path):
    runs = [guest_harvest(tmp_path), physical_harvest(tmp_path), mac_harvest(tmp_path)]
    table = receipts.markdown([receipts.receipts_for(run)[0] for run in runs])
    assert table.splitlines() == [
        HEADER,
        "|" + "---|" * 14,
        f"| guest | - | compare_276_quality | {GUEST[:8]} | {SHA[:7]} | SHADOW | true | paired/SHADOW | true "
        "| 189.960 | 222.828 | 76.422 | 13.000 | none |",
        f"| fa706g3 | - | uia_param_overhang_speeds | {FA[:8]} | - | SHADOW | true | - | true "
        "| 231.998 | - | 123.000 | 3.875 | locate.Overhang speed; field.Overhang speed; field.Gap |",
        f"| mac | - | walls | {MAC[:8]} | - | SHADOW | - | - | - | - | 116.916 | - | - | - |"]


@pytest.mark.parametrize("kind", sorted(HARVESTS))
def test_every_value_says_which_file_it_came_from(tmp_path, kind):
    for receipt in receipts.receipts_for(HARVESTS[kind](tmp_path)):
        for path, value in leaves({name: receipt[name] for name in SECTIONS}):
            if value is not None:
                source = receipt["sources"].get(path)
                assert isinstance(source, str) and source, path
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    assert re.search(r"\.(json|log|3mf|gcode)", source), path


@pytest.mark.parametrize("kind", sorted(HARVESTS))
def test_a_null_with_a_source_is_always_accounted_for_in_missing(tmp_path, kind):
    """A null that names a file means "expected from that file, absent"; a null without a source does not apply."""
    for receipt in receipts.receipts_for(HARVESTS[kind](tmp_path)):
        for section in ("seconds", "stages", "artifacts"):
            for path, value in leaves(receipt[section], section):
                source = receipt["sources"].get(path)
                if value is None and source is not None:
                    name = source.split("#")[0]
                    assert name in receipt["missing"] or any(
                        entry.startswith(name + "#") for entry in receipt["missing"]), path


@pytest.mark.parametrize(("line", "stage"), [
    ("[flow276] save ok=1 seconds=8.0932", ("save", 1, 8.0932)),
    ("[timing] edit_readback.Outer wall speed ok=0 seconds=0.5", ("edit_readback.Outer wall speed", 0, 0.5)),
    ("[t] a.b ok=1 seconds=12", ("a.b", 1, 12.0)),
])
def test_stage_line_accepts_any_single_word_tag(line, stage):
    assert [(s["stage"], s["ok"], s["seconds"]) for s in receipts.parse_stages(line + "\n")] == [stage]


@pytest.mark.parametrize("line", [
    "[profile] seeded C:\\x\\profile",
    "[panel] click_tab(Quality) poll0 strat0: '|= layer height ok=1 seconds=9'",
    "[win util] save ok=1 seconds=1",
    "[flow276] save ok=2 seconds=1",
    "[flow276] save ok=1 seconds=x",
    "[flow276] save ok=1 seconds=-1",
])
def test_lines_without_the_stage_shape_are_not_stages(line):
    assert receipts.parse_stages(line + "\r\n") == []


def test_runs_are_looked_up_under_every_root(tmp_path, capsys):
    guest_harvest(tmp_path)
    mac_harvest(tmp_path)
    windows, macos = tmp_path / "artifacts" / "windows_mcp_harvest", tmp_path / "artifacts" / "mac_project_copy"
    assert receipts.main([str(windows), str(macos), "--runs", f"{GUEST}, {MAC}"]) == 0
    assert [line.split("|")[1].strip() for line in capsys.readouterr().out.splitlines()[2:]] == ["guest", "mac"]


def test_harvest_root_without_runs_is_refused(tmp_path, capsys):
    guest_harvest(tmp_path)
    assert receipts.main([str(tmp_path / "artifacts" / "windows_mcp_harvest")]) == 2
    assert "--runs" in capsys.readouterr().err


def test_unknown_run_id_and_missing_ledger_exit_2(tmp_path, capsys):
    guest_harvest(tmp_path)
    windows = tmp_path / "artifacts" / "windows_mcp_harvest"
    assert receipts.main([str(windows), "--runs", "e5" * 16]) == 2
    assert "e5" * 16 in capsys.readouterr().err
    assert receipts.main([str(windows), "--runs", GUEST, "--ledger", str(tmp_path / "no-ledger.jsonl")]) == 2
    assert "no-ledger.jsonl" in capsys.readouterr().err


@pytest.mark.parametrize(("damage", "named"), [
    ("truncated-json", "process.json: invalid JSON"),
    ("wrong-type", "result.json#verified_pass: expected bool, got str"),
    ("not-an-object", "process.json: top level is list, not an object"),
    ("timestamps-reversed", "process.json#finished_at_ns - started_at_ns: finished_at_ns precedes started_at_ns"),
])
def test_malformed_file_exits_2_naming_the_file_and_still_lists_the_healthy_run(tmp_path, capsys, damage, named):
    guest_harvest(tmp_path)
    broken = tmp_path / "artifacts" / "windows_mcp_harvest" / FA
    put_json(broken / "result.json", PASSING)
    put_json(broken / "process.json", {"run_id": FA, "started_at_ns": STARTED, "finished_at_ns": STARTED + 10**9})
    if damage == "truncated-json":
        (broken / "process.json").write_text('{"run_id": "x", "started_at_ns": 1,', encoding="utf-8")
    elif damage == "wrong-type":
        put_json(broken / "result.json", {**PASSING, "verified_pass": "true"})
    elif damage == "not-an-object":
        (broken / "process.json").write_text("[1, 2]", encoding="utf-8")
    else:
        put_json(broken / "process.json", {"started_at_ns": STARTED + 10**9, "finished_at_ns": STARTED})
    assert receipts.main([str(broken.parent), "--runs", f"{GUEST},{FA}"]) == 2
    out, err = capsys.readouterr()
    assert named in err and str(broken) in err
    assert GUEST[:8] in out and FA[:8] not in out


def test_damaged_ledger_line_exits_2_and_keeps_the_other_evidence(tmp_path, capsys):
    run = guest_harvest(tmp_path)
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(json.dumps({"run_id": GUEST, "label": "base-q1"}) + "\n{not json}\n", encoding="utf-8")
    assert receipts.main([str(run), "--ledger", str(ledger)]) == 2
    out, err = capsys.readouterr()
    assert f"{ledger}: line 2: invalid JSON" in err and GUEST[:8] in out


def test_unknown_machine_choice_is_a_usage_error(tmp_path):
    with pytest.raises(SystemExit) as stopped:
        receipts.main([str(tmp_path), "--machine", "vm"])
    assert stopped.value.code == 2


def test_same_run_twice_is_refused(tmp_path, capsys):
    guest_harvest(tmp_path)
    windows = tmp_path / "artifacts" / "windows_mcp_harvest"
    assert receipts.main([str(windows), str(windows), "--runs", GUEST]) == 2
    assert "more than once" in capsys.readouterr().err


def test_json_writes_one_receipt_per_run_and_leaves_the_harvest_untouched(tmp_path, capsys):
    guest_harvest(tmp_path)
    physical_harvest(tmp_path)
    before = snapshot(tmp_path / "artifacts")
    out = tmp_path / "receipts"
    windows = tmp_path / "artifacts" / "windows_mcp_harvest"
    assert receipts.main([str(windows), "--runs", f"{GUEST},{FA}", "--json", str(out)]) == 0
    capsys.readouterr()
    assert snapshot(tmp_path / "artifacts") == before
    assert sorted(path.name for path in out.iterdir()) == sorted([f"{FA}.json", f"{GUEST}.json"])
    saved = json.loads((out / f"{GUEST}.json").read_text(encoding="utf-8"))
    assert saved == receipts.receipts_for(windows / GUEST)[0]


def test_json_directory_inside_the_harvest_is_refused(tmp_path):
    guest_harvest(tmp_path)
    windows = tmp_path / "artifacts" / "windows_mcp_harvest"
    before = snapshot(tmp_path / "artifacts")
    assert receipts.main([str(windows), "--runs", GUEST, "--json", str(windows)]) == 2
    assert receipts.main([str(windows / GUEST), "--json", str(windows / GUEST / "receipts")]) == 2
    assert snapshot(tmp_path / "artifacts") == before


def test_json_directory_is_not_created_when_no_receipt_could_be_built(tmp_path):
    broken = tmp_path / "artifacts" / "windows_mcp_harvest" / FA
    broken.mkdir(parents=True)
    (broken / "process.json").write_text("{", encoding="utf-8")
    out = tmp_path / "receipts"
    assert receipts.main([str(broken.parent), "--runs", FA, "--json", str(out)]) == 2
    assert not out.exists()


def test_integer_seconds_are_shown_with_the_same_three_decimals(tmp_path):
    run = guest_harvest(tmp_path)
    path = tmp_path / "artifacts" / "native_save_demo" / GUEST / "summary.json"
    put_json(path, {**json.loads(path.read_text(encoding="utf-8")), "host_wall_seconds": 223, "harvest_seconds": 2})
    row = receipts.markdown(receipts.receipts_for(run)).splitlines()[2]
    assert row.split(" | ")[9:12] == ["189.960", "223.000", "76.422"]


def test_command_line_entry_point_prints_the_table(tmp_path):
    guest_harvest(tmp_path)
    result = subprocess.run(
        [sys.executable, "-B", str(ROOT / "tools" / "ninehour_receipts.py"),
         str(tmp_path / "artifacts" / "windows_mcp_harvest"), "--runs", GUEST],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=False)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[:1] == [HEADER] and GUEST[:8] in result.stdout
