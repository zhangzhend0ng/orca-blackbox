"""Small policy/evidence challenges and a local fake-protocol client check.

These are not model or GUI coverage.
"""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from harness.ip_guard import validate_status
from harness.native_save_session import native_actor, native_contract, verify_saved
from harness.run_verdict import contract_digest
from tools.windows_mcp_zcode_probe import model_io_summary, provider_metadata
from unit_tests.test_native_save import native_evidence


def status():
    return dict(ready=True, state="OK", time=100, last_us_age=3, evidence_ttl=1800,
                guard_pid=123, hosts_block_active=False, group_on_reject=False)


@pytest.mark.parametrize("key,value", [
    ("ready", 1), ("ready", False), ("state", "VERIFY_RETRY"), ("time", 80),
    ("time", 103), ("time", float("nan")), ("time", True),
    ("last_us_age", 1801), ("evidence_ttl", float("inf")),
    ("hosts_block_active", True), ("group_on_reject", True), ("guard_pid", True),
])
def test_guard_rejects_unverified_stale_and_blocked_status(key, value):
    data=status();data[key]=value
    with pytest.raises(ValueError):validate_status(data,100)


def test_guard_accepts_fresh_ready_snapshot_without_returning_credentials():
    assert validate_status(status(),100)=={k:v for k,v in status().items()
        if k not in {"hosts_block_active","group_on_reject"}}


def test_native_actor_registry_preserves_codex_digest_and_rejects_unknown_contract():
    assert contract_digest(native_contract())=="ee2dd9ed8b78898962450b9f3c540ad41ad8e19196ce8bc4ef3f25a7d33e2517"
    assert native_actor(contract_digest(native_contract("zcode")))=="zcode"
    with pytest.raises(ValueError):native_actor("0"*64)
    with pytest.raises(ValueError):native_contract("other")


@pytest.mark.parametrize("fault", [None,"provider_id","model_id","guard_checked","sources_unchanged","toolset_verified"])
def test_zcode_proof_requires_exact_vendor_and_completed_safety_receipt(native_evidence, fault):
    snapshot=native_evidence;snapshot.contract=native_contract("zcode")
    root=snapshot.artifact_dir
    proof=json.loads((root/"proof.json").read_text());proof["contract_sha256"]=contract_digest(snapshot.contract)
    (root/"proof.json").write_text(json.dumps(proof))
    host=json.loads((root/"host_done.json").read_text())
    host.update(actor="zcode",provider_id="new-provider",model_id="glm-5.3-flash",
                guard_checked=True,sources_unchanged=True,toolset_verified=True)
    if fault:host[fault]="wrong" if fault.endswith("_id") else False
    (root/"host_done.json").write_text(json.dumps(host))
    assert verify_saved(snapshot).evidence_complete is (fault is None)


@pytest.mark.parametrize("host,protocol", [("other.example","anthropic-messages"),("ai-gateway.s.com","openai-chat-completions")])
def test_provider_metadata_rejects_a_different_company_endpoint(tmp_path, host, protocol):
    p=tmp_path/"provider.json"
    p.write_text(json.dumps({"config":{"providerConfigRules":{"providerRules":[{
        "providerId":"new-provider","providerName":"Snapmaker","config":{
            "api":{"type":protocol,"baseUrl":"https://"+host+"/v1"},
            "access":{"type":"api-key","apiKey":"test-placeholder"},
            "personalModelIds":["glm-5.3-flash"]}}]}}}))
    with pytest.raises(ValueError, match="provider_changed"):provider_metadata(p)


@pytest.mark.parametrize("fault", [None,"provider","tools"])
def test_native_model_io_requires_actual_vendor_and_exact_gui_toolset(tmp_path, fault):
    from harness.native_save_policy import NATIVE_TOOLS
    root=tmp_path/"storage/cli/rollout";root.mkdir(parents=True)
    data={"request":{"toolNames":["mcp__windows_mcp__"+n for n in NATIVE_TOOLS]},
          "response":{"usage":{}},"model":{"providerId":"new-provider","modelId":"glm-5.3-flash"}}
    if fault=="provider":data["model"]["providerId"]="other"
    if fault=="tools":data["request"]["toolNames"].append("Bash")
    (root/"model-io-test.jsonl").write_text(json.dumps(data)+"\n")
    if fault:
        with pytest.raises(ValueError):model_io_summary(tmp_path)
    else:assert len(model_io_summary(tmp_path))==1


FAKE_SERVER=r"""
const rl=require('node:readline').createInterface({input:process.stdin});
const fault=process.env.ZCODE_TEST_FAULT;
rl.on('line',line=>{
 const q=JSON.parse(line);let result={};
 if(q.id==='preferences'){
  require('node:fs').writeFileSync(process.env.ZCODE_TEST_DECISION+'.preferences',JSON.stringify(q.result));return;
 }
 if(q.method==='runtime/capabilities')result={};
 if(q.method==='session/create'){
  process.stdout.write(JSON.stringify({id:'preferences',method:'session/requestRuntimePreferences',params:{}})+'\n');
  result={session:{id:'sess_test'},settings:{model:{current:{providerId:fault==='wrong_model'?'other':'new-provider',modelId:'glm-5.3-flash'}},thoughtLevel:{current:'low'}}};
 }
 if(q.method==='session/send'){
  process.stdout.write(JSON.stringify({id:'permission',method:'interaction/requestPermission',params:{toolName:'Bash',input:{command:'DO_NOT_EXECUTE'}}})+'\n');
 }
 if(q.method==='session/events')result={events:[]};
 if(q.id==='permission')require('node:fs').writeFileSync(process.env.ZCODE_TEST_DECISION,JSON.stringify(q.result));
 else process.stdout.write(JSON.stringify({id:q.id,result})+'\n');
});
rl.on('close',()=>process.exit(0));
"""


@pytest.mark.parametrize("fault", ["wrong_model","permission"])
def test_protocol_client_stops_model_drift_and_denies_non_gui_permission(tmp_path, monkeypatch, fault):
    node=shutil.which("node")
    if not node:pytest.skip("Node runtime unavailable")
    server=tmp_path/"fake.cjs";server.write_text(FAKE_SERVER)
    decision=tmp_path/"decision.json"
    monkeypatch.setenv("ZCODE_TEST_FAULT",fault)
    monkeypatch.setenv("ZCODE_TEST_DECISION",str(decision))
    spec=tmp_path/"spec.json"
    spec.write_text(json.dumps(dict(root=str(tmp_path),bundle=str(server),workspace=str(tmp_path),
        run_id="a"*32,python="unused",bridge="unused",prompt="probe")))
    driver=Path(__file__).resolve().parents[1]/"tools/zcode_session_driver.mjs"
    result=subprocess.run([node,str(driver),str(spec)],capture_output=True,timeout=15)
    assert (tmp_path/"actor.json").exists(), result.stderr.decode(errors="replace")
    report=json.loads((tmp_path/"actor.json").read_text())
    assert result.returncode==1
    preferences=json.loads(Path(str(decision)+".preferences").read_text())
    assert preferences["memoryEnabled"] is False and preferences["subagentRuntimeConfigEnabled"] is False
    assert preferences["toolSearchMode"]=="off"
    if fault=="wrong_model":assert report["error"]=="selected_model_mismatch" and not decision.exists()
    else:
        assert report["error"]=="unexpected_permission_tool"
        assert json.loads(decision.read_text())["decision"]=="deny"
