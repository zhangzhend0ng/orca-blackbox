// ZCode's original app-server owns the agent loop. This client only binds a
// session, supplies its goal, enforces permissions and records native events.
import {spawn} from 'node:child_process';
import {createHash} from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import readline from 'node:readline';

const spec=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const names=spec.tools??['Snapshot','Screenshot','Click','Type','Shortcut','Wait','ControlStatus'];
const allowed=new Set(names.map(n=>'mcp__windows_mcp__'+n));
const authorityMode=spec.authority_protocol==='native-authority-1';
const serialScheduler=authorityMode&&typeof spec.scenario==='string'&&(spec.scenario.startsWith('uia_')||spec.scenario.startsWith('compare_'));
const report={actor:'zcode',provider_id:'new-provider',model_id:'glm-5.4',error:null,
 native_tool_calls:[],permissions:[],event_counts:{},stage:'starting'};
let lastProgress;
function saveProgress(){
 const completed=report.native_tool_calls.filter(call=>call.status==='completed')
  .map(({tool,status})=>({tool,status}));
 const snapshot=JSON.stringify({native_tool_calls:completed});
 if(snapshot===lastProgress)return;
 fs.appendFileSync(path.join(spec.root,'progress.ndjson'),snapshot+'\n');
 lastProgress=snapshot;
}
const server=spawn(process.execPath,[spec.bundle,'app-server','--cwd',spec.workspace,'--no-color'],
 {cwd:spec.workspace,env:serialScheduler?{...process.env,ZCODE_MAX_TOOL_CONCURRENCY:'1'}:process.env,
  stdio:['pipe','pipe','pipe'],windowsHide:true});
const stderr=fs.openSync(path.join(spec.root,'server.stderr.log'),'wx');
let stderrBytes=0,wireBytes=0,sequence=0;
const pending=new Map();
const requestCounts=new Map();
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
  }else if(data.method==='session/readReplyLanguage'){
   // Newer app-server builds ask the client for the reply language before a
   // main turn; the server treats a rejected request as "skip" but any
   // unknown request poisons this driver's report. Answer with the language
   // the frozen prompts are written in.
   write({id:data.id,result:{language:'en'}});
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
 requestCounts.set(method,(requestCounts.get(method)||0)+1);
 return new Promise((resolve,reject)=>{
  const timer=setTimeout(()=>{pending.delete(id);reject(new Error('rpc_timeout:'+method))},seconds*1000);
  pending.set(id,{resolve,reject,timer,method});write({id,method,params});
 });
}
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const calls=new Map();
const diagnosticMode=['recovery_diagnostic_once','recovery_diagnostic_commit'].includes(spec.scenario);
const uiaRefreshMode=serialScheduler&&spec.uia_refresh_enabled===true;
let authorityConsumed=0;
let needsObservation=false,recoveryCount=0;
const requestIds=new Set();
const inputTools=new Set(['Click','Type','Shortcut']);
const observationTools=new Set(['Snapshot','Screenshot']);
let serialBatch;

// ZCode announces a complete native schedule before starting its first group.
// Check the groups and lifecycle, not how many calls have been announced.
function registerSerialCall(payload, call){
 const order=payload.schedule?.executionOrder;
 const groups=payload.schedule?.parallelGroups;
 if(!Array.isArray(order)||order.length<1||order.length>40
   ||order.some(id=>typeof id!=='string'||!id)||new Set(order).size!==order.length
   ||!Array.isArray(groups)||groups.length!==order.length
   ||groups.some((group,i)=>!Array.isArray(group)||group.length!==1||group[0]!==order[i]))
  throw new Error('native_serial_schedule_invalid');
 if(!serialBatch){
  if(order.some(id=>calls.has(id)))throw new Error('native_serial_schedule_reused_call');
  serialBatch={order,announced:new Set(),next:0};
 }
 const index=order.indexOf(call.tool_call_id);
 if(index<0||order.length!==serialBatch.order.length||order.some((id,i)=>id!==serialBatch.order[i])
   ||serialBatch.next!==0||(payload.parallelGroupIndex!==undefined&&payload.parallelGroupIndex!==index))
  throw new Error('native_serial_schedule_identity');
 serialBatch.announced.add(call.tool_call_id);
}
function startSerialCall(call, payload){
 if(!serialBatch||serialBatch.announced.size!==serialBatch.order.length
   ||call.started_event||call.status!=='pending'||serialBatch.order[serialBatch.next]!==call.tool_call_id
   ||(payload.toolName!==undefined&&payload.toolName!=='mcp__windows_mcp__'+call.tool))
  throw new Error('native_serial_start_out_of_order');
 call.started_event=true;
 if(needsObservation&&inputTools.has(call.tool))throw new Error('native_recovery_observation_required');
}
function finishSerialCall(call){
 if(!serialBatch||!call.started_event||serialBatch.order[serialBatch.next]!==call.tool_call_id)
  throw new Error('native_serial_result_out_of_order');
 serialBatch.next++;
 if(serialBatch.next===serialBatch.order.length)serialBatch=undefined;
}
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
  const protocol=diagnosticMode?'native-diagnostic-recovery-1':'native-recovery-1';
  const error=diagnosticMode?'native_diagnostic_injected_pre_dispatch':
   uiaRefreshMode?'native_uia_refresh_required':'native_type_requires_owned_edit';
  const allowedRecovery=diagnosticMode||uiaRefreshMode||spec.recovery_enabled;
  const canRecover=uiaRefreshMode?['Click','Type'].includes(call.tool):call.tool==='Type';
  if(!allowedRecovery||!canRecover||a.dispatched!==false||r?.protocol!==protocol||r.run_id!==spec.run_id
    ||r.seq!==a.seq||r.tool!==call.tool||r.decision!=='recoverable'||r.dispatch_state!=='not_dispatched'
    ||a.error_code!==error||r.error_code!==a.error_code
    ||typeof r.facts_sha256!=='string'||!/^[0-9a-f]{64}$/.test(r.facts_sha256)
    ||r.requires_observation!==true||!Number.isInteger(r.budget_used)||r.budget_used!==recoveryCount+1
    ||r.budget_used>(diagnosticMode?1:2))
    throw new Error('native_recovery_receipt_invalid');
  recoveryCount++;needsObservation=true;
 }else if(a.dispatched!==true)throw new Error('native_authority_completion_not_dispatched');
 else if(observationTools.has(call.tool))needsObservation=false;
 else if(needsObservation&&inputTools.has(call.tool))throw new Error('native_recovery_observation_required');
 return a;
}
let session,finished=false;
try{
 if(diagnosticMode&&!authorityMode)throw new Error('native_diagnostic_authority_required');
 await request('runtime/capabilities',{});
 let snapshot=await request('session/create',{
  workspace:{workspacePath:spec.workspace,workspaceKey:'orca-native-'+spec.run_id},
  // ZCode retains GLM-5.4's registered reasoning settings on its default-session path.
  mode:'guarded',persistence:'deferred',titleGenerationEnabled:false,
  toolAllowlist:[...allowed],dynamicWorkflowEnabled:false,offPeakToolEnabled:false,
  mcpServers:[{name:'windows_mcp',scope:'user',command:spec.python,
   args:['-B',spec.bridge,'--run-id',spec.run_id,'--goal-save',
    ...(spec.scenario&&spec.scenario!=='base'?['--scenario',spec.scenario]:[]),
    ...(authorityMode?['--authority-log',spec.authority_log]:[])],env:[],isolation:'session',protocolVersion:'legacy',alwaysLoad:true,timeoutMs:60000}]
 });
 session=snapshot.session?.sessionId;
 if(!session)throw new Error('session_id_missing');
 const matchesModel=ref=>ref?.providerId===report.provider_id&&ref?.modelId===report.model_id;
 if(!matchesModel(snapshot.settings?.model?.current)){
  const registered=snapshot.settings?.model?.available?.find(model=>matchesModel(model.ref));
  const reasoningLevel=registered?.reasoning?.defaultLevel;
  if(!reasoningLevel||!registered.reasoning.levels?.some(level=>level.value===reasoningLevel))
   throw new Error('selected_model_mismatch');
  snapshot=await request('session/setModel',{sessionId:session,persistAsWorkspaceLastUsed:false,
   model:{providerId:report.provider_id,modelId:report.model_id,options:{reasoningLevel}}});
  if(snapshot.settings?.model?.current?.options?.reasoningLevel!==reasoningLevel)
   throw new Error('selected_reasoning_mismatch');
 }
 report.selection=snapshot.settings?.model?.current;
 report.thought_level=snapshot.settings?.thoughtLevel?.current;
 if(!matchesModel(report.selection))throw new Error('selected_model_mismatch');
 report.session_id=session;report.stage='ready';saveProgress();
 // Newer app-server builds start the turn immediately and snapshot the tool
 // registry as-is: run 6165a41c went out with toolNames=[] because the
 // windows_mcp ferry (stdio -> relay -> guest HTTP) had not finished its
 // initialize/initialized/tools/list round trips yet, and the model narrated
 // a fake completion without a single tool. Hold the single turn until the
 // MCP connections have had time to register their tools. The wait is not
 // contract time: the guest's 900 s budget starts at its own ready receipt.
 const readyWaitMs=Math.min(Math.max(Number(spec.mcp_ready_wait_s??0),0),60)*1000;
 await delay(readyWaitMs);
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
    if(!['scheduled','error','result'].includes(p.kind)&&!(serialScheduler&&p.kind==='started')){
     report.informational_tool_event_kinds||={};
     report.informational_tool_event_kinds[String(p.kind)]=(report.informational_tool_event_kinds[String(p.kind)]||0)+1;
     continue;
    }
    if(diagnosticMode&&(report.event_counts['turn.started']!==1||finished))
     throw new Error('native_diagnostic_tool_outside_turn');
    if(authorityMode&&(typeof p.toolCallId!=='string'||!p.toolCallId))throw new Error('native_tool_call_identity_missing');
    const call=calls.get(p.toolCallId)||{tool_call_id:p.toolCallId,status:'pending'};
    if(authorityMode&&p.kind!=='scheduled'&&!calls.has(p.toolCallId))throw new Error('native_unscheduled_tool_event');
    if(serialScheduler&&p.kind==='started')startSerialCall(call,p);
    if(p.kind==='error'){
     if(authorityMode&&call.error_event)throw new Error('native_duplicate_error_event');
     call.status='failed';call.error_event=true;calls.set(p.toolCallId,call);
     if(authorityMode && takeAuthority(call).decision==='recoverable'){
      if(serialScheduler)finishSerialCall(call);
      call.status='recoverable_rejection';continue;
     }
     throw new Error('native_tool_error_event');
    }
    if(p.kind==='scheduled'){
     if(!allowed.has(p.toolName))throw new Error('native_tool_out_of_scope');
     if(authorityMode&&calls.has(p.toolCallId))throw new Error('native_duplicate_tool_call_id');
     call.tool=p.toolName.slice('mcp__windows_mcp__'.length);
     if(serialScheduler)registerSerialCall(p,call);
     else if(authorityMode && [...calls.values()].some(c=>c.status==='pending'))throw new Error('native_parallel_tool_calls_rejected');
     calls.set(p.toolCallId,call);
     if(calls.size>40)throw new Error('native_action_budget');
    }
    if(p.kind==='result'){
     if(authorityMode&&call.result_event)throw new Error('native_duplicate_result_event');
     if(serialScheduler&&!call.authority)finishSerialCall(call);
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
  report.native_tool_calls=[...calls.values()];report.stage=finished?'completed':'running';saveProgress();
  if(!finished)await delay(500);
 }
 if(!calls.size||[...calls.values()].some(c=>!['completed','recoverable_rejection'].includes(c.status)))throw new Error('native_calls_incomplete');
 if(serialScheduler&&serialBatch)throw new Error('native_serial_schedule_incomplete');
 if(authorityMode && authorityConsumed!==calls.size)throw new Error('native_authority_count_mismatch');
 if(authorityMode){
  const raw=fs.readFileSync(spec.authority_log,'utf8');
  if(!raw.endsWith('\n')||raw.split('\n').length-1!==authorityConsumed)throw new Error('native_authority_extra_or_partial_receipt');
  if(needsObservation)throw new Error('native_recovery_unresolved');
 }
 const read=await request('session/read',{sessionId:session,messageLimit:1});
 const selected=read.settings?.model?.current;
 if(selected?.providerId!==report.provider_id||selected?.modelId!==report.model_id)throw new Error('final_model_mismatch');
 if(diagnosticMode){
  const turn={
   run_id:spec.run_id,session_identity_sha256:createHash('sha256').update(session).digest('hex'),
   session_create_count:requestCounts.get('session/create'),
   session_send_count:requestCounts.get('session/send'),
   turn_started_count:report.event_counts['turn.started']||0,
   turn_completed_count:report.event_counts['turn.completed']||0,
   turn_failed_count:report.event_counts['turn.failed']||0,
  };
  if(recoveryCount!==1||turn.session_create_count!==1||turn.session_send_count!==1
     ||turn.turn_started_count!==1||turn.turn_completed_count!==1||turn.turn_failed_count!==0)
   throw new Error('native_diagnostic_single_turn_or_refusal_missing');
  report.diagnostic_turn={...turn,calls:[...calls.values()].map(({authority:a})=>({
   seq:a.seq,tool:a.tool,decision:a.decision,dispatched:a.dispatched,
   facts_sha256:a.recovery?.facts_sha256||null,
  }))};
 }
}catch(e){report.error=String(e.message).slice(0,300)}
finally{
 try{if(session)await request('session/close',{sessionId:session},15)}catch{report.error||='session_close_unconfirmed';}
 report.native_tool_calls=[...calls.values()];
 server.stdin.end();
 const exited=await Promise.race([new Promise(resolve=>server.on('exit',()=>resolve(true))),delay(5000).then(()=>false)]);
 if(!exited){report.error||='server_exit_unconfirmed';server.kill();}
 fs.closeSync(stderr);
 try{saveProgress()}catch{report.error||='native_progress_write_failed';}
 fs.writeFileSync(path.join(spec.root,'actor.json'),JSON.stringify(report,null,2),{flag:'wx'});
 process.exitCode=report.error?1:0;
}
