// Real HTTP streaming with controlled chunk timing; all data is synthetic.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const http=require('http'),fs=require('fs'),path=require('path');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  for(const width of [1440,375])for(const saved of [false,true]){
   const home='stream-fixture',artifact='visualizations/task/notes',log='.sandbox/sandbox.2026-01-01.log';
   const make=(id,allowed,reason,recommended=false)=>({id,name:id,files:1,bytes:1024,modified:1700000000,allowed,reason,recommended,samples:[id]});
   const logEntry=make(log,true,'old_log',true),artifactEntry=make(artifact,true,'artifact');
   const initial={home,days:7,entries:[],directories:[{name:'.sandbox',pending:true,files:0,bytes:0,issues:0},{name:'visualizations',pending:true,files:0,bytes:0,issues:0}],bytes:0,complete:false,scan:{path:'',files:0}};
   const partial={...initial,snapshot:'fixture-snapshot',entries:[make(log,false,'scanning')],directories:[{name:'.sandbox',pending:false,files:1,bytes:1024,issues:0},initial.directories[1]],bytes:1024,scan:{path:'visualizations',files:1}};
   const final={...partial,complete:true,entries:[logEntry,artifactEntry],directories:partial.directories.map(folder=>({...folder,pending:false,files:1,bytes:1024})),bytes:2048,scan:{path:'',files:2}};
   let releasePartial,releaseFinal;
   const assets={'/':'index.html','/app.js':'app.js','/files.js':'files.js','/tabs.js':'tabs.js','/database.js':'database.js','/i18n.js':'i18n.js','/style.css':'style.css','/locales/en.json':'locales/en.json','/locales/zh-CN.json':'locales/zh-CN.json'};
   const server=http.createServer((request,response)=>{
    const url=new URL(request.url,'http://localhost');
    const json=data=>{response.setHeader('Content-Type','application/json');response.end(JSON.stringify(data));};
    if(url.pathname==='/api/state')return json({csrf:'test',home,rows:[],complete:true,generation:1,status:'扫描完成',source:'fixture',error:'',cli:{available:true,message:'已验证',version:'fixture'},diagnostics:[],diagnostic_count:0});
    if(url.pathname.endsWith('-progress'))return json({running:false});
    if(url.pathname==='/api/files-inspect'){
     response.setHeader('Content-Type','application/x-ndjson; charset=utf-8');response.write(JSON.stringify(initial)+'\n');
     releasePartial=()=>response.write(JSON.stringify(partial)+'\n');releaseFinal=()=>response.end(JSON.stringify(final)+'\n');return;
    }
    if(url.pathname==='/api/files-list')return json({id:log,token:'preview-token',total:1,matched:1,offset:0,next:null,items:[{path:log,bytes:1024,modified:1700000000,kind:'text'}]});
    if(url.pathname==='/api/files-preview')return json({path:log,bytes:1024,modified:1700000000,kind:'text',text:'Preview while the scan is still running'});
    const asset=assets[url.pathname];if(asset){response.setHeader('Content-Type',asset.endsWith('.js')?'text/javascript':asset.endsWith('.css')?'text/css':asset.endsWith('.json')?'application/json':'text/html');response.end(fs.readFileSync(path.join(__dirname,'../web',asset)));return;}
    response.statusCode=404;json({error:'Unknown fixture endpoint'});
   });
   await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
   const page=await browser.newPage({viewport:{width,height:844}}),errors=[];page.on('pageerror',error=>errors.push(error.message));
   try{
    await page.addInitScript(({home,artifact,saved})=>{localStorage.setItem('cleaner.language','zh-CN');if(saved)localStorage.setItem('cleaner.files:'+home,JSON.stringify({chosen:[artifact],grouped:true,closedFolders:[],days:'7',search:'',filter:'all'}));},{home,artifact,saved});
    await page.goto('http://127.0.0.1:'+server.address().port);await page.evaluate(()=>I18N.ready);await page.locator('#filesTab').click();
    await page.locator('#filesNavItems [data-folder="visualizations"]').waitFor();
    if(!await page.locator('.files-skeleton').first().isVisible()||!await page.locator('#filesLoading').isVisible())throw Error('Initial scan shows a blank pane');
    if(!(await page.locator('#filesNavItems [data-folder="visualizations"]').innerText()).includes('检查中'))throw Error('Pending directory is not identified');
    releasePartial();await page.locator('.file-entry').waitFor();
    if(!await page.locator('.file-entry input').isDisabled()||!await page.locator('#filesReview').isDisabled())throw Error('Incomplete checks enabled deletion');
    if(!(await page.locator('#filesScanText').innerText()).includes('visualizations'))throw Error('Scan progress path missing');
    if(saved&&!(await page.evaluate(home=>JSON.parse(localStorage.getItem('cleaner.files:'+home)).chosen,home)).includes(artifact))throw Error('Partial results discarded saved selection');
    await page.screenshot({path:'.investigation/files-stream-pending-'+(width>800?'desktop':'mobile')+'.png'});
    await page.locator('.file-entry .file-view').click();await page.locator('#fileContentText').waitFor({state:'visible'});
    const close=page.locator('#fileBrowserClose');
    if((await close.textContent()).trim()!=='×'||await close.getAttribute('aria-label')!=='关闭')throw Error('Close is not an accessible X icon');
    const button=await close.boundingBox(),header=await page.locator('.file-browser-header').boundingBox();
    if(button.y+button.height>header.y+header.height||header.x+header.width-button.x-button.width>28)throw Error('Close is not at the upper right');
    await close.click();releaseFinal();await page.locator('#filesLoading').waitFor({state:'hidden'});await page.locator('.file-entry').nth(1).waitFor();
    const selected=page.locator(`.file-entry[data-file-id="${saved?artifact:log}"] input`);
    if(!await selected.isChecked())throw Error('Final scan failed to preserve or auto-select items');
    const unselected=page.locator(`.file-entry[data-file-id="${saved?log:artifact}"] input`);
    if(await unselected.isChecked())throw Error('Final scan changed the requested selection');
    await page.screenshot({path:'.investigation/files-stream-'+(width>800?'desktop':'mobile')+'.png'});
    if(errors.length)throw Error(errors.join('\n'));
   }finally{await page.close();server.closeAllConnections?.();await new Promise(resolve=>server.close(resolve));}
  }
  console.log('PASS: early directory inventory, scan skeleton/progress, partial rows and previews, accessible upper-right X, final recommendations and saved selections on desktop/mobile');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1)});
