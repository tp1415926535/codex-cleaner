// Every API response is mocked; no user data or cleanup service is used.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await browser.newPage(),pageErrors=[];
  page.on('pageerror',e=>pageErrors.push(e.message));
  const row={id:'fixture-session',title:'错误恢复测试',kind:'main',project:'fixture',cwd:'fixture',size:1024,reclaimable:1024,updated_at:1,issues:[],missing_files:[],file_count:1,activity:{code:'idle'},state:'普通'};
  const file={id:'.sandbox/fixture.log',name:'.sandbox/fixture.log',bytes:1024,files:1,modified:1700000000,allowed:true,recommended:true,reason:'old_log',samples:['.sandbox/fixture.log']};
  const db={name:'logs_2.sqlite',exists:true,bytes:1024,wal_bytes:0,free_bytes:512,
   required_temp_bytes:32*1024*1024,available_bytes:16*1024*1024,shortfall_bytes:16*1024*1024};
  const failures=new Map();let fileRunning=false,dbRunning=false,dbStopping=false,deleteRunning=false;
  const defaults={
   '/api/state':()=>({csrf:'fixture',home:'fixture-home',rows:[row],complete:true,generation:1,status:'扫描完成',source:'fixture',error:'',cli:{available:true,lock_verified:true,message:'已验证',version:'fixture',path:'fixture'},diagnostics:[],diagnostic_count:0}),
   '/api/preview':()=>({messages:[],note:'fixture preview',next:null,files:[]}),
   '/api/plan':()=>({token:'session-plan',allowed:true,bytes:1024,blockers:[],entries:[{...row,files:[],bytes:1024,blockers:[]}]}),
   '/api/delete-progress':()=>({running:deleteRunning,started:Date.now()/1000+1,done:0,total:1,can_stop:true,phase:'fixture'}),
   '/api/files-inspect':()=>({home:'fixture-home',days:7,bytes:1024,entries:[file],directories:[]}),
   '/api/files-plan':()=>({token:'file-plan',entries:[file],bytes:1024,files:1}),
   '/api/files-progress':()=>({running:fileRunning,started:1,done:0,total:1,bytes:0,results:[]}),
   '/api/files-start':()=>{fileRunning=true;return {ok:true};},
   '/api/files-list':()=>({id:file.id,token:'preview-token',total:1,matched:1,offset:0,next:null,items:[{path:file.id,bytes:1024,modified:1700000000,kind:'text'}]}),
   '/api/files-preview':()=>({path:file.id,bytes:1024,modified:1700000000,kind:'text',text:'preview recovered'}),
   '/api/database-inspect':()=>({databases:[db]}),
   '/api/database-plan':()=>({token:'db-plan',entries:[{...db,logs_to_delete:0}]}),
   '/api/database-progress':()=>({running:dbRunning,stopping:dbStopping,phase:'compacting',database:db.name,done:0,total:1,results:[]}),
   '/api/database-start':()=>{dbRunning=true;return {ok:true};},
   '/api/database-stop':()=>{dbStopping=true;return {ok:true};}
  };
  await page.route('**/api/**',route=>{
   const path=new URL(route.request().url()).pathname;
   return route.fulfill(failures.has(path)?{status:400,json:{error:failures.get(path)}}:{json:defaults[path]?.()||{ok:true,running:false}});
  });
  let failLocale=true;
  await page.route('**/locales/en.json',route=>{if(failLocale){failLocale=false;return route.fulfill({status:503,body:'unavailable'});}return route.continue();});
  await page.goto(process.env.CLEANER_URL || 'http://127.0.0.1:18766');
  await page.waitForFunction(()=>document.getElementById('language').disabled);
  await page.evaluate(()=>I18N.ready);
  if(await page.locator('#language').isDisabled()||await page.locator('#language').getAttribute('title'))throw Error('Language loading error did not recover');
  await page.locator('#language').selectOption('zh-CN');await page.locator('.session-row').waitFor();
  async function visible(id,text){await page.waitForFunction(({id,text})=>{const el=document.getElementById(id);return !el.hidden&&el.textContent.includes(text);},{id,text});}
  async function hidden(id){await page.waitForFunction(id=>document.getElementById(id).hidden,id);}
  async function invoke(id){await page.evaluate(id=>document.getElementById(id).onclick(),id);}

  failures.set('/api/preview','预览失败 fixture');await page.evaluate(()=>loadPreview('fixture-session'));
  await visible('error','预览失败 fixture');
  failures.set('/api/scan','扫描失败 fixture');await invoke('rescan');await visible('error','扫描失败 fixture');
  failures.delete('/api/scan');await invoke('rescan');await visible('error','预览失败 fixture');
  failures.delete('/api/preview');await page.evaluate(()=>loadPreview('fixture-session',true));await hidden('error');
  failures.set('/api/preview','清空前的预览错误');await page.evaluate(()=>loadPreview('fixture-session'));
  await invoke('clearPreview');await hidden('error');failures.delete('/api/preview');

  failures.set('/api/scan','删除后刷新失败 fixture');
  await page.evaluate(()=>{completionHandled=false;finishDelete({results:[]});});await visible('error','列表更新失败');
  failures.delete('/api/scan');await invoke('rescan');await hidden('error');
  failures.set('/api/delete-stop','停止会话失败 fixture');await invoke('stopDelete');await visible('error','停止会话失败');
  failures.delete('/api/delete-stop');await invoke('stopDelete');await hidden('error');
  failures.set('/api/delete','删除断线 fixture');failures.set('/api/delete-progress','进度断线 fixture');
  await page.evaluate(()=>{activePlan={token:'fixture-plan',allowed:true};});await invoke('execute');
  await visible('result','连接中断');
  deleteRunning=true;failures.delete('/api/delete-progress');await page.evaluate(()=>pollDeleteProgress());
  if(await page.locator('#result').textContent()!=='')throw Error('Recovered deletion still shows connection-lost message');
  deleteRunning=false;failures.delete('/api/delete');await page.evaluate(()=>pollDeleteProgress());await invoke('closePlan');

  failures.set('/api/settings','设置失败 fixture');await invoke('settings');await invoke('saveSettings');await visible('settingsError','设置失败');
  failures.delete('/api/settings');await invoke('saveSettings');await invoke('settings');await hidden('settingsError');await invoke('closeSettings');

  await page.locator('#filesTab').click();await page.locator('.file-entry').waitFor();
  failures.set('/api/files-list','文件列表失败 fixture');await page.locator('.file-view').click();await visible('fileBrowserError','文件列表失败');
  failures.delete('/api/files-list');await page.locator('#fileBrowserSearch').fill('fixture');await hidden('fileBrowserError');
  failures.set('/api/files-preview','文件预览失败 fixture');await page.locator('.file-browser-item').click();await visible('fileContentError','文件预览失败');
  failures.delete('/api/files-preview');await page.locator('.file-browser-item').click();await hidden('fileContentError');await invoke('fileBrowserClose');
  failures.set('/api/files-inspect','文件检查失败 fixture');await invoke('filesRefresh');await visible('filesError','文件检查失败');
  failures.delete('/api/files-inspect');await invoke('filesRefresh');await hidden('filesError');
  failures.set('/api/files-plan','文件计划失败 fixture');await invoke('filesReview');await visible('filesError','文件计划失败');
  failures.delete('/api/files-plan');await invoke('filesReview');await hidden('filesError');
  failures.set('/api/files-start','文件启动失败 fixture');await invoke('filesExecute');await visible('filesError','文件启动失败');
  // The server may have started despite a failed response; polling is authoritative.
  fileRunning=true;await hidden('filesError');await invoke('filesPlanClose');failures.delete('/api/files-start');
  failures.set('/api/files-stop','文件停止失败 fixture');await invoke('filesStop');await visible('filesError','文件停止失败');
  failures.delete('/api/files-stop');await invoke('filesStop');await hidden('filesError');
  fileRunning=false;await hidden('filesProgress');await invoke('filesPlanClose');

  await page.locator('#openDatabases').click();await page.locator('#dbTable input').waitFor();
  failures.set('/api/database-inspect','数据库检查失败 fixture');await invoke('dbClose');await visible('dbError','数据库检查失败');
  failures.delete('/api/database-inspect');await invoke('dbClose');await hidden('dbError');
  failures.set('/api/database-plan','数据库计划失败 fixture');await invoke('dbReview');await visible('dbError','数据库计划失败');
  failures.delete('/api/database-plan');await invoke('dbReview');await hidden('dbError');
  const planText=await page.locator('#dbPlan').innerText();
  if(!planText.includes('临时空间 32.00 MiB')||!planText.includes('还差 16.00 MiB'))throw Error('Plan does not disclose temporary space requirement and shortage');
  await page.evaluate(()=>I18N.setLanguage('en'));
  if(!(await page.locator('#dbPlan').innerText()).includes('Temporary space is short by 16.00 MiB'))throw Error('Temporary space warning is not localized');
  await page.evaluate(()=>I18N.setLanguage('zh-CN'));
  failures.set('/api/database-start','数据库启动失败 fixture');await invoke('dbExecute');await visible('dbError','数据库启动失败');
  dbRunning=true;await hidden('dbError');failures.delete('/api/database-start');
  failures.set('/api/database-stop','数据库停止失败 fixture');await invoke('dbStop');await visible('dbError','数据库停止失败');
  failures.delete('/api/database-stop');await invoke('dbStop');await hidden('dbError');
  dbRunning=false;await hidden('dbProgress');
  if(pageErrors.length)throw Error(pageErrors.join('\n'));
  console.log('PASS: language retry, session preview/scan/refresh/stop/settings/deletion reconnect, file list/preview/inspect/plan/start/stop, database inspect/plan/start/stop recover without stale alerts');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
