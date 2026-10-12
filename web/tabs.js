'use strict';
let activeTab='sessions';
const tabIds={sessions:'sessionsTab',database:'openDatabases',files:'filesTab'};
function showTab(name){
 if(!Object.hasOwn(tabIds,name))return;
 activeTab=name;
 for(const [key,id] of Object.entries(tabIds)){
  $(key==='database'?'databasePanel':key+'Panel').hidden=key!==name;
  $(id).setAttribute('aria-selected',String(key===name));
  $(id).tabIndex=key===name?0:-1;
 }
 window.dispatchEvent(new CustomEvent('cleaner-tab-change',{detail:name}));
}
for(const [name,id] of Object.entries(tabIds)){
 $(id).onclick=()=>showTab(name);
 $(id).onkeydown=event=>{
  if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
  event.preventDefault();const names=Object.keys(tabIds),index=names.indexOf(name);
  const next=event.key==='Home'?names[0]:event.key==='End'?names[names.length-1]:names[(index+(event.key==='ArrowRight'?1:2))%names.length];
  showTab(next);$(tabIds[next]).focus();
 };
}
showTab('sessions');
