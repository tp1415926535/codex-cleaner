'use strict';
(()=>{
 let report=null,chosen=new Set(),home='',plan=null,loading=false,observed=false,starting=false,sequence=0,pendingSince=0;
 let browserId='',browserOffset=0,browserNext=null,browserSequence=0,browserTimer,browserReport=null;
 let previewPath='',previewToken='',previewSequence=0,previewData=null,noticeTimer;
 let folderGrouped=true,closedFolders=new Set();
 let activeFolder='',emptyFolder='',navigationScroll=null,folderHeaders=new Map(),folderButtons=new Map();
 function imageUrl(token,path){return '/api/files-image?'+new URLSearchParams({token,path});}
 async function reveal(id,button,path='',token=''){
  button.disabled=true;clearTimeout(noticeTimer);
  try{await api('/api/files-reveal',{id,days:Number($('filesDays').value),path,token,snapshot:report?.snapshot||''});uiText($('filesOpenNotice'),msg('files_folder_opened'));$('filesOpenNotice').classList.remove('error');}
  catch(error){uiText($('filesOpenNotice'),error.message);$('filesOpenNotice').classList.add('error');}
  finally{button.disabled=false;($('fileBrowserDialog').open?$('fileBrowserDialog'):document.body).append($('filesOpenNotice'));$('filesOpenNotice').hidden=false;noticeTimer=setTimeout(()=>$('filesOpenNotice').hidden=true,5000);}
 }
 function clearContent(){
  previewSequence++;previewData=null;previewPath='';previewToken='';
  for(const id of ['fileContentLoading','fileContentError','fileContentImage','fileContentText','fileContentNote','fileContentFolder'])$(id).hidden=true;
  $('filePreviewImage').removeAttribute('src');rawText($('fileContentText'),'');uiText($('fileContentTitle'),msg('files_preview'));uiText($('fileContentMeta'),'');
  uiText($('fileContentEmpty'),msg('files_preview_choose'));$('fileContentEmpty').hidden=false;
 }
 function renderContent(data){
  rawText($('fileContentTitle'),data.path.split('/').pop());
  uiText($('fileContentMeta'),fmt(data.bytes)+' · '+new Date(data.modified*1000).toLocaleDateString(I18N.language==='en'?'en-US':'zh-CN'));
  if(data.kind==='image'){
   $('filePreviewImage').alt=data.path;$('filePreviewImage').src=imageUrl(previewToken,data.path);$('fileContentImage').hidden=false;
  }else if(data.kind==='text'){
   rawText($('fileContentText'),data.text);$('fileContentText').hidden=false;
   if(data.truncated){uiText($('fileContentNote'),msg('files_preview_truncated'));$('fileContentNote').hidden=false;}
  }else{uiText($('fileContentEmpty'),msg(data.reason==='image_limit'?'files_image_limit':'files_preview_unsupported'));$('fileContentEmpty').hidden=false;}
 }
 async function previewFile(item,token){
  clearContent();previewPath=item.path;previewToken=token;const request=previewSequence;
  rawText($('fileContentTitle'),item.path.split('/').pop());$('fileContentEmpty').hidden=true;$('fileContentLoading').hidden=false;$('fileContentFolder').hidden=false;
  for(const row of $('fileBrowserRows').children)row.classList.toggle('active',row.dataset.path===item.path);
  try{const data=await api('/api/files-preview?'+new URLSearchParams({token,path:item.path}));if(request!==previewSequence)return;previewData=data;renderContent(data);}
  catch(error){if(request===previewSequence){uiText($('fileContentError'),error.message);$('fileContentError').hidden=false;}}
  finally{if(request===previewSequence)$('fileContentLoading').hidden=true;}
 }
 $('filePreviewImage').onerror=()=>{uiText($('fileContentError'),msg('files_image_error'));$('fileContentError').hidden=false;$('fileContentImage').hidden=true;};
 $('fileContentImage').onclick=()=>{rawText($('fileImageTitle'),previewPath);$('fileImageLarge').alt=previewPath;$('fileImageLarge').src=imageUrl(previewToken,previewPath);$('fileImageDialog').showModal();};
 $('fileImageClose').onclick=()=>$('fileImageDialog').close();
 $('fileImageDialog').addEventListener('close',()=>$('fileImageLarge').removeAttribute('src'));
 $('fileBrowserFolder').onclick=()=>reveal(browserId,$('fileBrowserFolder'));
 $('fileContentFolder').onclick=()=>reveal(browserId,$('fileContentFolder'),previewPath,previewToken);
 function renderBrowser(data){
  uiText($('fileBrowserCount'),msg('files_browser_count',{start:data.matched?data.offset+1:0,end:Math.min(data.offset+data.items.length,data.matched),count:data.matched,total:data.total}));
  $('fileBrowserRows').replaceChildren();
  for(const item of data.items){
   const row=element('tr');row.dataset.path=item.path;row.classList.toggle('active',item.path===previewPath);
   const cell=element('td'),button=element('button',undefined,'file-browser-item');button.title=item.path;
   const name=item.path.startsWith(browserId+'/')?item.path.slice(browserId.length+1):item.path.split('/').pop();
   if(item.kind==='image'&&data.token&&item.bytes<=16*1024*1024){const thumbnail=element('img');thumbnail.alt='';thumbnail.loading='lazy';thumbnail.decoding='async';thumbnail.src=imageUrl(data.token,item.path);thumbnail.onerror=()=>{thumbnail.hidden=true;};button.append(thumbnail);}
   button.append(content('span',name));button.onclick=()=>{if(data.token)previewFile(item,data.token);};cell.append(button);
   row.append(cell,element('td',fmt(item.bytes),'bytes'),content('td',new Date(item.modified*1000).toLocaleDateString(I18N.language==='en'?'en-US':'zh-CN')));$('fileBrowserRows').append(row);
  }
  $('fileBrowserEmpty').hidden=data.items.length>0;
  $('fileBrowserPrev').disabled=data.offset===0;$('fileBrowserNext').disabled=data.next===null;
 }
 async function browse(offset=0){
  const request=++browserSequence;
  $('fileBrowserLoading').hidden=false;$('fileBrowserError').hidden=true;
  $('fileBrowserPrev').disabled=true;$('fileBrowserNext').disabled=true;
  try{
   const query=new URLSearchParams({id:browserId,days:String(report.days),offset:String(offset),q:$('fileBrowserSearch').value,snapshot:report.snapshot||''});
   const data=await api('/api/files-list?'+query);
   if(request!==browserSequence)return;
   browserOffset=data.offset;browserNext=data.next;browserReport=data;renderBrowser(data);
   if(data.token){
    const selected=data.items.find(item=>item.path===previewPath)||data.items.find(item=>item.kind==='image')||data.items[0],version=previewSequence;
    if(selected)requestAnimationFrame(()=>setTimeout(()=>{if(request===browserSequence&&version===previewSequence&&$('fileBrowserDialog').open)previewFile(selected,data.token);},0));
    else clearContent();
   }
   document.querySelector('.file-browser-scroll').scrollTop=0;
  }catch(error){if(request===browserSequence){uiText($('fileBrowserError'),error.message);$('fileBrowserError').hidden=false;if(!previewToken)$('fileContentLoading').hidden=true;}}
  finally{if(request===browserSequence)$('fileBrowserLoading').hidden=true;}
 }
 function openBrowser(entry){
  browserId=entry.id;browserReport=null;clearContent();$('fileBrowserSearch').value='';
  rawText($('fileBrowserTitle'),entry.name);$('fileBrowserRows').replaceChildren();uiText($('fileBrowserCount'),'');$('fileBrowserEmpty').hidden=true;
  if(entry.files===1){
   const item={path:entry.samples?.[0]||entry.id,bytes:entry.bytes,modified:entry.modified};
   previewPath=item.path;
   browserReport={id:entry.id,total:1,matched:1,offset:0,next:null,items:[item]};renderBrowser(browserReport);
   rawText($('fileContentTitle'),item.path.split('/').pop());uiText($('fileContentMeta'),fmt(item.bytes)+' · '+new Date(item.modified*1000).toLocaleDateString(I18N.language==='en'?'en-US':'zh-CN'));
   $('fileContentEmpty').hidden=true;$('fileContentLoading').hidden=false;
  }
  $('fileBrowserDialog').showModal();browse();
 }
 $('fileBrowserClose').onclick=()=>$('fileBrowserDialog').close();
 $('fileBrowserDialog').addEventListener('close',()=>{browserSequence++;clearTimeout(browserTimer);clearContent();});
 $('fileBrowserSearch').oninput=()=>{browserSequence++;clearTimeout(browserTimer);browserTimer=setTimeout(()=>browse(),200);};
 $('fileBrowserPrev').onclick=()=>browse(Math.max(0,browserOffset-100));
 $('fileBrowserNext').onclick=()=>{if(browserNext!==null)browse(browserNext);};
 function save(){if(!home||report?.complete===false)return;try{localStorage.setItem('cleaner.files:'+home,JSON.stringify({chosen:[...chosen],days:$('filesDays').value,search:$('filesSearch').value,filter:$('filesFilter').value,grouped:folderGrouped,closedFolders:[...closedFolders]}));}catch{}}
 function restore(next){
  if(next===home)return false;home=next;chosen=new Set();folderGrouped=true;closedFolders=new Set();activeFolder='';emptyFolder='';$('filesNavSearch').value='';
  try{const saved=JSON.parse(localStorage.getItem('cleaner.files:'+home)||'null');if(saved){chosen=new Set(saved.chosen||[]);if(typeof saved.grouped==='boolean')folderGrouped=saved.grouped;closedFolders=new Set(saved.closedFolders||[]);for(const [field,id] of [['days','filesDays'],['search','filesSearch'],['filter','filesFilter']])if(typeof saved[field]==='string')$(id).value=saved[field];return true;}}catch{}
  return false;
 }
 function matches(){const query=$('filesSearch').value.toLocaleLowerCase(),filter=$('filesFilter').value;return (report?.entries||[]).filter(entry=>entry.id.toLocaleLowerCase().includes(query)&&(filter==='all'||filter==='recommended'&&entry.recommended||filter==='allowed'&&entry.allowed&&!entry.recommended||filter==='protected'&&!entry.allowed));}
 function controls(){
  const blocked=loading||report?.complete===false||filesBusy||deleting||databaseBusy;
  $('filesReview').disabled=blocked||!chosen.size||!report;
  $('filesRefresh').disabled=loading||filesBusy;$('filesAuto').disabled=blocked||!report;$('filesDays').disabled=filesBusy;
  $('filesSelectAll').disabled=blocked||!report||!matches().some(entry=>entry.allowed);$('filesNavSearch').disabled=!report;
  for(const input of $('filesRows').querySelectorAll('input'))input.disabled=blocked||input.dataset.protected==='true';
  if(state)selection();
 }
 function layout(){
  $('filesNav').hidden=!folderGrouped;document.querySelector('.files-layout').classList.toggle('with-files-nav',folderGrouped);
  $('filesGroup').setAttribute('aria-pressed',String(folderGrouped));$('filesGroup').classList.toggle('active',folderGrouped);
 }
 function loadingState(){
  $('filesLoading').hidden=!loading||!!report?.entries.length;
  if(!loading)uiText($('filesScanText'),'');
  document.querySelector('.files-list').setAttribute('aria-busy',String(loading));
 }
 function folderGroups(entries){
  const groups=new Map();
  for(const entry of entries){const key=entry.id.includes('/')?entry.id.split('/')[0]:'.';if(!groups.has(key))groups.set(key,{key,entries:[],bytes:0,files:0});const group=groups.get(key);group.entries.push(entry);group.bytes+=entry.bytes;group.files+=entry.files;}
  return [...groups.values()].sort((a,b)=>b.bytes-a.bytes||a.key.localeCompare(b.key));
 }
 function setActiveFolder(key){
  activeFolder=key;
  for(const [folder,button] of folderButtons){button.classList.toggle('active',folder===key);if(folder===key)button.setAttribute('aria-current','location');else button.removeAttribute('aria-current');}
 }
 function jumpToFolder(key){
  folderGrouped=true;closedFolders.delete(key);
  const belongs=entry=>(entry.id.includes('/')?entry.id.split('/')[0]:'.')===key;
  if(!matches().some(belongs)){$('filesSearch').value='';$('filesFilter').value='all';}
  emptyFolder=report.entries.some(belongs)?'':key;activeFolder=key;render();
  const header=folderHeaders.get(key),wrapper=document.querySelector('.files-list');if(!header)return;
  wrapper.scrollTop+=header.getBoundingClientRect().top-wrapper.getBoundingClientRect().top-wrapper.querySelector('thead').offsetHeight;
  navigationScroll=wrapper.scrollTop;
  setActiveFolder(key);header.querySelector('.group-toggle').focus({preventScroll:true});
 }
 function renderFolderNav(){
  layout();
  const list=$('filesNavItems');list.replaceChildren();folderButtons=new Map();if(!folderGrouped)return;
  const folders=[...report.directories];
  const roots=report.entries.filter(entry=>!entry.id.includes('/'));
  if(roots.length)folders.push({name:'.',bytes:roots.reduce((sum,entry)=>sum+entry.bytes,0),files:roots.reduce((sum,entry)=>sum+entry.files,0),issues:0});
  // Keep groups navigable even if an older report lacks their inventory row.
  for(const group of folderGroups(report.entries))if(!folders.some(folder=>folder.name===group.key))folders.push({name:group.key,bytes:group.bytes,files:group.files,issues:0});
  folders.sort((a,b)=>b.bytes-a.bytes||a.name.localeCompare(b.name));
  const query=$('filesNavSearch').value.trim().toLocaleLowerCase(),visible=folders.filter(folder=>(folder.name==='.'?I18N.format('files_root'):folder.name).toLocaleLowerCase().includes(query));
  uiText($('filesNavCount'),query?`${visible.length} / ${folders.length}`:String(folders.length));
  for(const folder of visible){
   const button=element('button',undefined,'nav-project');button.dataset.folder=folder.name;
   const name=element('span',undefined,'nav-project-name'),icon=element('span',undefined,'folder-icon');icon.setAttribute('aria-hidden','true');
   name.append(icon,folder.name==='.'?element('span',msg('files_root')):content('span',folder.name));
   const meta=element('span',undefined,'nav-project-meta');meta.append(element('span',folder.pending?msg('files_checking'):msg('files_count',{count:folder.files})),element('span',folder.pending&&!folder.files?'—':fmt(folder.bytes)));
   button.append(name,meta);if(folder.issues)button.append(element('small',msg('files_directory_issues',{count:folder.issues}),'nav-directory-issues'));
   button.onclick=()=>jumpToFolder(folder.name);list.append(button);folderButtons.set(folder.name,button);
  }
  if(!visible.length)list.append(element('p',msg('files_no_directories'),'nav-empty'));setActiveFolder(activeFolder);
 }
 function entryRow(entry,group){
  const row=element('tr',undefined,'file-entry'+(!entry.allowed?' blocked':chosen.has(entry.id)?' selected':'')+(group?' folder-child':''));
  row.dataset.fileId=entry.id;
  const cell=element('td'),check=element('input');check.type='checkbox';check.checked=chosen.has(entry.id);check.dataset.protected=String(!entry.allowed);check.disabled=!entry.allowed;
  I18N.attribute(check,'aria-label',msg('files_select_item',{path:entry.id}));check.onchange=()=>{check.checked?chosen.add(entry.id):chosen.delete(entry.id);plan=null;render();};cell.append(check);
  const path=element('td'),name=group&&group.key!=='.'?entry.name.slice(group.key.length+1):entry.name;
  const label=content('span',name,'file-name');label.title=entry.name;path.append(label);
  const meta=element('div',undefined,'file-meta');meta.append(element('small',msg('files_count',{count:entry.files})));
  const view=element('button',msg(entry.files>1?'files_browse':'files_preview'),'file-view');view.onclick=()=>openBrowser(entry);meta.append(view);
  const folder=element('button',msg('files_open_folder'),'file-open-folder');folder.onclick=()=>reveal(entry.id,folder);meta.append(folder);
  if(entry.files===1&&entry.samples?.[0]&&entry.samples[0]!==entry.id)path.append(content('small',entry.samples[0],'files-path'));
  path.append(meta);
  const advice=element('td');advice.append(element('span',msg(entry.reason==='scanning'?'files_checking':entry.recommended?'files_only_suggested':entry.allowed?'files_manual':'files_protected'),'file-badge'+(!entry.allowed?' protected':'')),element('small',msg('files_reason_'+entry.reason),'files-reason'));
  row.append(cell,path,element('td',fmt(entry.bytes),'bytes'),content('td',new Date(entry.modified*1000).toLocaleDateString(I18N.language==='en'?'en-US':'zh-CN')),advice);
  return row;
 }
 function groupRows(group){
  const row=element('tr',undefined,'project-group file-group');row.dataset.folder=group.key;
  folderHeaders.set(group.key,row);
  const eligible=group.entries.filter(entry=>entry.allowed),count=group.entries.filter(entry=>chosen.has(entry.id)).length,allEligibleSelected=eligible.length>0&&eligible.every(entry=>chosen.has(entry.id));
  const check=element('input');check.type='checkbox';check.className='file-group-select';check.checked=group.entries.length>0&&count===group.entries.length;check.indeterminate=count>0&&count<group.entries.length;check.dataset.protected=String(!eligible.length);check.disabled=!eligible.length;
  I18N.attribute(check,'aria-label',msg('files_select_folder',{path:group.key}));
  check.onchange=()=>{for(const entry of eligible)allEligibleSelected?chosen.delete(entry.id):chosen.add(entry.id);plan=null;render();};
  const selectCell=element('td');selectCell.append(check);row.append(selectCell);
  const heading=element('td');heading.colSpan=4;const bar=element('div',undefined,'group-heading');
  const collapsible=group.entries.length>1,closed=collapsible&&closedFolders.has(group.key);
  const toggle=element(collapsible?'button':'span',undefined,'group-toggle');
  if(!collapsible)toggle.tabIndex=-1;
  const arrow=element('span',undefined,'group-chevron');arrow.setAttribute('aria-hidden','true');toggle.append(arrow);
  if(collapsible){toggle.setAttribute('aria-expanded',String(!closed));toggle.onclick=()=>{closed?closedFolders.delete(group.key):closedFolders.add(group.key);render();};}
  const icon=element('span',undefined,'folder-icon');icon.setAttribute('aria-hidden','true');toggle.append(icon,group.key==='.'?element('span',msg('files_root'),'group-name'):content('span',group.key,'group-name'));
  bar.append(toggle,element('span',msg('files_group_summary',{count:group.entries.length,files:group.files,size:fmt(group.bytes)}),'group-stats'));heading.append(bar);row.append(heading);$('filesRows').append(row);
  if(!closed)for(const entry of group.entries)$('filesRows').append(entryRow(entry,group));
  if(!group.entries.length){const empty=element('tr',undefined,'file-folder-empty'),cell=element('td',msg(report.complete===false?'files_reason_scanning':'files_directory_empty'));cell.colSpan=5;empty.append(cell);$('filesRows').append(empty);}
 }
 function render(){
  layout();
  if(!report){controls();return;}
  const byId=new Map(report.entries.map(entry=>[entry.id,entry]));
  if(report.complete!==false)chosen=new Set([...chosen].filter(id=>byId.get(id)?.allowed));
  const entries=matches(),selectedEntries=report.entries.filter(entry=>chosen.has(entry.id));
  uiText($('filesTotal'),fmt(report.bytes));uiText($('filesSuggested'),fmt(report.entries.filter(entry=>entry.recommended).reduce((sum,entry)=>sum+entry.bytes,0)));
  const size=selectedEntries.reduce((sum,entry)=>sum+entry.bytes,0);
  uiText($('filesSelectedSize'),fmt(size));uiText($('filesSelection'),msg('files_selection',{count:chosen.size,size:fmt(size)}));
  const wrapper=document.querySelector('.files-list'),scrollTop=wrapper.scrollTop;navigationScroll=null;
  uiText($('filesItemCount'),msg('files_item_count',{count:entries.length}));
  $('filesRows').replaceChildren();folderHeaders=new Map();
  if(folderGrouped)for(const group of folderGroups(entries))groupRows(group);
  else for(const entry of entries)$('filesRows').append(entryRow(entry));
  if(report.complete===false&&!entries.length)for(let index=0;index<6;index++){const row=element('tr',undefined,'files-skeleton'),cell=element('td');row.setAttribute('aria-hidden','true');cell.colSpan=5;cell.append(element('div'),element('small'));row.append(cell);$('filesRows').append(row);}
  if(folderGrouped&&emptyFolder&&!folderHeaders.has(emptyFolder))groupRows({key:emptyFolder,entries:[],bytes:0,files:0});
  wrapper.scrollTop=scrollTop;
  $('filesEmpty').hidden=report.complete===false||entries.length>0||folderGrouped&&!!emptyFolder;
  $('filesSelectAll').checked=entries.length>0&&entries.every(entry=>chosen.has(entry.id));$('filesSelectAll').indeterminate=entries.some(entry=>chosen.has(entry.id))&&!$('filesSelectAll').checked;
  renderFolderNav();
  save();controls();
 }
 async function inspect(){
  if(loading||filesBusy||!state?.home)return;
  const restored=restore(state.home),first=!report||report.home!==home;
  layout();
  const requestedDays=Number($('filesDays').value),requestedHome=home,request=++sequence;
  const previous=report?.home===home&&report.complete!==false?report:null;
  let completed=false;
  loading=true;loadingState();$('filesError').hidden=true;controls();plan=null;
  uiText($('filesLoading').querySelector('strong'),msg('files_loading'));
  uiText($('filesScanText'),msg('files_loading'));
  function apply(next){
   if(next.error)throw new Error(next.error);
   if(request!==sequence||next.home!==requestedHome)return;
   if(next.scan){const message=msg(next.scan.path?'files_scan_progress':'files_scan_start',{path:next.scan.path,count:next.scan.files});uiText($('filesScanText'),message);I18N.attribute($('filesScanText'),'title',message);}
   if(next.complete===false){if(!previous){report=next;render();}loadingState();return;}
   completed=true;report=next;if(first&&!restored)chosen=new Set(report.entries.filter(entry=>entry.recommended).map(entry=>entry.id));render();
  }
  try{
   const response=await fetch('/api/files-inspect?days='+requestedDays+'&stream=1');
   if(!response.ok){const error=await response.json();throw new Error(error.error||response.statusText);}
   if(response.headers.get('Content-Type')?.includes('application/x-ndjson')){
    const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='';
    try{while(true){const {value,done}=await reader.read();buffer+=decoder.decode(value,{stream:!done});let newline;while((newline=buffer.indexOf('\n'))>=0){const line=buffer.slice(0,newline);buffer=buffer.slice(newline+1);if(line.trim())apply(JSON.parse(line));}if(done)break;}if(buffer.trim())apply(JSON.parse(buffer));}
    catch(error){await reader.cancel().catch(()=>{});throw error;}
    finally{reader.releaseLock();}
   }else apply(await response.json());
   if(!completed)throw new Error(I18N.format('files_scan_interrupted'));
  }catch(error){uiText($('filesError'),error.message);$('filesError').hidden=false;}
  finally{loading=false;loadingState();controls();}
 }
 $('filesRefresh').onclick=inspect;
 $('filesGroup').onclick=()=>{folderGrouped=!folderGrouped;render();};
 $('filesAuto').onclick=()=>{chosen=new Set(report.entries.filter(entry=>entry.recommended).map(entry=>entry.id));plan=null;render();};
 $('filesDays').onchange=()=>{save();inspect();};
 $('filesSearch').oninput=$('filesFilter').onchange=()=>{emptyFolder='';render();};
 $('filesNavSearch').oninput=()=>{if(report)renderFolderNav();};
 document.querySelector('.files-list').addEventListener('scroll',()=>{
  if(!folderGrouped||!folderHeaders.size)return;
  const wrapper=document.querySelector('.files-list');
  // At the end of the list, a short target cannot reach the top. Keep the
  // clicked directory current until the user scrolls to another position.
  if(navigationScroll===wrapper.scrollTop)return;navigationScroll=null;
  const top=wrapper.getBoundingClientRect().top+wrapper.querySelector('thead').offsetHeight+2;
  let key=folderHeaders.keys().next().value;
  for(const [folder,header] of folderHeaders){if(header.getBoundingClientRect().top>top)break;key=folder;}
  setActiveFolder(key);
 });
 $('filesSelectAll').onchange=()=>{const eligible=matches().filter(entry=>entry.allowed),allSelected=eligible.length>0&&eligible.every(entry=>chosen.has(entry.id));for(const entry of eligible)allSelected?chosen.delete(entry.id):chosen.add(entry.id);plan=null;render();};
 $('filesReview').onclick=async()=>{
  $('filesReview').disabled=true;$('filesError').hidden=true;
  try{
   plan=await api('/api/files-plan',{ids:[...chosen],days:Number($('filesDays').value)});
   uiText($('filesPlanSummary'),msg('files_plan_summary',{count:plan.entries.length,files:plan.files,size:fmt(plan.bytes)}));
   $('filesPlanList').replaceChildren(...plan.entries.map(entry=>content('p',entry.name+' · '+fmt(entry.bytes))));
   $('filesExecute').disabled=false;$('filesPlanDialog').showModal();
  }catch(error){uiText($('filesError'),error.message);$('filesError').hidden=false;}
  finally{controls();}
 };
 $('filesPlanClose').onclick=()=>$('filesPlanDialog').close();
 $('filesExecute').onclick=async()=>{
  if(!plan||filesBusy)return;starting=true;filesBusy=true;pendingSince=Date.now()/1000;controls();$('filesExecute').disabled=true;
  $('filesError').hidden=true;$('filesResult').hidden=true;
  try{await api('/api/files-start',{token:plan.token,confirmed:true});observed=true;plan=null;$('filesPlanDialog').close();}
  catch(error){filesBusy=false;uiText($('filesError'),error.message);$('filesError').hidden=false;}
  finally{starting=false;$('filesExecute').disabled=false;controls();}
 };
 $('filesStop').onclick=async()=>{try{$('filesStop').disabled=true;await api('/api/files-stop',{});}catch(error){uiText($('filesError'),error.message);$('filesError').hidden=false;$('filesStop').disabled=false;}};
 function finish(progress){
  $('filesResult').replaceChildren();$('filesResult').hidden=false;
  const failed=(progress.results||[]).filter(result=>result.status==='failed');
  uiText($('filesResult'),msg(progress.error?'files_failed':progress.stopped?'files_stopped':'files_finished',{count:progress.done||0,size:fmt(progress.bytes),failed:failed.length}));
  if(progress.error)$('filesResult').append(element('p',progress.error));
  if(failed.length){const details=element('details');details.append(element('summary',msg('files_failures')));for(const result of failed)details.append(content('p',result.path+'\n'+result.error));$('filesResult').append(details);}
 }
 async function progress(){
  try{const next=await api('/api/files-progress');
   if(next.running){observed=true;filesBusy=true;$('filesProgress').hidden=false;$('filesProgressBar').max=next.total||1;$('filesProgressBar').value=next.done;uiText($('filesProgressText'),msg('files_progress',{done:next.done,total:next.total,size:fmt(next.bytes)}));controls();}
   else if(!next.running&&!starting&&(observed||pendingSince&&next.started>=pendingSince)){observed=false;pendingSince=0;filesBusy=false;$('filesProgress').hidden=true;$('filesStop').disabled=false;finish(next);await inspect();controls();}
  }catch{}finally{setTimeout(progress,1000);}
 }
 window.addEventListener('cleaner-tab-change',event=>{if(event.detail==='files'&&(!report||report.home!==state?.home))inspect();});
 window.addEventListener('cleaner-state-change',()=>{if(activeTab==='files'&&(!report||report.home!==state?.home)&&!loading&&!filesBusy)inspect();});
 window.addEventListener('cleaner-language-change',()=>{render();if(browserReport)renderBrowser(browserReport);if(previewData)renderContent(previewData);});
 // State can arrive after the user switches to Files.
 setInterval(()=>{if(activeTab==='files'&&state?.home&&(!report||report.home!==state.home)&&!loading&&!filesBusy)inspect();controls();},1500);
 layout();controls();if(activeTab==='files'&&state?.home)inspect();progress();window.addEventListener('pagehide',save);
})();
