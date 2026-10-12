// Hold inspection responses to compare the actual loading and ready layouts.
// Every API endpoint is mocked; no cleanup is performed.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  for(const size of [{width:1440,height:900},{width:1100,height:900},{width:375,height:844}])for(const grouped of [true,false]){
   const page=await browser.newPage({viewport:size}),errors=[];
   page.on('pageerror',error=>errors.push(error.message));
   await page.addInitScript(({grouped})=>{localStorage.setItem('cleaner.language','zh-CN');localStorage.setItem('cleaner.files:loading-fixture',JSON.stringify({grouped,chosen:['.sandbox/example.log'],days:'7',search:'',filter:'all'}));},{grouped});
   await page.route('**/api/state',route=>route.fulfill({json:{csrf:'test',home:'loading-fixture',rows:[],complete:true,generation:1,status:'扫描完成',source:'fixture',error:'',cli:{available:true,lock_verified:true,message:'已验证',version:'fixture'},diagnostics:[],diagnostic_count:0}}));
   for(const endpoint of ['delete-progress','database-progress','files-progress'])await page.route('**/api/'+endpoint,route=>route.fulfill({json:{running:false}}));
   let release,requested,inspectReady=new Promise(resolve=>requested=resolve);
   const data={home:'loading-fixture',days:7,bytes:1024,entries:[{id:'.sandbox/example.log',name:'.sandbox/example.log',bytes:1024,files:1,modified:1700000000,allowed:true,recommended:true,reason:'old_log',samples:[]}],directories:[{name:'.sandbox',bytes:1024,files:1,issues:0}]};
   await page.route('**/api/files-inspect?*',async route=>{const gate=new Promise(resolve=>release=resolve);requested();await gate;await route.fulfill({json:data});});
   await page.goto(process.env.CLEANER_URL || 'http://127.0.0.1:8766');await page.evaluate(()=>I18N.ready);await page.locator('#filesTab').click();await inspectReady;
   const geometry=()=>page.evaluate(()=>Object.fromEntries(['#filesNav','.files-workspace','.files-list-toolbar','.files-filters','.files-list','.files-list thead','.files-list th:nth-child(1)','.files-list th:nth-child(2)','.files-list th:nth-child(3)','.files-list th:nth-child(4)','.files-list th:nth-child(5)','.files-footer'].filter(selector=>!document.querySelector(selector).hidden).map(selector=>{const r=document.querySelector(selector).getBoundingClientRect();return [selector,{x:r.x,y:r.y,width:r.width,height:r.height}];})));
   const before=await geometry();
   if(await page.locator('#filesNav').isVisible()!==grouped)throw Error('Saved grouping not applied while loading');
   if(!await page.locator('#filesLoading').isVisible()||await page.locator('.files-list').getAttribute('aria-busy')!=='true')throw Error('Loading state missing');
   if(!await page.locator('#filesSelectAll').isDisabled())throw Error('Empty loading list is selectable');
   if(grouped&&size.width>800&&before['#filesNav'].x+before['#filesNav'].width>=before['.files-workspace'].x)throw Error('Loading sidebar is stacked on desktop');
   if(grouped&&size.width===1440)await page.screenshot({path:'.investigation/files-loading-desktop.png'});
   if(grouped&&size.width===375)await page.screenshot({path:'.investigation/files-loading-mobile.png'});
   release();await page.locator('#filesLoading').waitFor({state:'hidden'});await page.locator('.file-entry').waitFor();
   const after=await geometry();
   for(const selector of Object.keys(before))for(const field of ['x','y','width','height'])if(Math.abs(before[selector][field]-after[selector][field])>1)throw Error('Loading layout shifted: '+JSON.stringify({size,grouped,selector,field,before,after}));
   inspectReady=new Promise(resolve=>requested=resolve);await page.locator('#filesRefresh').click();await inspectReady;
   if(!await page.locator('.file-entry input').isChecked()||!(await page.locator('#filesScanText').innerText()).length)throw Error('Refresh discarded selected data or has no progress');
   const refreshing=await geometry();for(const selector of Object.keys(after))for(const field of ['x','y','width','height'])if(Math.abs(refreshing[selector][field]-after[selector][field])>1)throw Error('Refresh shifted layout');
   release();await page.waitForFunction(()=>document.getElementById('filesScanText').textContent==='');
   if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Loading layout overflows');
   if(errors.length)throw Error(errors.join('\n'));await page.close();
  }
  console.log('PASS: stable initial/ready/refresh geometry on desktop, tablet and mobile; saved flat/grouped layouts; loading controls and retained selection');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1)});
