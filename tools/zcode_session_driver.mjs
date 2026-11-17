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
const save=()=>{
 const p=path.join(spec.root,'actor.json');
 fs.writeFileSync(p+'.pending',JSON.stringify(report,null,2));fs.renameSync(p+'.pending',p);
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
let session,finished=false;
try{
 await request('runtime/capabilities',{});
 const snapshot=await request('session/create',{
  workspace:{workspacePath:spec.workspace,workspaceKey:'orca-native-'+spec.run_id},
  model:{providerId:report.provider_id,modelId:report.model_id,options:{reasoningLevel:'low'}},thoughtLevel:'low',
  mode:'guarded',persistence:'deferred',titleGenerationEnabled:false,
  toolAllowlist:[...allowed],dynamicWorkflowEnabled:false,offPeakToolEnabled:false,
  mcpServers:[{name:'windows_mcp',scope:'user',command:spec.python,
   args:['-B',spec.bridge,'--run-id',spec.run_id,'--goal-save'],env:[],isolation:'session',protocolVersion:'legacy',alwaysLoad:true,timeoutMs:60000}]
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
    const call=calls.get(p.toolCallId)||{tool_call_id:p.toolCallId,status:'pending'};
    if(p.kind==='scheduled'){
     if(!allowed.has(p.toolName))throw new Error('native_tool_out_of_scope');
     call.tool=p.toolName.slice('mcp__windows_mcp__'.length);
     calls.set(p.toolCallId,call);
     if(calls.size>40)throw new Error('native_action_budget');
    }
    if(p.kind==='result'){
     const r=p.result||{};
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
 if(!calls.size||[...calls.values()].some(c=>c.status!=='completed'))throw new Error('native_calls_incomplete');
 const read=await request('session/read',{sessionId:session,messageLimit:1});
 const selected=read.settings?.model?.current;
 if(selected?.providerId!==report.provider_id||selected?.modelId!==report.model_id)throw new Error('final_model_mismatch');
}catch(e){report.error=String(e.message).slice(0,300)}
finally{
 try{if(session)await request('session/close',{sessionId:session},15)}catch{report.error||='session_close_unconfirmed';}
 report.native_tool_calls=[...calls.values()];save();
 server.stdin.end();
 const exited=await Promise.race([new Promise(resolve=>server.on('exit',()=>resolve(true))),delay(5000).then(()=>false)]);
 if(!exited){report.error||='server_exit_unconfirmed';server.kill();save();}
 fs.closeSync(stderr);
 process.exitCode=report.error?1:0;
}
