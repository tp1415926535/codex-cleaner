// All data and deletion endpoints are mocked. No user files are changed.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  const session={id:'fixture-session',title:'保留我的会话选择',kind:'main',project:'测试项目',cwd:'fixture',size:1024,reclaimable:1024,updated_at:1,issues:[],file_count:1,missing_files:[],activity:{code:'idle'},state:'普通'};
  const entries=[
   {id:'.sandbox/sandbox.2026-01-01.log',name:'.sandbox/sandbox.2026-01-01.log',category:'.sandbox',bytes:4096000,files:1,modified:1700000000,allowed:true,recommended:true,reason:'old_log',samples:['.sandbox/sandbox.2026-01-01.log']},
   {id:'visualizations/2026/08/01/fixture-artifact',name:'visualizations/2026/08/01/fixture-artifact',category:'visualizations',bytes:2048000,files:3,modified:1700000000,allowed:true,recommended:false,reason:'artifact',samples:['visualizations/2026/08/01/fixture-artifact/index.html']},
   {id:'.tmp/bundled-marketplaces/openai-bundled',name:'.tmp/bundled-marketplaces/openai-bundled',category:'.tmp',bytes:8192000,files:10,modified:1700000000,allowed:false,recommended:false,reason:'referenced',samples:['.tmp/bundled-marketplaces/openai-bundled/plugin/SKILL.md']},
   {id:'.sandbox/sandbox.2026-10-12.log',name:'.sandbox/sandbox.2026-10-12.log',category:'.sandbox',bytes:1024,files:1,modified:Date.now()/1000,allowed:false,recommended:false,reason:'recent',samples:['.sandbox/sandbox.2026-10-12.log']}
  ];
  const databases=['thread_history_1.sqlite','logs_2.sqlite','state_5.sqlite'];
  let running=false,stopped=false,deleted=false,submission=null,planned=null,complete=true;
  await page.route('**/api/state',route=>route.fulfill({json:{csrf:'test',rows:complete?[session]:[],home:'fixture-home',complete,generation:1,status:complete?'扫描完成':'扫描中',source:'fixture',error:'',cli:{available:true,lock_verified:true,message:'删除能力与会话锁检测已验证',path:'fixture',version:'fixture'},diagnostics:[],diagnostic_count:0}}));
  await page.route('**/api/delete-progress',route=>route.fulfill({json:{running:false}}));
  await page.route('**/api/database-progress',route=>route.fulfill({json:{running:false}}));
  await page.route('**/api/database-inspect',route=>route.fulfill({json:{databases:databases.map(name=>({name,exists:true,bytes:4096000,wal_bytes:0,free_bytes:1024000}))}}));
  await page.route('**/api/files-inspect?*',route=>route.fulfill({json:{home:'fixture-home',days:7,bytes:14337024,entries:deleted?entries.slice(1):entries,directories:[{name:'.sandbox',bytes:4097024,files:2,issues:0},{name:'.tmp',bytes:8192000,files:10,issues:0},{name:'visualizations',bytes:2048000,files:3,issues:0},{name:'skills',bytes:20000,files:4,issues:0}]}}));
  await page.route('**/api/files-plan',route=>{planned=route.request().postDataJSON();return route.fulfill({json:{token:'fixture-plan',entries:[entries[0]],files:1,bytes:entries[0].bytes}});});
  await page.route('**/api/files-start',route=>{submission=route.request().postDataJSON();running=true;return route.fulfill({json:{ok:true}});});
  await page.route('**/api/files-stop',route=>{stopped=true;running=false;deleted=true;return route.fulfill({json:{ok:true}});});
  await page.route('**/api/files-progress',route=>route.fulfill({json:{running,done:stopped?1:0,total:2,bytes:stopped?4096000:0,stopped,error:'',results:stopped?[{path:entries[0].id,status:'success',bytes:4096000}]:[]}}));
  await page.goto(process.env.CLEANER_URL || 'http://127.0.0.1:8766');await page.evaluate(()=>I18N.ready);
  await page.locator('#language').selectOption('zh-CN');
  await page.locator('.session-row input').check();await page.locator('#search').fill(session.title);
  await page.locator('#filesTab').click();await page.locator('#filesRows .file-entry').nth(3).waitFor();await page.locator('#filesGroup').click();
  const checks=page.locator('#filesRows .file-entry input');
  if(!await checks.nth(0).isChecked()||await checks.nth(1).isChecked())throw Error('Initial recommendation selection');
  if(!await checks.nth(2).isDisabled()||!await checks.nth(3).isDisabled())throw Error('Protected items enabled');
  await checks.nth(1).check();
  await page.locator('#openDatabases').click();await page.locator('#dbTable input').first().uncheck();await page.locator('#dbLogDays').selectOption('30');
  await page.locator('#sessionsTab').click();
  if(!await page.locator('.session-row input').isChecked()||await page.locator('#search').inputValue()!==session.title)throw Error('Session choices lost across tabs');
  await page.locator('#filesTab').click();
  if(!await checks.nth(1).isChecked())throw Error('File choice lost across tabs');
  complete=false;await page.reload();await page.evaluate(()=>I18N.ready);if(await page.locator('#sessionsTab').getAttribute('aria-selected')!=='true')throw Error('Reload must start in Sessions');await page.locator('#filesTab').click();await checks.nth(1).waitFor();
  if(!await page.evaluate(()=>selected.has('fixture-session')))throw Error('Partial scan discarded saved session selection');
  complete=true;await page.evaluate(()=>poll());
  if(!await checks.nth(0).isChecked()||!await checks.nth(1).isChecked())throw Error('File choices lost on reload');
  if(await page.locator('#filesTab').getAttribute('aria-selected')!=='true')throw Error('Cannot switch to Files after reload');
  await page.locator('#openDatabases').click();await page.locator('#dbTable input').first().waitFor();
  if(await page.locator('#dbTable input').first().isChecked()||await page.locator('#dbLogDays').inputValue()!=='30')throw Error('Database choices lost on reload');
  await page.locator('#sessionsTab').click();
  if(!await page.locator('.session-row input').isChecked())throw Error('Session selection lost on reload');
  await page.locator('#filesTab').click();await page.locator('#filesAuto').click();
  if(!await checks.nth(0).isChecked()||await checks.nth(1).isChecked())throw Error('Auto selection included outputs');
  await page.locator('#filesFilter').selectOption('recommended');
  if(await page.locator('#filesRows tr').count()!==1)throw Error('Recommendation filter');
  await page.locator('#filesFilter').selectOption('all');
  await page.screenshot({path:'.investigation/file-cleanup.png',fullPage:true});
  await page.locator('#filesReview').click();await page.locator('#filesPlanDialog').waitFor({state:'visible'});
  if(planned.ids.length!==1||planned.ids[0]!==entries[0].id)throw Error('Wrong deletion selection');
  await page.locator('#filesExecute').click();await page.locator('#filesProgress').waitFor({state:'visible'});
  if(!submission.confirmed||submission.token!=='fixture-plan')throw Error('Missing explicit confirmation');
  await page.locator('#sessionsTab').click();if(!await page.locator('#plan').isDisabled())throw Error('Concurrent session delete enabled');
  await page.locator('#filesTab').click();await page.locator('#filesStop').click();await page.locator('#filesResult').waitFor({state:'visible'});
  if(!(await page.locator('#filesResult').innerText()).includes('已停止'))throw Error('Stopped results');
  await page.locator('#language').selectOption('en');
  if(await page.locator('#filesTab').textContent()!=='File cleanup')throw Error('Tab translation');
  if(!(await page.locator('#filesResult').innerText()).includes('Remaining cleanup stopped'))throw Error('Result translation');
  await page.setViewportSize({width:650,height:950});
  if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Page overflows narrow viewport');
  await page.screenshot({path:'.investigation/file-cleanup-narrow.png',fullPage:true});
  if(errors.length)throw Error(errors.join('\n'));
  console.log('PASS: tabs, auto selection, protected files, all selection persistence, plan/confirmation, progress/stop, localization and narrow layout');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1)});
