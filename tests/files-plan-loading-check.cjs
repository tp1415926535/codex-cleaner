// Delayed and failed plan responses are mocked. No user files are inspected or removed.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 const gates=[];
 try{
  const page=await browser.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
  let notify=()=>{};
  const entry={id:'.sandbox/fixture.log',name:'.sandbox/fixture.log',bytes:1024,files:1,modified:1700000000,allowed:true,recommended:true,reason:'old_log',samples:[]};
  await page.route('**/api/**',async route=>{
   const endpoint=new URL(route.request().url()).pathname;
   if(endpoint==='/api/files-plan'){
    const index=gates.length,reply=await new Promise(resolve=>{gates.push(resolve);notify();});
    try{await route.fulfill(reply||{json:{token:'plan-'+index,entries:[{...entry,name:'plan-'+index}],files:1,bytes:1024}});}catch{}
    return;
   }
   let data={running:false};
   if(endpoint==='/api/state')data={csrf:'fixture',home:'plan-loading',rows:[],complete:true,generation:1,status:'',error:'',cli:{available:true,lock_verified:true},diagnostics:[],diagnostic_count:0};
   if(endpoint==='/api/files-inspect')data={home:'plan-loading',days:7,entries:[entry],bytes:1024,directories:[]};
   return route.fulfill({json:data});
  });
  await page.goto(process.env.CLEANER_URL || 'http://127.0.0.1:18766');await page.evaluate(()=>I18N.ready);
  await page.locator('#language').selectOption('zh-CN');await page.locator('#filesTab').click();await page.locator('.file-entry').waitFor();
  async function begin(){const requested=new Promise(resolve=>notify=resolve);await page.locator('#filesReview').click();await requested;await page.locator('#filesPlanDialog').waitFor({state:'visible'});}
  async function ready(){await page.waitForFunction(()=>!document.getElementById('filesExecute').disabled);}
  await begin();
  if(!await page.locator('#filesPlanLoading').isVisible()||!await page.locator('#filesExecute').isDisabled())throw Error('No immediate plan loading dialog or unsafe confirmation');
  // The existing controls timer runs every 1.5 seconds: it must not re-enable this request.
  await page.waitForTimeout(2200);
  if(!await page.locator('#filesReview').isDisabled()||await page.locator('#filesReview').getAttribute('aria-busy')!=='true')throw Error('Timer re-enabled pending plan');
  if(!await page.locator('.file-entry input').isDisabled()||!await page.locator('#filesDays').isDisabled()||!await page.locator('#filesRefresh').isDisabled())throw Error('Selection changed while preparing plan');
  await page.evaluate(()=>document.getElementById('filesReview').onclick());
  if(gates.length!==1)throw Error('Duplicate plan request');
  await page.evaluate(()=>I18N.setLanguage('en'));
  if(!(await page.locator('#filesReview').textContent()).includes('Preparing')||!(await page.locator('#filesPlanLoading').textContent()).includes('Checking'))throw Error('Loading translations');
  gates[0]();await ready();
  if(await page.locator('#filesPlanLoading').isVisible()||!(await page.locator('#filesPlanList').innerText()).includes('plan-0'))throw Error('Loaded plan not displayed');
  await page.keyboard.press('Escape');
  await begin();await page.locator('#filesPlanClose').click();await page.locator('#filesPlanDialog').waitFor({state:'hidden'});
  await page.waitForFunction(()=>!document.getElementById('filesReview').disabled);
  await begin();gates[1]();await page.waitForTimeout(100);
  if(!await page.locator('#filesPlanLoading').isVisible()||!await page.locator('#filesExecute').isDisabled())throw Error('Canceled response replaced new pending plan');
  gates[2]();await ready();
  if(!(await page.locator('#filesPlanList').innerText()).includes('plan-2'))throw Error('New plan lost after cancellation');
  await page.keyboard.press('Escape');await begin();gates[3]({status:400,json:{error:'fixture plan failed'}});
  await page.locator('#filesPlanDialog').waitFor({state:'hidden'});await page.locator('#filesError').waitFor({state:'visible'});
  await page.waitForFunction(()=>!document.getElementById('filesReview').disabled);
  await begin();gates[4]();await ready();
  if(await page.locator('#filesError').isVisible())throw Error('Plan retry kept old error');
  if(errors.length)throw Error(errors.join('\n'));
  console.log('PASS: immediate plan loading, timer-safe busy controls, duplicate prevention, translations, cancellation/stale responses and failed-plan retry');
 }finally{for(const release of gates)release();await browser.close();}
})().catch(error=>{console.error(error);process.exit(1)});
