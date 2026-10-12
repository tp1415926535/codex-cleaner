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
  await page.goto(process.env.CLEANER_URL || 'http://127.0.0.1:8766');
  await page.evaluate(()=>I18N.ready);
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
  if(errors.length)throw Error(errors.join('\n'));
  console.log('PASS: automatic reconnect clears fetch error, preserves selection/filter, retains operation errors and resolves scan errors');
 } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exit(1)});
