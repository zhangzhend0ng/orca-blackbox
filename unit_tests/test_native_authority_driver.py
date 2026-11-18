"""Host authority protocol challenges with a fake Node app-server only.

No MCP bridge, credentials, model, VM or GUI is started. The fake app-server
writes the sidecar that a trusted bridge would write before returning events.
"""
import copy
import json
from pathlib import Path
import shutil
import subprocess

import pytest

RUN_ID = "a" * 32
DRIVER = Path(__file__).resolve().parents[1] / "tools/zcode_session_driver.mjs"
FAKE_SERVER = r"""
const fs=require('node:fs');
const path=require('node:path');
const config=JSON.parse(fs.readFileSync(path.join(process.cwd(),'fake-config.json'),'utf8'));
const selected={providerId:'new-provider',modelId:'glm-5.3-flash'};
const settings={model:{current:selected},thoughtLevel:{current:'low'}};
fs.writeFileSync(path.join(process.cwd(),'fake-concurrency.txt'),process.env.ZCODE_MAX_TOOL_CONCURRENCY??'');
const rl=require('node:readline').createInterface({input:process.stdin});
let polls=0;
rl.on('line',line=>{
 const q=JSON.parse(line);let result={};
 fs.appendFileSync(path.join(process.cwd(),'fake-requests.ndjson'),JSON.stringify(q)+'\n');
 if(q.method==='session/create')result={session:{sessionId:'single_turn'},settings};
 if(q.method==='session/read')result={settings};
 if(q.method==='session/events'){
  const index=polls++;
  fs.writeFileSync(path.join(process.cwd(),'authority.ndjson'),config.sidecar);
  const batch=config.batches[index];
  if(!batch)throw Error('unexpected polling after fixed events');
  result={events:batch};
 }
 process.stdout.write(JSON.stringify({id:q.id,result})+'\n');
});
rl.on('close',()=>process.exit(0));
"""


def receipt(seq=1, tool="Screenshot", decision="completed"):
    row = dict(protocol="native-authority-1", run_id=RUN_ID, seq=seq,
               tool=tool, decision=decision, dispatched=decision == "completed")
    if decision != "completed":
        row["error_code"] = ("native_type_requires_owned_edit" if decision == "recoverable"
                             else "native_foreground_not_owned")
    if decision == "recoverable":
        row["recovery"] = dict(protocol="native-recovery-1", run_id=RUN_ID,
            seq=seq, tool=tool, error_code=row["error_code"],
            dispatch_state="not_dispatched", decision="recoverable",
            requires_observation=True, budget_used=1, facts_sha256="b" * 64)
    return row


def tool_events(call_id, tool, *, error=False):
    return [dict(type="tool.updated", payload=dict(kind="scheduled", toolCallId=call_id,
                toolName="mcp__windows_mcp__" + tool)),
            dict(type="tool.updated", payload=(dict(kind="error", toolCallId=call_id,
                error={"type": "ToolError", "message": "authority rejected"}) if error else
                dict(kind="result", toolCallId=call_id,
                     result={"content": [{"type": "text", "text": "ToolError wrapped as normal content"}]})))]


def run_driver(tmp_path, rows, events, *, enabled=True, suffix="", count=None, request_ids=None,
               idle_after=None, scenario="base", uia_refresh=False):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node runtime unavailable")
    events = copy.deepcopy(events)
    if count is None:
        count = len({e["payload"]["toolCallId"] for e in events if e["type"] == "tool.updated"})
    events.append(dict(type="turn.completed", payload=dict(resultType="success", toolCallCount=count)))
    for seq, event in enumerate(events, 1):
        event["seq"] = seq
    sidecar = "".join(json.dumps({"request_id": (request_ids[index - 1] if request_ids is not None
                                   else "mcp-" + str(index)), "authority": row}) + "\n"
                      for index, row in enumerate(rows, 1)) + suffix
    batches = [events] if idle_after is None else [events[:idle_after], [], [], events[idle_after:]]
    (tmp_path / "fake-config.json").write_text(json.dumps(dict(sidecar=sidecar, batches=batches)))
    server = tmp_path / "fake-server.cjs"
    server.write_text(FAKE_SERVER)
    spec = dict(root=str(tmp_path), bundle=str(server), workspace=str(tmp_path), run_id=RUN_ID,
                python="MUST_NOT_EXECUTE", bridge="MUST_NOT_EXECUTE", prompt="synthetic protocol test",
                authority_protocol="native-authority-1", authority_log=str(tmp_path / "authority.ndjson"),
                recovery_enabled=enabled, scenario=scenario, uia_refresh_enabled=uia_refresh)
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps(spec))
    result = subprocess.run([node, str(DRIVER), str(spec_file)], capture_output=True, timeout=15)
    actor = tmp_path / "actor.json"
    assert actor.exists(), result.stderr.decode(errors="replace")
    report = json.loads(actor.read_text())
    requests = [json.loads(line) for line in (tmp_path / "fake-requests.ndjson").read_text().splitlines()]
    assert sum(q.get("method") == "session/send" for q in requests) == 1
    assert sum(q.get("method") == "session/create" for q in requests) == 1
    assert any(q.get("method") == "session/close" for q in requests)
    return result.returncode, report


def assert_stopped(result):
    code, report = result
    assert code == 1, report
    assert report["error"] and report["error"].startswith("native_"), report


def test_surface_success_cannot_hide_guest_fatal(tmp_path):
    result = run_driver(tmp_path, [receipt(decision="fatal")], tool_events("c1", "Screenshot"))
    assert_stopped(result)
    assert result[1]["error"].startswith("native_authority_fatal")


def test_recoverable_error_event_continues_original_turn_after_observation(tmp_path):
    events = tool_events("c1", "Type", error=True) + tool_events("c2", "Screenshot") + tool_events("c3", "Type")
    code, report = run_driver(tmp_path, [receipt(1, "Type", "recoverable"), receipt(2), receipt(3, "Type")], events)
    assert code == 0, report
    assert report["error"] is None
    assert [call["status"] for call in report["native_tool_calls"]] == ["recoverable_rejection", "completed", "completed"]
    assert report["native_tool_calls"][0]["error_event"] is True


@pytest.mark.parametrize("diagnostic", [True, False])
def test_diagnostic_receipt_accepted_only_in_its_own_contract(tmp_path, diagnostic):
    from harness.native_diagnostic_recovery import ERROR_CODE, PROTOCOL, SCENARIO

    injected = receipt(1, "Type", "recoverable")
    injected["error_code"] = ERROR_CODE
    injected["recovery"].update(error_code=ERROR_CODE, protocol=PROTOCOL)
    events = [dict(type="turn.started")]
    events += tool_events("c1", "Type", error=True) + tool_events("c2", "Screenshot") + tool_events("c3", "Type")
    code, report = run_driver(tmp_path, [injected, receipt(2), receipt(3, "Type")], events,
                              enabled=not diagnostic, scenario=SCENARIO if diagnostic else "recovery_owned_edit")
    if not diagnostic:
        assert code == 1 and report["error"] == "native_recovery_receipt_invalid"
    else:
        assert code == 0, report
        turn = report["diagnostic_turn"]
        assert turn["session_send_count"] == turn["turn_started_count"] == turn["turn_completed_count"] == 1
        assert turn["calls"][0] == dict(seq=1, tool="Type", decision="recoverable", dispatched=False,
                                         facts_sha256="b" * 64)


def test_completed_receipt_allows_clean_turn(tmp_path):
    code, report = run_driver(tmp_path, [receipt()], tool_events("c1", "Screenshot"))
    assert code == 0 and report["error"] is None


def test_progress_excludes_full_receipts_and_skips_idle_polls(tmp_path):
    from harness.native_matrix import completed_progress

    events = tool_events("c1", "Click") + tool_events("c2", "Screenshot")
    code, report = run_driver(tmp_path, [receipt(1, "Click"), receipt(2)], events, idle_after=2)
    assert code == 0, report
    path = tmp_path / "progress.ndjson"
    completed = [{"tool": "Click", "status": "completed"}, {"tool": "Screenshot", "status": "completed"}]
    assert [json.loads(line)["native_tool_calls"] for line in path.read_text().splitlines()] == [
        [], completed[:1], completed,
    ]
    assert completed_progress(path) == completed
    assert report["native_tool_calls"][0]["authority"] == receipt(1, "Click")


def test_informational_tool_update_without_call_id_does_not_abort_clean_tool(tmp_path):
    events = tool_events("c1", "Screenshot")
    events.append(dict(type="tool.updated", payload=dict(kind="progress")))
    code, report = run_driver(tmp_path, [receipt()], events, count=1)
    assert code == 0 and report["error"] is None
    assert report["informational_tool_event_kinds"] == {"progress": 1}


def test_recoverable_error_followed_by_result_consumes_receipt_once(tmp_path):
    events = tool_events("c1", "Type", error=True)
    events.append(tool_events("c1", "Type")[-1])
    events += tool_events("c2", "Snapshot")
    code, report = run_driver(tmp_path, [receipt(1, "Type", "recoverable"), receipt(2, "Snapshot")], events)
    assert code == 0 and report["error"] is None, report


def test_repeated_wire_request_id_rejected(tmp_path):
    assert_stopped(run_driver(tmp_path, [receipt(), receipt(2)],
        tool_events("c1", "Screenshot") + tool_events("c2", "Screenshot"), request_ids=["same", "same"]))


def test_unscheduled_result_rejected(tmp_path):
    assert_stopped(run_driver(tmp_path, [receipt()], [tool_events("c1", "Screenshot")[-1]]))


@pytest.mark.parametrize("call_id", [None, "", 7])
def test_missing_or_invalid_native_call_identity_rejected(tmp_path, call_id):
    assert_stopped(run_driver(tmp_path, [receipt()], tool_events(call_id, "Screenshot")))


def test_duplicate_recoverable_error_rejected(tmp_path):
    events = tool_events("c1", "Type", error=True)
    events.append(copy.deepcopy(events[-1]))
    events += tool_events("c2", "Screenshot")
    assert_stopped(run_driver(tmp_path, [receipt(1, "Type", "recoverable"), receipt(2)], events))


@pytest.mark.parametrize("field,value", [
    ("protocol", "forged"), ("run_id", "c" * 32), ("seq", 2),
    ("seq", True), ("tool", "Click"), ("decision", "success"),
    ("dispatched", False), ("dispatched", "true"),
])
def test_wrong_receipt_identity_or_dispatch_stops(tmp_path, field, value):
    row = receipt(); row[field] = value
    assert_stopped(run_driver(tmp_path, [row], tool_events("c1", "Screenshot")))


def test_missing_receipt_stops_even_when_native_claims_success(tmp_path):
    assert_stopped(run_driver(tmp_path, [], tool_events("c1", "Screenshot")))


@pytest.mark.parametrize("suffix", ['{"authority":', '{"untrusted":"complete-but-no-newline"}'])
def test_partial_sidecar_tail_cannot_be_ignored(tmp_path, suffix):
    assert_stopped(run_driver(tmp_path, [receipt()], tool_events("c1", "Screenshot"), suffix=suffix))


def test_extra_receipt_cannot_be_ignored(tmp_path):
    assert_stopped(run_driver(tmp_path, [receipt(), receipt(2)], tool_events("c1", "Screenshot")))


def test_two_scheduled_calls_before_completion_are_rejected(tmp_path):
    one, two = tool_events("c1", "Screenshot"), tool_events("c2", "Type")
    assert_stopped(run_driver(tmp_path, [receipt(), receipt(2, "Type")], [one[0], two[0], one[1], two[1]]))


def serial_batch(*calls, concurrent=False):
    order = [call[0]["payload"]["toolCallId"] for call in calls]
    groups = [order] if concurrent else [[cid] for cid in order]
    schedule = dict(executionOrder=order, parallelGroups=groups)
    announced, executed = [], []
    for i, (scheduled, terminal) in enumerate(calls):
        scheduled["payload"].update(schedule=schedule, parallelGroupIndex=0 if concurrent else i)
        start = dict(type="tool.updated", payload=dict(kind="started", toolCallId=order[i],
                     toolName=scheduled["payload"]["toolName"]))
        announced.append(scheduled)
        executed.extend((start, terminal))
    return announced + executed


def test_uia_can_announce_multiple_serial_observations(tmp_path):
    events = serial_batch(tool_events("c1", "Snapshot"), tool_events("c2", "Screenshot"))
    code, report = run_driver(tmp_path, [receipt(1, "Snapshot"), receipt(2)], events, scenario="uia_y_quality")
    assert code == 0, report
    assert (tmp_path / "fake-concurrency.txt").read_text() == "1"
    assert [call["authority"]["seq"] for call in report["native_tool_calls"]] == [1, 2]


def test_uia_rejects_genuine_parallel_group(tmp_path):
    events = serial_batch(tool_events("c1", "Snapshot"), tool_events("c2", "Click"), concurrent=True)
    code, report = run_driver(tmp_path, [], events, scenario="uia_y_quality")
    assert code == 1 and report["error"] == "native_serial_schedule_invalid"


def test_uia_rejects_out_of_order_tool_start(tmp_path):
    events = serial_batch(tool_events("c1", "Snapshot"), tool_events("c2", "Screenshot"))
    events[2], events[4] = events[4], events[2]
    code, report = run_driver(tmp_path, [], events, scenario="uia_y_quality")
    assert code == 1 and report["error"] == "native_serial_start_out_of_order"


def uia_refresh_receipt():
    row = receipt(1, "Click", "recoverable")
    row["error_code"] = row["recovery"]["error_code"] = "native_uia_refresh_required"
    return row


def test_uia_refresh_receipt_continues_after_snapshot(tmp_path):
    events = serial_batch(tool_events("c1", "Click", error=True))
    events += serial_batch(tool_events("c2", "Snapshot"))
    events += serial_batch(tool_events("c3", "Click"))
    code, report = run_driver(tmp_path, [uia_refresh_receipt(), receipt(2, "Snapshot"), receipt(3, "Click")],
                              events, enabled=False, scenario="uia_y_quality", uia_refresh=True)
    assert code == 0, report
    assert [c["status"] for c in report["native_tool_calls"]] == ["recoverable_rejection", "completed", "completed"]


def test_uia_refresh_receipt_does_not_accept_wait_as_observation(tmp_path):
    events = serial_batch(tool_events("c1", "Click", error=True))
    events += serial_batch(tool_events("c2", "Wait"), tool_events("c3", "Click"))
    code, report = run_driver(tmp_path, [uia_refresh_receipt(), receipt(2, "Wait"), receipt(3, "Click")],
                              events, enabled=False, scenario="uia_y_quality", uia_refresh=True)
    assert code == 1 and report["error"] == "native_recovery_observation_required"


def test_reused_completed_call_id_cannot_reuse_cached_authority(tmp_path):
    events = tool_events("c1", "Screenshot") + tool_events("c1", "Screenshot")
    assert_stopped(run_driver(tmp_path, [receipt()], events, count=1))


def test_duplicate_result_cannot_reuse_authority(tmp_path):
    events = tool_events("c1", "Screenshot")
    events.append(copy.deepcopy(events[-1]))
    assert_stopped(run_driver(tmp_path, [receipt()], events, count=1))


def test_old_contract_cannot_accept_recoverable_receipt(tmp_path):
    assert_stopped(run_driver(tmp_path, [receipt(1, "Type", "recoverable")],
                             tool_events("c1", "Type", error=True), enabled=False))


@pytest.mark.parametrize("field,value", [("run_id", "c" * 32), ("seq", 2), ("tool", "Click"),
    ("dispatch_state", "dispatched"), ("requires_observation", False), ("budget_used", 3)])
def test_forged_recovery_receipt_stops(tmp_path, field, value):
    row = receipt(1, "Type", "recoverable"); row["recovery"][field] = value
    assert_stopped(run_driver(tmp_path, [row], tool_events("c1", "Type", error=True)))


def test_recovery_cannot_complete_without_observation(tmp_path):
    assert_stopped(run_driver(tmp_path, [receipt(1, "Type", "recoverable")], tool_events("c1", "Type", error=True)))


def test_wait_is_not_recovery_observation(tmp_path):
    events = tool_events("c1", "Type", error=True) + tool_events("c2", "Wait") + tool_events("c3", "Type")
    assert_stopped(run_driver(tmp_path, [receipt(1, "Type", "recoverable"), receipt(2, "Wait"), receipt(3, "Type")], events))
