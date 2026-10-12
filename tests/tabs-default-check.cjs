// Old saved tabs must not change the landing page or trigger file scans.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  for(const width of [1440,375])for(const savedTab of ['files','database']){
   const page=await browser.newPage({viewport:{width,height:900}}),errors=[];let fileScans=0;
   page.on('pageerror',error=>errors.push(error.message));
   await page.addInitScript(savedTab=>{localStorage.setItem('cleaner.activeTab',savedTab);localStorage.setItem('cleaner.language','en');localStorage.setItem('cleaner.files:fixture',JSON.stringify({chosen:['retained-item'],search:'retained-filter',grouped:false}));},savedTab);
   await page.route('**/api/state',route=>route.fulfill({json:{csrf:'test',home:'fixture',rows:[],complete:true,generation:1,status:'扫描完成',source:'fixture',error:'',cli:{available:true,message:'已验证',version:'fixture'},diagnostics:[],diagnostic_count:0}}));
   for(const endpoint of ['delete-progress','database-progress','files-progress'])await page.route('**/api/'+endpoint,route=>route.fulfill({json:{running:false}}));
   await page.route('**/api/files-inspect?*',route=>{fileScans++;return route.fulfill({json:{home:'fixture',days:7,bytes:0,entries:[],directories:[]}});});
   await page.goto(process.env.CLEANER_URL || 'http://127.0.0.1:8766');await page.evaluate(()=>I18N.ready);
   if(await page.locator('#sessionsTab').getAttribute('aria-selected')!=='true'||!await page.locator('#sessionsPanel').isVisible()||await page.locator('#filesPanel').isVisible())throw Error('Saved tab changed default landing page');
   if(fileScans!==0)throw Error('Landing page started an unwanted file inspection');
   if(await page.title()!=='Codex Cleaner'||await page.locator('header h1').textContent()!=='Codex Cleaner')throw Error('Product branding not updated');
   const preferences=await page.evaluate(()=>JSON.parse(localStorage.getItem('cleaner.files:fixture')));
   if(preferences.chosen[0]!=='retained-item'||preferences.search!=='retained-filter'||preferences.grouped!==false||await page.locator('#language').inputValue()!=='en')throw Error('Landing preference change discarded other settings');
   await page.locator('#filesTab').click();await page.locator('#filesLoading').waitFor({state:'hidden'});
   if(await page.locator('#filesTab').getAttribute('aria-selected')!=='true')throw Error('Manual tab switching failed');
   const scans=fileScans;await page.reload();await page.evaluate(()=>I18N.ready);
   if(await page.locator('#sessionsTab').getAttribute('aria-selected')!=='true'||fileScans!==scans)throw Error('Reload did not return to Sessions');
   await page.locator('#sessionsTab').focus();await page.keyboard.press('End');
   if(await page.locator('#filesTab').getAttribute('aria-selected')!=='true')throw Error('Keyboard tab navigation failed');
   if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Renamed mobile header overflows');
   if(errors.length)throw Error(errors.join('\n'));await page.close();
  }
  console.log('PASS: Sessions landing/reload regardless of old saved tab, no automatic file scan, preserved preferences, keyboard navigation and Codex Cleaner branding on desktop/mobile');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1)});
