// Development-only check: all API responses and outages are simulated.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try {
  const page=await browser.newPage();
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  const row={id:'fixture-session',title:'重新连接测试',kind:'main',project:'测试项目',cwd:'fixture',size:1024,reclaimable:1024,updated_at:1,issues:[],missing_files:[],file_count:1,activity:{code:'idle'},state:'普通'};
  let offline=false,scanError='';
  await page.route('**/api/state',route=>offline?route.abort('failed'):route.fulfill({json:{csrf:'test',rows:[row],complete:true,generation:1,status:'扫描完成',source:'fixture',error:scanError,cli:{available:true,lock_verified:true,message:'删除能力与会话锁检测已验证',version:'fixture',path:'fixture'},diagnostics:[],diagnostic_count:0}}));
  await page.route('**/api/delete-progress',route=>route.fulfill({json:{running:false}}));
  await page.route('**/api/database-progress',route=>route.fulfill({json:{running:false}}));
  await page.route('**/api/files-progress',route=>route.fulfill({json:{running:false}}));
  await page.goto(process.env.CLEANER_URL || 'http://127.0.0.1:8766');
  await page.evaluate(()=>I18N.ready);
  await page.locator('#language').selectOption('zh-CN');
  await page.locator('.session-row input').check();
  await page.locator('#search').fill(row.title);
  offline=true;
  await page.locator('#error').waitFor({state:'visible',timeout:12000});
  if(!(await page.locator('#error').innerText()).includes('Failed to fetch'))throw Error('Missing connection error');
  offline=false;
  await page.locator('#error').waitFor({state:'hidden',timeout:12000});
  if(await page.locator('#error').textContent()!=='')throw Error('Recovered error text remains');
  if(!await page.locator('.session-row input').isChecked())throw Error('Selection lost on reconnect');
  if(await page.locator('#search').inputValue()!==row.title)throw Error('Filter lost on reconnect');
  if(await page.locator('#plan').isDisabled())throw Error('Selection no longer usable');
  await page.evaluate(()=>error(new Error('操作失败测试')));
  offline=true;await page.evaluate(()=>poll());
  if(!(await page.locator('#error').innerText()).includes('Failed to fetch'))throw Error('Outage was not shown');
  offline=false;await page.evaluate(()=>poll());
  if(await page.locator('#error').innerText()!=='操作失败测试')throw Error('Operation error lost after reconnect');
  await page.evaluate(()=>clearError('operation'));
  scanError='扫描失败测试';await page.evaluate(()=>poll());
  if(await page.locator('#error').innerText()!==scanError)throw Error('Backend scan error hidden');
  scanError='';await page.evaluate(()=>poll());
  if(await page.locator('#error').isVisible())throw Error('Resolved scan error remains');
  let planFailure='请求过大';
  await page.route('**/api/plan',route=>route.fulfill(planFailure?
   {status:413,json:{error:planFailure}}:
   {json:{token:'fixture-plan',allowed:true,bytes:row.size,blockers:[],entries:[{id:row.id,title:row.title,files:[],bytes:row.size,blockers:[]}]}}));
  await page.locator('#plan').click();
  await page.waitForFunction(()=>document.getElementById('error').textContent==='请求过大');
  await page.evaluate(()=>poll());
  if(!await page.locator('#error').isVisible())throw Error('Polling hid unresolved plan error');
  planFailure='请求超过 16384 KiB 上限，请减少选择项后重试';
  await page.locator('#plan').click();
  await page.waitForFunction(()=>document.getElementById('error').textContent.includes('16384'));
  scanError='扫描失败测试';await page.evaluate(()=>poll());
  planFailure='';await page.locator('#plan').click();
  await page.locator('#planDialog').waitFor({state:'visible'});
  if(await page.locator('#error').textContent()!==scanError)throw Error('Plan recovery hid unrelated scan error');
  await page.locator('#closePlan').click();
  scanError='';await page.evaluate(()=>poll());
  if(await page.locator('#error').isVisible()||await page.locator('#error').textContent()!=='')throw Error('Successful plan retry left stale error');
  if(errors.length)throw Error(errors.join('\n'));
  console.log('PASS: reconnect and successful plan retry clear their errors while preserving unrelated failures and selection/filter');
 } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exit(1)});
