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


def test_transport_schema_rejects_observed_string_coordinates_and_matches_valid_authority():
    from harness.native_save_policy import scoped_tool_schemas, NATIVE_TOOLS, validate_input
    import importlib.util
    if not importlib.util.find_spec("jsonschema"):
        pytest.skip("jsonschema unavailable")
    from jsonschema import validate, ValidationError
    output=r"C:\owned\0001.3mf"
    original=[{"name":n,"inputSchema":{"type":"object","properties":{"loc":{"type":"string"}}}} for n in NATIVE_TOOLS]
    tools={t["name"]:t["inputSchema"] for t in scoped_tool_schemas(original,output)}
    for tool, args in [("Click",{"loc":"[264, 765]"}),("Snapshot",{"use_vision":"true"}),
                       ("Type",{"loc":[264,765],"text":"powershell"})]:
        with pytest.raises(ValidationError):validate(args,tools[tool])
        with pytest.raises(ValueError):validate_input(tool,args,output)
    for tool,args in [("Click",{"loc":[264,765]}),("Type",{"loc":[264,765],"text":"0.24","clear":True}),
                      ("Type",{"loc":[264,765],"text":output}),("Snapshot",{"use_vision":True})]:
        validate(args,tools[tool]);validate_input(tool,args,output)
    assert all(t["inputSchema"]["properties"]["loc"]["type"]=="string" for t in original)


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
@pytest.mark.parametrize("legacy", [False, True])
def test_zcode_proof_requires_exact_vendor_and_completed_safety_receipt(native_evidence, fault, legacy):
    snapshot=native_evidence;snapshot.contract=native_contract("zcode", legacy_zcode=legacy)
    root=snapshot.artifact_dir
    proof=json.loads((root/"proof.json").read_text());proof["contract_sha256"]=contract_digest(snapshot.contract)
    (root/"proof.json").write_text(json.dumps(proof))
    host=json.loads((root/"host_done.json").read_text())
    model_ids=("glm-5.4","glm-5.3-flash")
    host.update(actor="zcode",provider_id="new-provider",model_id=model_ids[legacy],
                guard_checked=True,sources_unchanged=True,toolset_verified=True)
    if fault:
        host[fault]={"model_id":model_ids[not legacy],"provider_id":"wrong"}.get(fault, False)
    (root/"host_done.json").write_text(json.dumps(host))
    assert verify_saved(snapshot).evidence_complete is (fault is None)


@pytest.mark.parametrize("host,protocol", [("other.example","anthropic-messages"),("ai-gateway.s.com","openai-chat-completions")])
def test_provider_metadata_rejects_a_different_company_endpoint(tmp_path, host, protocol):
    p=tmp_path/"provider.json"
    p.write_text(json.dumps({"config":{"providerConfigRules":{"providerRules":[{
        "providerId":"new-provider","providerName":"Snapmaker","config":{
            "api":{"type":protocol,"baseUrl":"http://"+host+"/v1"},
            "access":{"type":"api-key","apiKey":"test-placeholder"},
            "personalModelIds":["glm-5.4"]}}]}}}))
    with pytest.raises(ValueError, match="provider_changed"):provider_metadata(p)


def test_provider_metadata_accepts_existing_company_address_without_exposing_key(tmp_path):
    p=tmp_path/"provider.json"
    p.write_text(json.dumps({"config":{"providerConfigRules":{"providerRules":[{
        "providerId":"new-provider","providerName":"Snapmaker","config":{
            "api":{"type":"anthropic-messages","baseUrl":"http://ai-gateway.s.com/v1"},
            "access":{"type":"api-key","apiKey":"test-placeholder-secret"},
            "personalModelIds":["glm-5.4"]}}]}}}))
    metadata=provider_metadata(p)
    assert metadata["endpoint_scheme"]=="http" and metadata["provider_name"]=="Snapmaker"
    assert "test-placeholder-secret" not in json.dumps(metadata)


@pytest.mark.parametrize("fault", [None,"provider","model","tools"])
def test_native_model_io_requires_actual_vendor_and_exact_gui_toolset(tmp_path, fault):
    from harness.native_save_policy import NATIVE_TOOLS
    root=tmp_path/"storage/cli/rollout";root.mkdir(parents=True)
    data={"request":{"toolNames":["mcp__windows_mcp__"+n for n in NATIVE_TOOLS]},
          "response":{"usage":{}},"model":{"providerId":"new-provider","modelId":"glm-5.4"}}
    if fault=="provider":data["model"]["providerId"]="other"
    if fault=="model":data["model"]["modelId"]="glm-5.3-flash"
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
  if(q.params.mcpServers[0].args.includes('--text-only-snapshot')!==(process.env.ZCODE_TEST_TEXT_ONLY==='1')){
   process.stdout.write(JSON.stringify({id:q.id,error:{code:-32602,message:'Incorrect Snapshot image trial flag'}})+'\n');return;
  }
  if(q.params.mcpServers[0].timeoutMs!==Number(process.env.ZCODE_TEST_MCP_TIMEOUT)){
   process.stdout.write(JSON.stringify({id:q.id,error:{code:-32602,message:'Incorrect MCP timeout'}})+'\n');return;
  }
  if('model' in q.params||'thoughtLevel' in q.params){
   process.stdout.write(JSON.stringify({id:q.id,error:{code:-32602,message:'Create must use registered default preferences'}})+'\n');return;
  }
  process.stdout.write(JSON.stringify({id:'preferences',method:'session/requestRuntimePreferences',params:{}})+'\n');
  const current={providerId:fault==='wrong_model'?'other':'new-provider',modelId:fault==='switch_model'?'older':'glm-5.4'};
  const available=fault==='switch_model'?[{ref:{providerId:'new-provider',modelId:'glm-5.4'},reasoning:{defaultLevel:'enabled',levels:[{value:'enabled'}]}}]:[];
  result={session:{sessionId:'sess_test'},settings:{model:{current,available},thoughtLevel:{current:'enabled'}}};
 }
 if(q.method==='session/setModel'){
  if(q.params.sessionId!=='sess_test'||q.params.persistAsWorkspaceLastUsed!==false||q.params.model?.options?.reasoningLevel!=='enabled'){
   process.stdout.write(JSON.stringify({id:q.id,error:{code:-32602,message:'Session model must use the registered default effort'}})+'\n');return;
  }
  result={settings:{model:{current:q.params.model},thoughtLevel:{current:'enabled'}}};
 }
 if(q.method==='session/send' && fault!=='tool_error'){
  process.stdout.write(JSON.stringify({id:'permission',method:'interaction/requestPermission',params:{toolName:'Bash',input:{command:'DO_NOT_EXECUTE'}}})+'\n');
 }
 if(q.method==='session/events')result={events:fault==='tool_error'?[{seq:1,type:'tool.updated',payload:{kind:'scheduled',toolCallId:'call_test',toolName:'mcp__windows_mcp__Screenshot'}},{seq:2,type:'tool.updated',payload:{kind:'error',toolCallId:'call_test',error:{type:'InputValidationError',message:'unexpected region'}}}]:[]};
 if(q.id==='permission')require('node:fs').writeFileSync(process.env.ZCODE_TEST_DECISION,JSON.stringify(q.result));
 else process.stdout.write(JSON.stringify({id:q.id,result})+'\n');
});
rl.on('close',()=>process.exit(0));
"""


@pytest.mark.parametrize("fault, comparison", [("wrong_model", False), ("permission", False),
                                                ("tool_error", False), ("switch_model", False), ("wrong_model", True)])
def test_protocol_client_stops_model_drift_and_denies_non_gui_permission(tmp_path, monkeypatch, fault, comparison):
    node=shutil.which("node")
    if not node:pytest.skip("Node runtime unavailable")
    server=tmp_path/"fake.cjs";server.write_text(FAKE_SERVER)
    decision=tmp_path/"decision.json"
    monkeypatch.setenv("ZCODE_TEST_FAULT",fault)
    monkeypatch.setenv("ZCODE_TEST_DECISION",str(decision))
    monkeypatch.setenv("ZCODE_TEST_MCP_TIMEOUT", "80000" if comparison else "60000")
    monkeypatch.setenv("ZCODE_TEST_TEXT_ONLY", "1" if comparison else "0")
    spec=tmp_path/"spec.json"
    config = dict(root=str(tmp_path),bundle=str(server),workspace=str(tmp_path),
                  run_id="a"*32,python="unused",bridge="unused",prompt="probe")
    if comparison:
        config.update(scenario="compare_276_quality", authority_protocol="native-authority-1",
                      authority_log=str(tmp_path / "authority.ndjson"), text_only_snapshot=True)
    spec.write_text(json.dumps(config))
    driver=Path(__file__).resolve().parents[1]/"tools/zcode_session_driver.mjs"
    result=subprocess.run([node,str(driver),str(spec)],capture_output=True,timeout=15)
    assert (tmp_path/"actor.json").exists(), result.stderr.decode(errors="replace")
    report=json.loads((tmp_path/"actor.json").read_text())
    assert result.returncode==1
    progress = tmp_path / "progress.ndjson"
    assert [json.loads(line) for line in progress.read_text().splitlines()] == [{"native_tool_calls": []}]
    preferences=json.loads(Path(str(decision)+".preferences").read_text())
    assert preferences["memoryEnabled"] is False and preferences["subagentRuntimeConfigEnabled"] is False
    assert preferences["toolSearchMode"]=="off"
    if fault=="wrong_model":assert report["error"]=="selected_model_mismatch" and not decision.exists()
    elif fault=="tool_error":
        assert report["error"]=="native_tool_error_event"
        assert report["native_tool_calls"][0]["status"]=="failed"
        assert report["native_tool_calls"][0]["error_event"] is True
    else:
        assert report["error"]=="unexpected_permission_tool"
        assert json.loads(decision.read_text())["decision"]=="deny"
