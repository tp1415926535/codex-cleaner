// Regression check for viewport scrolling, header alignment, and full file browsing.
// Uses mocked API data, including a directory with 5294 files.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:900}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  const folder={id:'.tmp/plugins',name:'.tmp/plugins',category:'.tmp',bytes:68000000,files:5294,modified:1700000000,allowed:true,recommended:true,reason:'temporary',samples:['.tmp/plugins/example-1.md','.tmp/plugins/example-2.md','.tmp/plugins/example-3.md']};
  const entries=[folder,...Array.from({length:200},(_,index)=>({id:`.sandbox/sandbox.2025-01-${String(index).padStart(3,'0')}.log`,name:`.sandbox/sandbox.2025-01-${String(index).padStart(3,'0')}.log`,category:'.sandbox',bytes:1024,files:1,modified:1700000000,allowed:true,recommended:true,reason:'old_log',samples:['same-single-file']}))];
  const directories=Array.from({length:32},(_,index)=>({name:`directory-${String(index).padStart(2,'0')}`,bytes:4096,files:index+1,issues:0}));
  await page.route('**/api/state',route=>route.fulfill({json:{csrf:'test',home:'layout-fixture',rows:[],complete:true,generation:1,status:'扫描完成',source:'fixture',error:'',cli:{available:true,lock_verified:true,message:'删除能力与会话锁检测已验证',version:'fixture'},diagnostics:[],diagnostic_count:0}}));
  await page.route('**/api/delete-progress',route=>route.fulfill({json:{running:false}}));
  await page.route('**/api/database-progress',route=>route.fulfill({json:{running:false}}));
  await page.route('**/api/files-progress',route=>route.fulfill({json:{running:false}}));
  await page.route('**/api/files-inspect?*',route=>route.fulfill({json:{home:'layout-fixture',days:7,bytes:68204800,entries,directories}}));
  await page.route('**/api/files-plan',route=>route.fulfill({json:{token:'read-only-fixture',entries,files:5494,bytes:68204800}}));
  await page.route('**/api/files-list?*',route=>{
   const query=new URL(route.request().url()).searchParams,offset=Number(query.get('offset')),search=query.get('q').toLowerCase();
   const names=Array.from({length:5294},(_,index)=>`.tmp/plugins/nested/file-${String(index).padStart(5,'0')}.md`).filter(name=>name.includes(search));
   return route.fulfill({json:{id:folder.id,total:5294,matched:names.length,offset,next:offset+100<names.length?offset+100:null,items:names.slice(offset,offset+100).map(path=>({path,bytes:1024,modified:1700000000}))}});
  });
  await page.goto(process.env.CLEANER_URL || 'http://127.0.0.1:8766');await page.evaluate(()=>I18N.ready);
  await page.locator('#language').selectOption('zh-CN');await page.locator('#filesTab').click();await page.locator('#filesRows .file-entry').nth(200).waitFor();
  if(await page.locator('#filesRows details').count())throw Error('Pointless inline disclosure remains');
  if(await page.locator('#filesRows .file-view').count()!==entries.length)throw Error('Files lack preview controls');
  await page.locator('.file-entry[data-file-id=".tmp/plugins"] .file-view').click();await page.locator('#fileBrowserRows tr').nth(99).waitFor();
  if(!(await page.locator('#fileBrowserCount').innerText()).includes('5294'))throw Error('Total file count missing');
  await page.locator('#fileBrowserNext').click();
  await page.waitForFunction(()=>document.querySelector('#fileBrowserRows tr td').textContent.endsWith('file-00100.md'));
  await page.locator('#fileBrowserSearch').fill('05293');
  await page.waitForFunction(()=>document.querySelectorAll('#fileBrowserRows tr').length===1);
  if(!(await page.locator('#fileBrowserRows').innerText()).includes('file-05293.md'))throw Error('Full directory search did not reach the final file');
  await page.locator('#fileBrowserClose').click();
  for(const size of [{width:1440,height:900},{width:390,height:844},{width:375,height:667}]){
   await page.setViewportSize(size);
   for(const language of ['zh-CN','en']){
    await page.locator('#language').selectOption(language);
    const header=await page.evaluate(()=>{const rect=selector=>document.querySelector(selector).getBoundingClientRect();const actions=rect('.header-actions'),settings=rect('#settings'),language=rect('#language'),header=rect('header');return {right:actions.right,settingsRight:settings.right,settingsTop:settings.top,languageTop:language.top,expected:header.right-parseFloat(getComputedStyle(document.querySelector('header')).paddingRight),overflow:document.documentElement.scrollWidth>innerWidth};});
    if(Math.abs(header.right-header.expected)>2||Math.abs(header.settingsRight-header.right)>2||Math.abs(header.settingsTop-header.languageTop)>4||header.overflow)throw Error('Header alignment: '+JSON.stringify({size,language,header}));
    if(await page.locator('.files-inventory').count())throw Error('Bottom inventory remains');
    await page.locator('#filesNavItems').evaluate(element=>element.scrollTop=element.scrollHeight);
    const last=await page.locator('#filesNavItems .nav-project').last().boundingBox(),panel=await page.locator('#filesNavItems').boundingBox();
    if(last.y<panel.y||last.y+last.height>panel.y+panel.height+1)throw Error('Last directory cannot be reached: '+JSON.stringify({size,last,panel}));
    const reachable=await page.locator('#filesNavItems .nav-project').last().evaluate(element=>{const r=element.getBoundingClientRect(),hit=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);return element.contains(hit);});
    if(!reachable)throw Error('Directory is covered');
    await page.locator('#filesNavItems [data-folder=".sandbox"]').click();
    const aligned=await page.evaluate(()=>{const wrapper=document.querySelector('.files-list'),row=document.querySelector('.file-group[data-folder=".sandbox"]');return Math.abs(row.getBoundingClientRect().top-wrapper.getBoundingClientRect().top-wrapper.querySelector('thead').offsetHeight)<5;});
    if(!aligned)throw Error('Directory jump did not align target');
    const footer=await page.locator('.files-footer').boundingBox();
    if(footer.y+footer.height>size.height+1)throw Error('File footer clipped');
    await page.locator('#filesReview').click();await page.locator('#filesPlanDialog').waitFor({state:'visible'});await page.waitForFunction(()=>!document.getElementById('filesExecute').disabled);
    await page.locator('#filesPlanClose').click();
   }
  }
  await page.locator('#language').selectOption('zh-CN');await page.locator('#filesPanel').evaluate(element=>element.scrollTop=0);
  await page.screenshot({path:'.investigation/files-layout-mobile.png'});
  await page.locator('#sessionsTab').click();
  const footer=await page.locator('.list>footer').boundingBox();
  if(footer.y+footer.height>667)throw Error('Sessions footer was clipped by its tab wrapper');
  if(errors.length)throw Error(errors.join('\n'));
  console.log('PASS: right-aligned mobile actions, no single-file disclosure, complete 5294-file pagination/search, reachable directory sidebar with jump alignment and session footer');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1)});
