// Development-only browser check against the local web assets; all API data is mocked.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try {
  const page=await browser.newPage({viewport:{width:1280,height:900}});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/api/state',route=>route.fulfill({json:{csrf:'test',rows:[],spawn_edges:{},complete:true,generation:1,status:'扫描完成',source:'fixture',cli:{available:false,lock_verified:false,message:'正在检测 CLI',version:'',path:''},diagnostics:[],diagnostic_count:0,home:'fixture'}}));
  await page.route('**/api/delete-progress',route=>route.fulfill({json:{running:false}}));
  await page.goto(process.env.CLEANER_URL || 'http://127.0.0.1:8766');
  await page.evaluate(()=>I18N.ready);
  await page.waitForFunction(()=>Boolean(state));
  await page.locator('#language').selectOption('zh-CN');
  if(await page.locator('#cliState').textContent()!=='CLI 检测中')throw Error('Checking status');
  if(await page.locator('#cliNotice').isVisible())throw Error('Pending validation displayed as a failure');
  await page.evaluate(()=>{
   state.cli={available:true,lock_verified:true,version:'codex-cli future-version',path:'C:\\codex.exe',message:'删除能力与会话锁检测已验证'};
   renderCliStatus();
  });
  if(await page.locator('#cliState').textContent()!=='CLI 可用 · 会话锁已验证')throw Error('Verified status');
  if(await page.locator('#cliNotice').isVisible())throw Error('Verified notice remains visible');
  await page.locator('#language').selectOption('en');
  if(await page.locator('#cliState').textContent()!=='CLI ready · Session locks verified')throw Error('Verified status translation');
  if(!(await page.locator('#cliState').getAttribute('title')).includes('Deletion capability and session lock detection verified'))throw Error('Verified tooltip translation');
  await page.evaluate(()=>{
   state.cli.available=false;state.cli.lock_verified=false;
   state.cli.message='只读：CLI 会话锁验证失败，删除已禁用。CLI 未保护持有写入锁的临时会话';
   renderCliStatus();
  });
  if(!(await page.locator('#cliState').textContent()).includes('verification failed'))throw Error('Failed status translation');
  if(!(await page.locator('#cliNotice').innerText()).includes('The CLI did not protect the temporary session'))throw Error('Failure detail translation');
  await page.locator('#language').selectOption('zh-CN');
  if(!(await page.locator('#cliNotice').innerText()).includes('CLI 未保护持有写入锁的临时会话'))throw Error('Failure notice switch back');
  await page.setViewportSize({width:600,height:850});
  if(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth))throw Error('Status notice overflows viewport');
  await page.evaluate(()=>{
   state.cli={available:false,lock_verified:false,version:'',path:'',message:'只读：未找到可用 CLI。请指定桌面版 codex.exe，或加入 PATH。'};
   renderCliStatus();
  });
  if(await page.locator('#cliState').textContent()!=='CLI 只读 · 未找到兼容 CLI')throw Error('Unavailable status');
  if(!await page.locator('#cliNotice').isVisible())throw Error('Missing CLI reason hidden');
  if(errors.length)throw Error(errors.join('\n'));
  console.log('PASS: checking, verified, failed and missing CLI states; Chinese/English details; narrow viewport');
 } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exit(1)});
