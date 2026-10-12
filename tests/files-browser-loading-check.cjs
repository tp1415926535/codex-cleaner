// Delayed list and content responses prove the two loading states are independent.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  for(const size of [{width:1440,height:1000},{width:375,height:844}]){
   const page=await browser.newPage({viewport:size}),errors=[];
   page.on('pageerror',error=>errors.push(error.message));
   const id='.sandbox/sandbox.2026-07-29.log',snapshot='inspection-snapshot';
   const item={path:id,bytes:18*1024*1024,modified:1700000000,kind:'text'};
   const entry={...item,id,name:id,files:1,allowed:true,recommended:true,reason:'old_log',samples:[id]};
   await page.route('**/api/state',route=>route.fulfill({json:{csrf:'test',home:'loading-fixture',rows:[],complete:true,generation:1,status:'扫描完成',source:'fixture',error:'',cli:{available:true,lock_verified:true,message:'已验证',version:'fixture'},diagnostics:[],diagnostic_count:0}}));
   for(const endpoint of ['delete-progress','database-progress','files-progress'])await page.route('**/api/'+endpoint,route=>route.fulfill({json:{running:false}}));
   await page.route('**/api/files-inspect?*',route=>route.fulfill({json:{home:'loading-fixture',snapshot,days:7,bytes:item.bytes,entries:[entry],directories:[{name:'.sandbox',bytes:item.bytes,files:1,issues:0}]}}));
   let releaseList,listRequested,releasePreview,previewRequested;
   const listReady=new Promise(resolve=>listRequested=resolve),previewReady=new Promise(resolve=>previewRequested=resolve);
   await page.route('**/api/files-list?*',async route=>{if(new URL(route.request().url()).searchParams.get('snapshot')!==snapshot)throw Error('Inspection snapshot missing');const gate=new Promise(resolve=>releaseList=resolve);listRequested();await gate;await route.fulfill({json:{id,token:'preview-token',total:1,matched:1,offset:0,next:null,items:[item]}});});
   await page.route('**/api/files-preview?*',async route=>{const gate=new Promise(resolve=>releasePreview=resolve);previewRequested();await gate;await route.fulfill({json:{...item,text:'The delayed log content',truncated:true}});});
   let opened=null;await page.route('**/api/files-reveal',route=>{opened=route.request().postDataJSON();return route.fulfill({json:{ok:true}});});
   await page.goto(process.env.CLEANER_URL || 'http://127.0.0.1:8766');await page.evaluate(()=>I18N.ready);await page.locator('#language').selectOption('zh-CN');await page.locator('#filesTab').click();await page.locator('.file-entry .file-view').click();await listReady;
   if(await page.locator('#fileBrowserRows tr').count()!==1||!(await page.locator('#fileBrowserRows').innerText()).includes('18.00 MiB'))throw Error('Known single-file metadata waited for the list response');
   if(!await page.locator('#fileContentLoading').isVisible()||await page.locator('#fileContentText').isVisible())throw Error('Pending detail did not have its own loading state');
   const geometry=()=>page.evaluate(()=>Object.fromEntries(['.file-browser-body','.file-browser-scroll','.file-content-preview','.file-browser-footer'].map(selector=>{const r=document.querySelector(selector).getBoundingClientRect();return [selector,{x:r.x,y:r.y,width:r.width,height:r.height}];})));
   const before=await geometry();
   releaseList();await previewReady;
   if(await page.locator('#fileBrowserLoading').isVisible()||!await page.locator('#fileContentLoading').isVisible()||await page.locator('#fileBrowserRows tr').count()!==1)throw Error('Content request blocked the list');
   const pending=await geometry();for(const selector of Object.keys(before))for(const field of ['x','y','width','height'])if(Math.abs(before[selector][field]-pending[selector][field])>1)throw Error('List loading shifted the browser layout');
   await page.locator('#fileBrowserFolder').click();if(opened?.snapshot!==snapshot||opened?.id!==id)throw Error('Folder action did not use cached inspection');
   await page.screenshot({path:'.investigation/files-detail-loading-'+(size.width>800?'desktop':'mobile')+'.png'});
   releasePreview();await page.locator('#fileContentText').waitFor({state:'visible'});
   if(await page.locator('#fileContentText').innerText()!=='The delayed log content')throw Error('Delayed content was not displayed');
   if(errors.length)throw Error(errors.join('\n'));await page.close();
  }
  console.log('PASS: immediate single-file metadata, independent delayed detail, unchanged browser geometry and cached folder action on desktop/mobile');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1)});
