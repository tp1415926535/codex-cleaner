// All APIs are mocked; this check never changes user caches or logs.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  let running=true,planned=null;
  const cache={id:'desktop-app/cache-source/web/Codex/Default/Partitions/codex-browser-app/Service Worker/CacheStorage',
   name:'OpenAI.Codex_fixture/web/Codex/Default/Partitions/codex-browser-app/Service Worker/CacheStorage',
   path:'C:\\Users\\fixture\\AppData\\Local\\Packages\\OpenAI.Codex_fixture\\LocalCache\\Roaming\\Codex\\web\\Codex\\Default\\Partitions\\codex-browser-app\\Service Worker\\CacheStorage',
   kind:'cache',source:'desktop',bytes:2433234863,files:1931,modified:1700000000,recommended:false,samples:[]};
  const log={id:'desktop-app/log-source/Logs/2026/10/09',name:'OpenAI.Codex_fixture/Logs/2026/10/09',
   path:'C:\\Users\\fixture\\AppData\\Local\\Packages\\OpenAI.Codex_fixture\\LocalCache\\Local\\Codex\\Logs\\2026\\10\\09',
   kind:'logs',source:'desktop',bytes:600388724,files:127,modified:1700000000,allowed:true,recommended:true,reason:'desktop_log',samples:[]};
  const runtime={id:'desktop-app/runtime-source/bin/codex.exe',name:'desktop/bin/codex.exe',
   path:'C:\\Users\\fixture\\AppData\\Local\\OpenAI\\Codex\\bin\\codex.exe',kind:'runtime',source:'desktop',
   bytes:245812016,files:1,modified:1700000000,allowed:true,recommended:false,reason:'runtime_unused',samples:[]};
  const current={...runtime,id:'desktop-app/runtime-source/bin/e78bad9887fa50cf',name:'desktop/bin/e78bad9887fa50cf',
   path:'C:\\Users\\fixture\\AppData\\Local\\OpenAI\\Codex\\bin\\e78bad9887fa50cf',allowed:false,reason:'runtime_current'};
  await page.route('**/api/**',route=>{
   const url=new URL(route.request().url()),endpoint=url.pathname;
   let data={running:false};
   if(endpoint==='/api/state')data={csrf:'fixture',home:'desktop-fixture',rows:[],complete:true,generation:1,status:'',error:'',cli:{available:true,lock_verified:true},diagnostics:[],diagnostic_count:0};
   if(endpoint==='/api/files-inspect')data={home:'desktop-fixture',days:7,bytes:cache.bytes+log.bytes+runtime.bytes+current.bytes,entries:[log,{...cache,allowed:!running,reason:running?'desktop_running':'desktop_cache'},runtime,current],directories:[{name:'desktop-app',bytes:cache.bytes+log.bytes+runtime.bytes+current.bytes,files:2060,issues:0}]};
   if(endpoint==='/api/files-plan'){planned=route.request().postDataJSON();const entries=[cache,runtime].filter(entry=>planned.ids.includes(entry.id));data={token:'fixture',entries,files:entries.reduce((n,entry)=>n+entry.files,0),bytes:entries.reduce((n,entry)=>n+entry.bytes,0)};}
   return route.fulfill({json:data});
  });
  await page.goto(process.env.CLEANER_URL || 'http://127.0.0.1:18766');await page.evaluate(()=>I18N.ready);
  await page.locator('#language').selectOption('zh-CN');await page.locator('#filesTab').click();
  const cacheRow=page.locator('.file-entry').filter({hasText:'Service Worker/CacheStorage'}),logRow=page.locator('.file-entry').filter({hasText:'Logs/2026/10/09'});
  await cacheRow.waitFor();
  if(!await cacheRow.locator('input').isDisabled())throw Error('Live desktop cache enabled');
  if(!await logRow.locator('input').isChecked())throw Error('Old desktop logs not recommended');
  const runtimeRow=page.locator('.file-entry[data-file-id="'+runtime.id+'"]'),currentRow=page.locator('.file-entry[data-file-id="'+current.id+'"]');
  if(await runtimeRow.locator('input').isChecked()||!await currentRow.locator('input').isDisabled())throw Error('Runtime recommendations or current version protection');
  if(!(await cacheRow.innerText()).includes(cache.path)||!(await cacheRow.innerText()).includes('退出'))throw Error('Missing real path or exit guidance');
  if(!(await page.locator('#filesNavItems').innerText()).includes('Codex 桌面缓存、日志与运行库'))throw Error('Untranslated desktop source group');
  await page.locator('#filesSearch').fill('LocalCache\\Local');
  if(await page.locator('.file-entry').count()!==1||!(await page.locator('.file-entry').innerText()).includes(log.path))throw Error('Absolute log path search');
  await page.locator('#filesSearch').fill('');
  running=false;await page.locator('#filesRefresh').click();
  await page.waitForFunction(()=>!document.querySelector('.file-entry[data-file-id*="cache-source"] input').disabled);
  if(await cacheRow.locator('input').isChecked())throw Error('Desktop cache auto-selected');
  await logRow.locator('input').uncheck();await cacheRow.locator('input').check();
  await page.locator('#filesReview').click();await page.locator('#filesPlanDialog').waitFor({state:'visible'});await page.waitForFunction(()=>!document.getElementById('filesExecute').disabled);
  if(planned.ids.length!==1||planned.ids[0]!==cache.id)throw Error('Wrong desktop plan selection');
  const plan=await page.locator('#filesPlanList').innerText();
  if(!plan.includes(cache.path)||!plan.includes('离线资源'))throw Error('Missing desktop path or cache consequence in plan');
  await page.keyboard.press('Escape');
  await cacheRow.locator('input').uncheck();await runtimeRow.locator('input').check();
  await page.locator('#filesReview').click();await page.locator('#filesPlanDialog').waitFor({state:'visible'});await page.waitForFunction(()=>!document.getElementById('filesExecute').disabled);
  const runtimePlan=await page.locator('#filesPlanList').innerText();
  if(planned.ids.length!==1||planned.ids[0]!==runtime.id||!runtimePlan.includes(runtime.path)||!runtimePlan.includes('动态路径'))throw Error('Runtime plan path or scope warning');
  await page.keyboard.press('Escape');
  await page.locator('#language').selectOption('en');
  if(!(await page.locator('#filesNavItems').innerText()).includes('Codex desktop caches, logs and runtimes'))throw Error('English source navigation');
  if(!(await cacheRow.innerText()).includes('Offline resources'))throw Error('English cache advice');
  await page.screenshot({path:'.investigation/desktop-cleanup.png',fullPage:true});
  await page.setViewportSize({width:650,height:950});
  if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Long desktop paths overflow narrow page');
  await page.screenshot({path:'.investigation/desktop-cleanup-narrow.png',fullPage:true});
  if(errors.length)throw Error(errors.join('\n'));
  console.log('PASS: desktop source navigation, real path search, running protection, manual caches, recommended logs, plan warning, translations and narrow layout');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1)});
