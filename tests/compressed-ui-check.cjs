// Mocked session data only; no real cleanup endpoints are used.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await browser.newPage(),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  const base={project:'fixture',cwd:'fixture',updated_at:1,kind:'main',issues:[],activity:{code:'idle'},state:'普通',missing_files:[]};
  const packed={...base,id:'compressed-session',title:'压缩后仍有数据',size:4096,reclaimable:4096,file_count:1,compressed_file_count:1};
  const missing={...base,id:'missing-session',title:'真正缺失',size:0,reclaimable:0,file_count:0,missing_files:['sessions/missing.jsonl']};
  let planned;
  await page.route('**/api/**',route=>{
   const path=new URL(route.request().url()).pathname;
   if(path==='/api/state')return route.fulfill({json:{csrf:'fixture',home:'fixture-compressed',rows:[packed,missing],complete:true,generation:1,status:'扫描完成',source:'fixture',error:'',cli:{available:true,message:'fixture',path:'fixture',version:'fixture'},diagnostics:[],diagnostic_count:0}});
   if(path==='/api/plan'){
    planned=route.request().postDataJSON();
    return route.fulfill({json:{token:'fixture',allowed:true,bytes:4096,blockers:[],entries:[{id:packed.id,title:packed.title,files:[{path:'sessions/fixture.jsonl.zst',size:4096,compressed:true}],bytes:4096,blockers:[]}]}});
   }
   return route.fulfill({json:{running:false}});
  });
  await page.goto(process.env.CLEANER_URL || 'http://127.0.0.1:18766');await page.evaluate(()=>I18N.ready);
  await page.locator('#language').selectOption('zh-CN');await page.locator('.session-row').first().waitFor();
  const compressedRow=page.locator('.session-row').filter({hasText:packed.title});
  if(!(await compressedRow.innerText()).includes('含 1 个压缩日志')||!(await compressedRow.innerText()).includes('4.00 KiB'))throw Error('Compressed data has no count or stored size');
  await page.locator('#fileStatus').selectOption('allMissing');
  if(await page.locator('.session-row').count()!==1||!(await page.locator('.session-row').innerText()).includes(missing.title))throw Error('Compressed data included in all-missing filter');
  await page.locator('#selectAll').check();
  if(JSON.stringify(await page.evaluate(()=>[...selected]))!==JSON.stringify([missing.id]))throw Error('All-missing bulk selection includes compressed session');
  await page.locator('#selectAll').uncheck();await page.locator('#fileStatus').selectOption('');
  await compressedRow.locator('input').check();await page.locator('#plan').click();await page.locator('#planDialog').waitFor({state:'visible'});
  const planText=await page.locator('#planBody').innerText();
  if(!planText.includes('1 个关联文件 · 4.00 KiB')||!planText.includes('压缩日志仍包含会话数据'))throw Error('Plan does not disclose compressed session data');
  if(planned.ids.length!==1||planned.ids[0]!==packed.id)throw Error('Wrong plan selection');
  await page.evaluate(()=>I18N.setLanguage('en'));
  if(!(await page.locator('#planBody').innerText()).includes('Compressed logs still contain session data'))throw Error('Compressed plan note is not localized');
  if(errors.length)throw Error(errors.join('\n'));
  console.log('PASS: compressed size/count, exclusion from missing-file bulk selection, explicit deletion-plan warning and localization');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
