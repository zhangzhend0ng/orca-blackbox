"""Negative challenges for acceptance identity, stop gates and partial logs."""
import json
from copy import deepcopy

import pytest

from harness.native_matrix import FIXTURE_SCENARIOS, RECORDED_SCENARIOS, SCENARIOS, completed_progress
from harness.native_save_session import native_contract, native_spec
from harness.run_verdict import contract_digest
from tools.zcode_matrix import grade


def test_registered_matrix_contracts_are_distinct_and_closed():
    from harness.native_matrix import BOUND_MODEL_MOVE
    script_only = RECORDED_SCENARIOS | set(FIXTURE_SCENARIOS) | {BOUND_MODEL_MOVE}
    scenarios = [scenario for scenario in SCENARIOS if scenario not in script_only]
    hashes = [contract_digest(native_contract("zcode", s)) for s in scenarios]
    assert len(set(hashes)) == len(scenarios)
    for scenario, digest in zip(scenarios, hashes):
        assert native_spec(digest) == ("zcode", scenario)
    for scenario in script_only:
        with pytest.raises(ValueError):
            native_contract("zcode", scenario)
    with pytest.raises(ValueError):
        native_contract("codex", "strength_a")
    with pytest.raises(ValueError):
        native_contract("zcode", "unregistered")
    assert native_contract("zcode", "safety_timeout").limits.timeout_s == 120


def test_partial_progress_tail_cannot_trigger_stop(tmp_path):
    path = tmp_path/"progress.ndjson"
    record = {"native_tool_calls": [{"tool": "Click", "status": "completed"}]}
    path.write_text(json.dumps(record))
    assert completed_progress(path) == []
    path.write_text(json.dumps(record)+"\n{" )
    assert completed_progress(path) == record["native_tool_calls"]


def receipts():
    return (
        {"host_job": {"active_processes": 0}, "sources_unchanged": True, "toolset_verified": True,
         "fault_event": {"completed_input_tools": ["Click"]}, "timeout_observed_at_ns": 100},
        {"cleanup_confirmed": True, "release_eligible": False, "verified_pass": False,
         "execution_status": "timeout", "release_verdict": "NON_GREEN"},
        {"active_processes": 0, "job_assigned": True},
        {"token_exists": False, "cleanup_confirmed": True},
        [{"tool": "Click", "error": None}],
    )


@pytest.mark.parametrize("fault", [None, "business_pass", "cleanup_unknown", "token_left",
                                  "no_real_input", "no_trigger", "wrong_status", "tool_escape"])
def test_expected_timeout_requires_trigger_and_actual_stop_receipts(fault):
    h, r, p, t, trace = deepcopy(receipts())
    if fault == "business_pass": r["verified_pass"] = True
    if fault == "cleanup_unknown": r["cleanup_confirmed"] = False
    if fault == "token_left": t["token_exists"] = True
    if fault == "no_real_input": trace = []
    if fault == "no_trigger": h.pop("fault_event")
    if fault == "wrong_status": r["execution_status"] = "cancelled"
    if fault == "tool_escape": trace.append({"tool": "Click", "error": "unowned_target"})
    assert grade("safety_timeout", h, r, p, t, trace) is (fault is None)


def test_guard_disconnect_requires_same_live_global_guard():
    h, r, p, t, trace = receipts()
    h["cancel"] = {"revoked_at_ns": 100}
    h.update(error="RuntimeError:ip_guard_unverified:URLError", guard_checks=[{"guard_pid": 123}],
             global_guard_after={"ready": True, "guard_pid": 123})
    r["execution_status"] = "cancelled"
    assert grade("safety_guard_disconnect", h, r, p, t, trace)
    h["global_guard_after"]["guard_pid"] = 456
    assert not grade("safety_guard_disconnect", h, r, p, t, trace)


def test_closed_run_local_guard_transport_fails_closed(monkeypatch, tmp_path):
    from harness.guard_fault import GuardTransport
    from harness.ip_guard import IPGuard
    token = tmp_path/"clash-guard/status-token"
    token.parent.mkdir()
    token.write_text("a"*32)
    monkeypatch.setattr("harness.ip_guard.Path.home", lambda: tmp_path)
    transport = GuardTransport()
    port = transport.port
    transport.close()
    with pytest.raises(RuntimeError, match="ip_guard_unverified"):
        IPGuard(status_port=port).check()
