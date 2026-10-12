// File previews and Explorer actions use mocked endpoints throughout.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs=require('fs');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  const id='visualizations/2026/10/02/fixture-directory',token='preview-token';
  const names=['after/screen.png','notes.md','report.json','script.exe','index.html','slow.json'];
  const items=names.map(name=>({path:id+'/'+name,bytes:1024,modified:1700000000,kind:name.endsWith('.png')?'image':name.endsWith('.exe')?'unsupported':'text'}));
  const entry={id,name:id,bytes:6144,files:6,modified:1700000000,allowed:true,recommended:false,reason:'artifact',samples:[]};
  const log={...entry,id:'.sandbox/sandbox.2026-01-01.log',name:'.sandbox/sandbox.2026-01-01.log',files:1,reason:'old_log',recommended:true};
  await page.route('**/api/state',route=>route.fulfill({json:{csrf:'test',home:'preview-fixture',rows:[],complete:true,generation:1,status:'扫描完成',source:'fixture',error:'',cli:{available:true,lock_verified:true,message:'已验证',version:'fixture'},diagnostics:[],diagnostic_count:0}}));
  for(const endpoint of ['delete-progress','database-progress','files-progress'])await page.route('**/api/'+endpoint,route=>route.fulfill({json:{running:false}}));
  await page.route('**/api/files-inspect?*',route=>route.fulfill({json:{home:'preview-fixture',days:7,bytes:12288,entries:[entry,log],directories:[{name:'visualizations',bytes:6144,files:6,issues:0},{name:'.sandbox',bytes:6144,files:1,issues:0}]}}));
  await page.route('**/api/files-list?*',route=>{const query=new URL(route.request().url()).searchParams,root=query.get('id'),all=root===id?items:[{path:log.id,bytes:6144,modified:1700000000,kind:'text'}],filtered=all.filter(item=>item.path.includes(query.get('q')));return route.fulfill({json:{id:root,token,directory:root,total:all.length,matched:filtered.length,offset:0,next:null,items:filtered}});});
  const png=fs.existsSync('.investigation/files-grouped-desktop.png')?fs.readFileSync('.investigation/files-grouped-desktop.png'):Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jx4QAAAAASUVORK5CYII=','base64');
  await page.route('**/api/files-image?*',route=>route.fulfill({contentType:'image/png',body:png}));
  let releaseSlow,slowRequested;const slowReady=new Promise(resolve=>slowRequested=resolve);
  await page.route('**/api/files-preview?*',async route=>{
   const path=new URL(route.request().url()).searchParams.get('path'),item=items.find(item=>item.path===path)||{path:log.id,bytes:6144,modified:1700000000,kind:'text'};
   if(path.endsWith('slow.json')){const wait=new Promise(resolve=>releaseSlow=resolve);slowRequested();await wait;}
   return route.fulfill({json:{...item,text:path.endsWith('index.html')?'<script>window.previewExecuted=true</script>':path.endsWith('notes.md')?'# 清理前确认\n这是可阅读的说明。':path.endsWith('report.json')?'JSON current preview':path===log.id?'Single file log preview':'slow old response',truncated:path.endsWith('notes.md')}});
  });
  const opened=[];await page.route('**/api/files-reveal',route=>{opened.push(route.request().postDataJSON());return route.fulfill({json:{ok:true}});});
  await page.goto(process.env.CLEANER_URL || 'http://127.0.0.1:8766');await page.evaluate(()=>I18N.ready);await page.locator('#language').selectOption('zh-CN');await page.locator('#filesTab').click();
  await page.locator(`.file-entry[data-file-id="${id}"] .file-open-folder`).click();
  if(opened[0].id!==id)throw Error('Main list folder action used wrong item');
  await page.locator(`.file-entry[data-file-id="${id}"] .file-view`).click();await page.locator('#fileContentImage').waitFor({state:'visible'});
  await page.waitForFunction(()=>document.getElementById('filePreviewImage').naturalWidth>0&&document.querySelector('#fileBrowserRows img').naturalWidth>0);
  if((await page.locator('#fileBrowserRows .file-browser-item').first().innerText())!=='after/screen.png')throw Error('Full parent prefix remains in file names');
  await page.locator('#fileContentImage').click();await page.locator('#fileImageDialog').waitFor({state:'visible'});await page.waitForFunction(()=>document.getElementById('fileImageLarge').naturalWidth>0);await page.locator('#fileImageClose').click();
  await page.locator('#fileBrowserFolder').click();if(opened.at(-1).id!==id||opened.at(-1).path)throw Error('Browser folder action used wrong target');
  const select=name=>page.locator(`#fileBrowserRows tr[data-path="${id}/${name}"] .file-browser-item`).click();
  await select('notes.md');await page.locator('#fileContentText').waitFor({state:'visible'});
  if(!(await page.locator('#fileContentText').innerText()).includes('可阅读的说明')||!await page.locator('#fileContentNote').isVisible())throw Error('Text/truncation preview missing');
  await page.locator('#fileContentFolder').click();if(opened.at(-1).path!==id+'/notes.md'||opened.at(-1).token!==token)throw Error('Selected file reveal did not carry its capability');
  await select('script.exe');await page.waitForFunction(()=>document.getElementById('fileContentEmpty').textContent.includes('无法直接预览'));
  await select('index.html');await page.locator('#fileContentText').waitFor({state:'visible'});
  if(!(await page.locator('#fileContentText').innerText()).includes('<script>')||await page.evaluate(()=>!!window.previewExecuted))throw Error('Markup executed instead of being shown as text');
  await select('slow.json');await slowReady;await select('report.json');await page.waitForFunction(()=>document.getElementById('fileContentText').textContent==='JSON current preview');releaseSlow();
  await page.waitForResponse(response=>response.url().includes('/api/files-preview?')&&response.url().includes('slow.json'));
  if(await page.locator('#fileContentText').innerText()!=='JSON current preview')throw Error('Late preview replaced current file');
  await select('after/screen.png');await page.locator('#fileContentImage').waitFor({state:'visible'});await page.screenshot({path:'.investigation/files-preview-desktop.png'});
  for(const language of ['zh-CN','en']){await page.setViewportSize({width:375,height:844});await page.locator('#language').selectOption(language);if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Preview overflows mobile');const dialog=await page.locator('#fileBrowserDialog').boundingBox(),footer=await page.locator('.file-browser-footer').boundingBox();if(footer.y+footer.height>dialog.y+dialog.height)throw Error('Preview footer is clipped');}
  await page.locator('#language').selectOption('zh-CN');await page.screenshot({path:'.investigation/files-preview-mobile.png'});
  await page.locator('#fileBrowserSearch').fill('absent');await page.locator('#fileBrowserEmpty').waitFor({state:'visible'});if(!await page.locator('#fileContentEmpty').isVisible()||await page.locator('#fileContentImage').isVisible())throw Error('Empty search retained previous preview');
  await page.locator('#fileBrowserClose').click();await page.locator(`.file-entry[data-file-id="${log.id}"] .file-view`).click();await page.waitForFunction(()=>document.getElementById('fileContentText').textContent==='Single file log preview');
  if(errors.length)throw Error(errors.join('\n'));
  console.log('PASS: image thumbnails/zoom, relative names, safe text and unsupported previews, stale response suppression, native folder actions, empty search, single files and mobile layout');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1)});
