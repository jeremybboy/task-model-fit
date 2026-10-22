"use strict";
const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="slide-token"]').content;
let bootstrap, baseline, latest = null, busy = false, activeId = null, timer = null, polling = null, started = 0, history = [], replayTimer = null;
const seconds = value => typeof value === 'number' ? `${value.toFixed(2)} s` : '—';

async function api(path, data) {
  const response = await fetch(path, {method:data === undefined ? 'GET' : 'POST',headers:{'X-Slide-Lab-Token':token,'Content-Type':'application/json'},...(data === undefined ? {} : {body:JSON.stringify(data)})});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'The local app could not complete this request.');
  return result;
}
function alertMessage(message='') { $('alert').textContent=message; $('alert').hidden=!message; }
function setBusy(value) {
  busy=value; document.body.classList.toggle('busy',value);
  for(const id of ['task','model','reset','tools']) $(id).disabled=value;
  $('run').disabled=value; $('cancel').hidden=!value;
}
function showState(which, key) {
  $(which).src=`/files/snapshots/${key}.svg`;
  $(which === 'before' ? 'downloadBefore' : 'downloadAfter').href=`/files/snapshots/${key}.pptx`;
}
function clearResult() {
  latest=null; $('total').textContent='—';$('request').textContent='—';$('outcome').textContent='Not run';
  $('audit').replaceChildren();$('events').replaceChildren();$('details').textContent='No measurements yet.';
  $('afterLabel').textContent='Waiting for a run';$('elapsed').textContent='';
}
function updateModel() {
  const model=$('model').value, config=bootstrap.models[model];
  $('modelDetail').textContent=`${model} · ${config.effort} reasoning · tools held constant`;
}
function renderRun(run, replay=false) {
  $('total').textContent=seconds(run.metrics.total_action_seconds);
  $('request').textContent=seconds(run.metrics.elapsed_request_seconds);
  $('outcome').textContent=run.audit ? (run.audit.passed ? 'Passed' : 'Review needed') : run.status === 'failed' ? 'Failed' : 'Pending';
  $('afterLabel').textContent=replay ? 'Replay · saved run' : run.mode === 'tools' ? 'Tool test · no model' : run.status === 'completed' ? 'Model run complete' : 'Live run';
  $('audit').replaceChildren(...(run.audit?.checks || []).map(check => {
    const element=document.createElement('span');element.textContent=`${check.passed?'✓':'!'} ${check.label}`;element.classList.toggle('failed',!check.passed);return element;
  }));
  $('events').replaceChildren(...run.events.map(event => {const li=document.createElement('li');li.textContent=`${seconds(event.received_seconds)} · ${event.label}`;return li;}));
  $('details').textContent=JSON.stringify({mode:run.mode,model:run.model,effort:run.effort,...run.metrics,audit_scope:run.audit?.scope,preview:run.preview_kind},null,2);
  $('activity').textContent=run.error || run.events.at(-1)?.label || 'Starting…';
  if(run.error) alertMessage(run.error);
  showState('after',run.after);
}
async function refreshConnection() {
  $('checkConnection').disabled=true;
  try {
    const status=await api('/api/connection');
    $('connectionBadge').textContent=status.ready ? 'ChatGPT sign-in detected' : 'Codex needs attention';
    $('connectionDetail').textContent=status.message;
    if(!status.ready) $('setup').open=true;
    return status;
  } catch(error) { $('connectionBadge').textContent='Connection check failed';$('connectionDetail').textContent=error.message; }
  finally { $('checkConnection').disabled=false; }
}
async function refreshHistory() {
  history=await api('/api/runs');
  const matching=history.filter(run=>run.baseline===baseline && run.task===$('task').value);
  $('historyEmpty').hidden=matching.length>0;$('historyTable').hidden=matching.length===0;
  $('historyBody').replaceChildren(...matching.map(run=>{
    const tr=document.createElement('tr');
    const values=[run.mode==='tools'?'Slide tools · no model':`${bootstrap.models[run.model]?.label || run.model} / ${run.effort}`,seconds(run.metrics.total_action_seconds),seconds(run.metrics.elapsed_request_seconds),run.audit ? (run.audit.passed?'Passed':'Review needed') : run.status];
    for(const value of values){const td=document.createElement('td');td.textContent=value;tr.append(td);}
    const td=document.createElement('td'),button=document.createElement('button');button.textContent='Replay';button.className='quiet';button.disabled=busy || run.status==='running';button.addEventListener('click',()=>replay(run));td.append(button);tr.append(td);return tr;
  }));
}
function stopTimers() {clearInterval(timer);clearInterval(polling);clearInterval(replayTimer);timer=polling=replayTimer=null;}
async function run(mode) {
  alertMessage();stopTimers();clearResult();showState('before',baseline);showState('after',baseline);setBusy(true);
  started=performance.now();$('activity').textContent=mode==='live'?'Starting Codex request…':'Testing native slide tools · no model call…';
  timer=setInterval(()=>{$('elapsed').textContent=seconds((performance.now()-started)/1000);},100);
  try {
    const result=await api('/api/run',{mode,task:$('task').value,model:$('model').value,baseline});activeId=result.id;
    const poll=async()=>{
      try {
        const record=await api(`/api/runs/${result.id}`);latest=record;renderRun(record);
        if(record.status!=='running') {stopTimers();activeId=null;setBusy(false);$('elapsed').textContent=seconds(record.metrics.total_action_seconds);await refreshHistory();}
      }catch(error){stopTimers();activeId=null;setBusy(false);alertMessage(error.message);}
    };
    await poll();if(busy)polling=setInterval(poll,350);
  } catch(error) {stopTimers();setBusy(false);$('activity').textContent='The run did not start.';alertMessage(error.message);}
}
async function replay(record) {
  if(busy)return;
  alertMessage();stopTimers();setBusy(true);activeId=null;
  baseline=record.baseline;showState('before',baseline);showState('after',baseline);
  $('afterLabel').textContent='Replay · saved run';$('activity').textContent='Replaying saved event timing · no model call';
  const start=performance.now();const duration=record.metrics.total_action_seconds || 0;
  replayTimer=setInterval(()=>{
    const elapsed=(performance.now()-start)/1000;
    $('elapsed').textContent=`Replay ${seconds(elapsed)}`;
    const visible=record.steps.filter(step=>step.received_seconds<=elapsed);
    showState('after',visible.at(-1)?.state || baseline);
    const events=record.events.filter(event=>event.received_seconds<=elapsed);
    $('activity').textContent=`Replay · ${events.at(-1)?.label || 'Waiting for recorded events'}`;
    if(elapsed>=duration){stopTimers();latest=record;renderRun(record,true);setBusy(false);refreshHistory().catch(error=>alertMessage(error.message));}
  },50);
}
async function init() {
  bootstrap=await api('/api/bootstrap');baseline=bootstrap.original.id;
  for(const [id,task] of Object.entries(bootstrap.tasks)){$('task').add(new Option(task.label,id));}
  for(const [id,model] of Object.entries(bootstrap.models)){$('model').add(new Option(`${model.label} · ${model.effort}`,id));}
  $('model').value='gpt-6.1-sol';updateModel();showState('before',baseline);showState('after',baseline);$('run').disabled=false;
  $('model').addEventListener('change',updateModel);
  $('task').addEventListener('change',()=>{
    if(latest?.status==='completed')baseline=latest.after;
    clearResult();showState('before',baseline);showState('after',baseline);alertMessage();refreshHistory().catch(error=>alertMessage(error.message));
  });
  $('reset').addEventListener('click',()=>{baseline=bootstrap.original.id;clearResult();showState('before',baseline);showState('after',baseline);alertMessage();refreshHistory().catch(error=>alertMessage(error.message));});
  $('run').addEventListener('click',()=>run('live'));$('tools').addEventListener('click',()=>run('tools'));
  $('checkConnection').addEventListener('click',refreshConnection);
  $('cancel').addEventListener('click',async()=>{
    if(activeId){try{await api('/api/cancel',{id:activeId});$('activity').textContent='Stopping…';}catch(error){alertMessage(error.message);}}
    else{stopTimers();setBusy(false);$('activity').textContent='Replay stopped.';}
  });
  await Promise.all([refreshConnection(),refreshHistory()]);
}
init().catch(error=>alertMessage(error.message));
