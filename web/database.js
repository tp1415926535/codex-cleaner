'use strict';
(()=>{
 let report=null,plan=null,observed=false,starting=false,reportHome='',inspecting=false;
 const dialog=$('databaseWorkspace');
 const description={'thread_history_1.sqlite':'db_history','logs_2.sqlite':'db_logs','state_5.sqlite':'db_state'};
 const errors=createErrorReporter($('dbError'),detail=>msg('db_error',{detail}));
 function invalidate(){plan=null;$('dbPlan').hidden=true;$('dbExecute').hidden=true;$('dbReview').hidden=false;}
 function save(){if(!reportHome)return;try{localStorage.setItem('cleaner.database:'+reportHome,JSON.stringify({names:[...dialog.querySelectorAll('#dbTable input:checked')].map(input=>input.value),days:$('dbLogDays').value}));}catch{}}
 function controls(busy){
  databaseBusy=busy;const unavailable=busy||filesBusy||deleting;
  $('dbClose').disabled=unavailable;$('dbReview').disabled=unavailable||!report;
  $('dbExecute').disabled=unavailable;$('dbLogDays').disabled=unavailable;$('dbStop').hidden=!busy;
  for(const input of dialog.querySelectorAll('input[type=checkbox]'))input.disabled=unavailable||input.dataset.invalid==='true';
  if(state)selection();
 }
 async function inspect(){
  if(!state?.home||inspecting)return;
  inspecting=true;
  const requestedHome=state.home;let saved=null;
  try{saved=JSON.parse(localStorage.getItem('cleaner.database:'+requestedHome)||'null');}catch{}
  $('dbLoading').hidden=false;uiText($('dbLoading'),msg('db_loading'));report=null;controls(false);
  try{
   const next=await api('/api/database-inspect');if(state.home!==requestedHome)return;
   report=next;reportHome=requestedHome;$('dbTable').replaceChildren();
   $('dbLogDays').value=saved?.days||'';
   const table=element('table'),head=element('thead'),tr=element('tr');
   for(const key of ['db_choose','db_database','db_disk','db_free'])tr.append(element('th',msg(key)));
   head.append(tr);table.append(head);const body=element('tbody');
   for(const db of report.databases){
    const row=element('tr'),checkCell=element('td'),check=element('input');check.type='checkbox';check.value=db.name;
    check.dataset.invalid=String(!db.exists||!!db.error);check.disabled=check.dataset.invalid==='true';check.checked=!check.disabled&&(!saved||saved.names.includes(db.name));
    I18N.attribute(check,'aria-label',msg('db_select',{name:db.name}));check.onchange=()=>{invalidate();save();};checkCell.append(check);
    const name=element('td');name.append(content('b',db.name),element('small',msg(description[db.name]),'db-description'));
    row.append(checkCell,name,element('td',db.exists&&!db.error?fmt(db.bytes+db.wal_bytes):msg('db_unavailable')),element('td',db.free_bytes!==undefined?fmt(db.free_bytes):'—'));
    if(db.error)name.append(element('small',db.error,'db-description'));body.append(row);
   }
   table.append(body);$('dbTable').append(table);
   const history=report.databases.find(d=>d.name==='thread_history_1.sqlite');
   $('dbUnmatched').hidden=!history?.unmatched_sessions;
   if(history?.unmatched_sessions)uiText($('dbUnmatched'),msg('db_unmatched',{count:history.unmatched_sessions,records:history.unmatched_records?.thread_items||0}));
   save();
   errors.clear('inspect');errors.clear('plan');errors.clear('start');
  }catch(e){errors.show(e,'inspect');}finally{inspecting=false;$('dbLoading').hidden=true;controls(databaseBusy);}
 }
 window.addEventListener('cleaner-tab-change',event=>{if(event.detail==='database'&&!report&&!databaseBusy)inspect();});
 if(activeTab==='database')inspect();
 $('dbLogDays').onchange=()=>{invalidate();save();};
 $('dbClose').onclick=()=>{if(!databaseBusy){invalidate();inspect();}};
 $('dbReview').onclick=async()=>{
  $('dbReview').disabled=true;
  try{
   const names=[...dialog.querySelectorAll('#dbTable input:checked')].map(input=>input.value);
   const log_days=$('dbLogDays').value===''?null:Number($('dbLogDays').value);
   plan=await api('/api/database-plan',{names,log_days});$('dbPlan').replaceChildren();
   $('dbPlan').append(element('p',msg('db_plan',{count:plan.entries.length,size:fmt(plan.entries.reduce((sum,d)=>sum+d.free_bytes,0))})));
   for(const entry of plan.entries){
    $('dbPlan').append(element('p',msg('db_plan_entry',{name:entry.name,size:fmt(entry.free_bytes)})));
    if(entry.required_temp_bytes!==undefined)$('dbPlan').append(element('p',msg('db_plan_space',{required:fmt(entry.required_temp_bytes),available:fmt(entry.available_bytes)})));
    if(entry.shortfall_bytes)$('dbPlan').append(element('p',msg('db_plan_space_shortfall',{size:fmt(entry.shortfall_bytes)}),'warning'));
   }
   $('dbPlan').append(element('p',log_days===null?msg('db_no_log_delete'):msg('db_log_delete',{count:plan.entries.reduce((sum,d)=>sum+d.logs_to_delete,0),date:new Date(plan.cutoff*1000).toLocaleString(I18N.language==='en'?'en-US':'zh-CN')})));
   $('dbPlan').hidden=false;$('dbExecute').hidden=false;$('dbReview').hidden=true;$('dbPlan').scrollIntoView({block:'nearest'});
   errors.clear('plan');errors.clear('start');
  }catch(e){errors.show(e,'plan');}finally{$('dbReview').disabled=false;}
 };
 $('dbExecute').onclick=async()=>{
  if(!plan||databaseBusy)return;starting=true;controls(true);$('dbProgress').hidden=false;
  uiText($('dbProgressText'),msg('db_starting'));
  try{await api('/api/database-start',{token:plan.token,confirmed:true});errors.clear('start');observed=true;plan=null;}
  catch(e){errors.show(e,'start');controls(false);$('dbProgress').hidden=true;}
  finally{starting=false;}
 };
 $('dbStop').onclick=async()=>{try{$('dbStop').disabled=true;await api('/api/database-stop',{});errors.clear('stop');}catch(e){errors.show(e,'stop');$('dbStop').disabled=false;}};
 function results(p){
  $('dbResults').replaceChildren();$('dbResults').hidden=false;
  $('dbResults').append(element('h3',msg('db_finished',{size:fmt(p.results.reduce((sum,r)=>sum+r.released,0))})));
  for(const r of p.results){const box=element('div',undefined,'db-result');box.append(content('b',r.name),element('p',msg('db_result',{status:I18N.message('db_status_'+r.status),logs:r.deleted_logs,size:fmt(r.released)})));if(r.error)box.append(element('p',msg('db_error',{detail:r.error})));$('dbResults').append(box);}
  $('dbResults').scrollIntoView({block:'nearest'});
 }
 async function progress(){
  try{const p=await api('/api/database-progress');
   if(p.running){
    errors.clear('start');if(p.stopping)errors.clear('stop');
    observed=true;controls(true);
    $('dbProgress').hidden=false;$('dbProgressBar').max=p.total||1;$('dbProgressBar').value=p.done;
    uiText($('dbProgressText'),msg('db_progress',{done:p.done,total:p.total,name:p.database,phase:msg(p.stopping?'db_stopping':'db_phase_'+p.phase)}));
    $('dbStop').disabled=!!p.stopping;
   }else if(observed&&!starting){errors.clear('start');errors.clear('stop');observed=false;controls(false);$('dbProgress').hidden=true;invalidate();results(p);inspect();}
  }catch{}finally{controls(databaseBusy);setTimeout(progress,1000);}
 }
 window.addEventListener('cleaner-state-change',()=>{
  if(reportHome&&reportHome!==state.home){report=null;reportHome='';errors.reset();invalidate();}
  if(activeTab==='database'&&!report&&!databaseBusy)inspect();
 });
 window.addEventListener('pagehide',save);
 progress();
})();
