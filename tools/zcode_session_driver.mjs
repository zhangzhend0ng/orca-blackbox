// ZCode's original app-server owns the agent loop. This client only binds a
// session, supplies its goal, enforces permissions and records native events.
import {spawn} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import readline from 'node:readline';

const spec=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const names=['Snapshot','Screenshot','Click','Type','Shortcut','Wait','ControlStatus'];
const allowed=new Set(names.map(n=>'mcp__windows_mcp__'+n));
const report={actor:'zcode',provider_id:'new-provider',model_id:'glm-5.3-flash',error:null,
 native_tool_calls:[],permissions:[],event_counts:{},stage:'starting'};
const save=(final=false)=>{
 if(final)fs.writeFileSync(path.join(spec.root,'actor.json'),JSON.stringify(report,null,2),{flag:'wx'});
 else fs.appendFileSync(path.join(spec.root,'progress.ndjson'),JSON.stringify(report)+'\n');
};
const server=spawn(process.execPath,[spec.bundle,'app-server','--cwd',spec.workspace,'--no-color'],
 {cwd:spec.workspace,env:process.env,stdio:['pipe','pipe','pipe'],windowsHide:true});
const stderr=fs.openSync(path.join(spec.root,'server.stderr.log'),'wx');
let stderrBytes=0,wireBytes=0,sequence=0;
const pending=new Map();
const write=d=>server.stdin.write(JSON.stringify(d)+'\n');
server.stderr.on('data',data=>{
 stderrBytes+=data.length;
 if(stderrBytes>2000000){report.error='server_stderr_limit';server.kill();return;}
 fs.writeSync(stderr,data);
});
readline.createInterface({input:server.stdout}).on('line',line=>{
 wireBytes+=line.length;
 if(line.length>8000000||wireBytes>128000000){report.error='protocol_output_limit';server.kill();return;}
 let data;try{data=JSON.parse(line)}catch{report.error='protocol_invalid_json';server.kill();return;}
 if(data.id!==undefined && !data.method && pending.has(String(data.id))){
  const p=pending.get(String(data.id));pending.delete(String(data.id));clearTimeout(p.timer);
  data.error?p.reject(new Error('rpc_error:'+p.method+':'+String(data.error.message).slice(0,200))):p.resolve(data.result);
 }else if(data.id!==undefined && data.method){
  if(data.method==='session/requestRuntimePreferences'){
   write({id:data.id,result:{nativeSearchEnhancementsEnabled:false,toolSearchMode:'off',
    subagentRuntimeConfigEnabled:false,memoryEnabled:false,askUserQuestionAutoResolutionEnabled:false}});
  }else if(data.method==='interaction/requestPermission'){
   const tool=data.params?.toolName;const permit=allowed.has(tool);
   report.permissions.push({tool,decision:permit?'allow':'deny'});
   if(!permit)report.error='unexpected_permission_tool';
   write({id:data.id,result:{decision:permit?'allow':'deny',reason:'Fixed guest GUI tool scope'}});
  }else if(data.method==='interaction/requestOfficialMcpAuthHeaders'){
   // Unused user plugins receive no desktop credentials from this client.
   report.denied_plugin_auth=true;
   write({id:data.id,error:{code:-32601,message:'No official-plugin credentials in GUI session'}});
  }else{
   report.error='unexpected_host_request:'+data.method;
   write({id:data.id,error:{code:-32601,message:'Unsupported in isolated GUI session'}});
  }
 }
});
function request(method,params,seconds=60){
 const id=String(++sequence);
 return new Promise((resolve,reject)=>{
  const timer=setTimeout(()=>{pending.delete(id);reject(new Error('rpc_timeout:'+method))},seconds*1000);
  pending.set(id,{resolve,reject,timer,method});write({id,method,params});
 });
}
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const calls=new Map();
const authorityMode=spec.authority_protocol==='native-authority-1';
let authorityConsumed=0;
let needsObservation=false,recoveryCount=0;
const requestIds=new Set();
function takeAuthority(call){
 if(call.authority)return call.authority;
 const raw=fs.existsSync(spec.authority_log)?fs.readFileSync(spec.authority_log,'utf8'):'';
 const lines=raw.split('\n').slice(0,-1);
 if(raw.length>1000000||lines.length<=authorityConsumed)throw new Error('native_authority_receipt_missing');
 const wire=JSON.parse(lines[authorityConsumed]);
 const a=wire.authority;
 const requestKey=JSON.stringify(wire.request_id);
 if(!['string','number'].includes(typeof wire.request_id)||requestIds.has(requestKey))throw new Error('native_authority_request_identity');
 if(a?.protocol!=='native-authority-1'||a.run_id!==spec.run_id||a.seq!==authorityConsumed+1||a.tool!==call.tool
    ||!['completed','recoverable','fatal'].includes(a.decision)||typeof a.dispatched!=='boolean')throw new Error('native_authority_receipt_mismatch');
 authorityConsumed++;
 requestIds.add(requestKey);
 call.authority=a;
 if(a.decision==='fatal')throw new Error('native_authority_fatal:'+a.error_code);
 if(a.decision==='recoverable'){
  const r=a.recovery;
  if(!spec.recovery_enabled||a.dispatched!==false||r?.protocol!=='native-recovery-1'||r.run_id!==spec.run_id
    ||r.seq!==a.seq||r.tool!==call.tool||r.decision!=='recoverable'||r.dispatch_state!=='not_dispatched'
    ||call.tool!=='Type'||a.error_code!=='native_type_requires_owned_edit'||r.error_code!==a.error_code
    ||typeof r.facts_sha256!=='string'||!/^[0-9a-f]{64}$/.test(r.facts_sha256)
    ||r.requires_observation!==true||!Number.isInteger(r.budget_used)||r.budget_used!==recoveryCount+1||r.budget_used>2)
    throw new Error('native_recovery_receipt_invalid');
  recoveryCount++;needsObservation=true;
 }else if(a.dispatched!==true)throw new Error('native_authority_completion_not_dispatched');
 else if(['Snapshot','Screenshot'].includes(call.tool))needsObservation=false;
 else if(needsObservation&&['Click','Type','Shortcut'].includes(call.tool))throw new Error('native_recovery_observation_required');
 return a;
}
let session,finished=false;
try{
 await request('runtime/capabilities',{});
 const snapshot=await request('session/create',{
  workspace:{workspacePath:spec.workspace,workspaceKey:'orca-native-'+spec.run_id},
  model:{providerId:report.provider_id,modelId:report.model_id,options:{reasoningLevel:'low'}},thoughtLevel:'low',
  mode:'guarded',persistence:'deferred',titleGenerationEnabled:false,
  toolAllowlist:[...allowed],dynamicWorkflowEnabled:false,offPeakToolEnabled:false,
  mcpServers:[{name:'windows_mcp',scope:'user',command:spec.python,
   args:['-B',spec.bridge,'--run-id',spec.run_id,'--goal-save',
    ...(spec.scenario&&spec.scenario!=='base'?['--scenario',spec.scenario]:[]),
    ...(authorityMode?['--authority-log',spec.authority_log]:[])],env:[],isolation:'session',protocolVersion:'legacy',alwaysLoad:true,timeoutMs:60000}]
 });
 report.selection=snapshot.settings?.model?.current;
 report.thought_level=snapshot.settings?.thoughtLevel?.current;
 if(report.selection?.providerId!==report.provider_id||report.selection?.modelId!==report.model_id||report.thought_level!=='low')throw new Error('selected_model_mismatch');
 session=snapshot.session?.sessionId;
 if(!session)throw new Error('session_id_missing');
 report.session_id=session;report.stage='ready';save();
 await request('session/send',{sessionId:session,content:spec.prompt});
 let after=0;
 const deadline=Date.now()+540000;
 while(!finished){
  if(Date.now()>deadline)throw new Error('agent_deadline');
  if(report.error)throw new Error(report.error);
  const result=await request('session/events',{sessionId:session,afterSeq:after,limit:200},30);
  for(const event of result.events||[]){
   after=Math.max(after,event.seq||0);
   report.event_counts[event.type]=(report.event_counts[event.type]||0)+1;
   const p=event.payload||{};
   if(event.type==='tool.updated'){
    if(!['scheduled','error','result'].includes(p.kind)){
     report.informational_tool_event_kinds||={};
     report.informational_tool_event_kinds[String(p.kind)]=(report.informational_tool_event_kinds[String(p.kind)]||0)+1;
     continue;
    }
    if(authorityMode&&(typeof p.toolCallId!=='string'||!p.toolCallId))throw new Error('native_tool_call_identity_missing');
    const call=calls.get(p.toolCallId)||{tool_call_id:p.toolCallId,status:'pending'};
    if(authorityMode&&p.kind!=='scheduled'&&!calls.has(p.toolCallId))throw new Error('native_unscheduled_tool_event');
    if(p.kind==='error'){
     if(authorityMode&&call.error_event)throw new Error('native_duplicate_error_event');
     call.status='failed';call.error_event=true;calls.set(p.toolCallId,call);
     if(authorityMode && takeAuthority(call).decision==='recoverable'){
      call.status='recoverable_rejection';continue;
     }
     throw new Error('native_tool_error_event');
    }
    if(p.kind==='scheduled'){
     if(!allowed.has(p.toolName))throw new Error('native_tool_out_of_scope');
     if(authorityMode&&calls.has(p.toolCallId))throw new Error('native_duplicate_tool_call_id');
     if(authorityMode && [...calls.values()].some(c=>c.status==='pending'))throw new Error('native_parallel_tool_calls_rejected');
     call.tool=p.toolName.slice('mcp__windows_mcp__'.length);
     calls.set(p.toolCallId,call);
     if(calls.size>40)throw new Error('native_action_budget');
    }
    if(p.kind==='result'){
     if(authorityMode&&call.result_event)throw new Error('native_duplicate_result_event');
     call.result_event=true;
     const r=p.result||{};
     if(authorityMode){
      const a=takeAuthority(call);
      call.result_keys=Object.keys(r);
      if(a.decision==='recoverable'){
       call.status='recoverable_rejection';continue;
      }
     }
     call.status=(r.isError||r.error||r.success===false||r.status==='error')?'failed':'completed';
     if(call.status!=='completed')throw new Error('native_tool_failed');
    }
   }
   if(event.type==='turn.failed')throw new Error('turn_failed:'+String(p.error?.message||p.turnPhase).slice(0,200));
   if(event.type==='turn.completed'){
    report.result_type=p.resultType;report.response=p.response;report.usage=p.usage;
    if(p.resultType!=='success'||p.toolCallCount!==calls.size)throw new Error('native_turn_not_successful');
    finished=true;
   }
  }
  report.native_tool_calls=[...calls.values()];report.stage=finished?'completed':'running';save();
  if(!finished)await delay(500);
 }
 if(!calls.size||[...calls.values()].some(c=>!['completed','recoverable_rejection'].includes(c.status)))throw new Error('native_calls_incomplete');
 if(authorityMode && authorityConsumed!==calls.size)throw new Error('native_authority_count_mismatch');
 if(authorityMode){
  const raw=fs.readFileSync(spec.authority_log,'utf8');
  if(!raw.endsWith('\n')||raw.split('\n').length-1!==authorityConsumed)throw new Error('native_authority_extra_or_partial_receipt');
  if(needsObservation)throw new Error('native_recovery_unresolved');
 }
 const read=await request('session/read',{sessionId:session,messageLimit:1});
 const selected=read.settings?.model?.current;
 if(selected?.providerId!==report.provider_id||selected?.modelId!==report.model_id)throw new Error('final_model_mismatch');
}catch(e){report.error=String(e.message).slice(0,300)}
finally{
 try{if(session)await request('session/close',{sessionId:session},15)}catch{report.error||='session_close_unconfirmed';}
 report.native_tool_calls=[...calls.values()];save();
 server.stdin.end();
 const exited=await Promise.race([new Promise(resolve=>server.on('exit',()=>resolve(true))),delay(5000).then(()=>false)]);
 if(!exited){report.error||='server_exit_unconfirmed';server.kill();}
 fs.closeSync(stderr);
 save(true);
 process.exitCode=report.error?1:0;
}
