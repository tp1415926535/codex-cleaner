// Every endpoint is mocked. This never invokes the real cleanup service.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  let running=false,finished=false,starts=0;
  const path='C:\\Users\\fixture\\AppData\\Local\\Packages\\OpenAI.Codex_fixture\\LocalCache\\Roaming\\Codex';
  const entry={id:'desktop-app/fixture/Cache',name:'desktop/Cache',path:path+'\\Cache',kind:'cache',source:'desktop',bytes:4*1024**3,files:5643,modified:1700000000,allowed:true,recommended:false,reason:'desktop_cache',samples:[]};
  const skipped={path,actual_path:path,status:'skipped',files:3986,bytes:0,reason:'desktop_cache_in_use',error:'Codex 桌面应用已启动或运行状态无法确认，剩余缓存已跳过；请退出桌面应用后重新检查。'};
  await page.route('**/api/**',route=>{
   const endpoint=new URL(route.request().url()).pathname;
   let data={running:false};
   if(endpoint==='/api/state')data={csrf:'fixture',home:'modal-fixture',rows:[],complete:true,generation:1,status:'',error:'',cli:{available:true,lock_verified:true},diagnostics:[],diagnostic_count:0};
   if(endpoint==='/api/files-inspect')data={home:'modal-fixture',days:7,bytes:entry.bytes,entries:[{...entry,allowed:!finished,reason:finished?'desktop_running':entry.reason}],directories:[]};
   if(endpoint==='/api/files-plan')data={token:'fixture',entries:[entry],files:entry.files,bytes:entry.bytes};
   if(endpoint==='/api/files-start'){running=true;starts++;data={ok:true};}
   if(endpoint==='/api/files-progress')data={running,started:1,done:finished?5643:100,total:5643,success:finished?1657:100,failed:0,skipped:finished?3986:0,bytes:finished?3.01*1024**3:1024,results:finished?[{path:'successful files',status:'success',files:1657,bytes:3.01*1024**3},skipped]:[],error:''};
   return route.fulfill({json:data});
  });
  await page.goto(process.env.CLEANER_URL || 'http://127.0.0.1:18766');await page.evaluate(()=>I18N.ready);
  await page.locator('#language').selectOption('zh-CN');await page.locator('#filesTab').click();await page.locator('.file-entry input').check();
  await page.locator('#filesReview').click();await page.waitForFunction(()=>!document.getElementById('filesExecute').disabled);await page.locator('#filesExecute').click();
  await page.locator('#filesProgress').waitFor({state:'visible'});
  if(!await page.locator('#filesPlanDialog').isVisible()||!await page.locator('#filesProgress').evaluate(node=>!!node.closest('#filesPlanDialog')))throw Error('Cleanup escaped confirmation dialog');
  await page.keyboard.press('Escape');if(!await page.locator('#filesPlanDialog').isVisible()||!await page.locator('#filesPlanClose').isDisabled())throw Error('Active cleanup can be closed');
  await page.reload();await page.evaluate(()=>I18N.ready);await page.locator('#filesProgress').waitFor({state:'visible'});
  if(!await page.locator('#filesPlanDialog').isVisible()||!await page.locator('#filesPlanClose').isDisabled())throw Error('Reload did not reconnect to protected cleanup dialog');
  running=false;finished=true;await page.locator('#filesResult').waitFor({state:'visible'});
  const text=await page.locator('#filesResult').innerText();
  if(!text.includes('部分完成')||!text.includes('成功 1657')||!text.includes('失败 0')||!text.includes('跳过 3986'))throw Error('Skipped caches reported as failed or total success');
  await page.locator('#filesResult summary').click();
  if(await page.locator('#filesResult p').count()>8||!(await page.locator('#filesResult').innerText()).includes(path))throw Error('Repeated skipped rows or unreadable virtual path');
  if(!await page.locator('#filesRetry').isVisible()||await page.locator('#filesPlanClose').isDisabled())throw Error('Completion controls unavailable');
  await page.evaluate(()=>showTab('files'));await page.screenshot({path:'.investigation/files-modal-partial.png'});
  await page.evaluate(()=>I18N.setLanguage('en'));
  const english=await page.locator('#filesResult').innerText();
  if(!english.includes('3986 skipped')||!english.includes('desktop app started')||!english.includes(path))throw Error('Result details lost or untranslated after language change');
  await page.setViewportSize({width:650,height:900});
  if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Cleanup modal overflows narrow viewport');
  await page.locator('#filesRetry').click();await page.locator('#filesPlanDialog').waitFor({state:'hidden'});
  if(starts!==1)throw Error('Retry automatically executed deletion');
  if(errors.length)throw Error(errors.join('\n'));
  console.log('PASS: in-dialog cleanup and results, busy close protection, reconnect, truthful skip counts, grouped reasons, actual paths, retry, translation and narrow layout');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1)});
