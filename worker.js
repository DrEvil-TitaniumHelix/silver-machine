"use strict";
importScripts('storage.js');
let pyodide, runner, application, requests, checkpoint, info, serial = Promise.resolve(), mounted = false;
let savedDigest, build, runtimeStart, stateReady = false, imported = false;
let assetSequence=0, selections={}, assetRoots={};
const waits = new Map(), tasks = new Map();
const hex = data => [...new Uint8Array(data)].map(b=>b.toString(16).padStart(2,'0')).join('');
const bytes = proxy => {const result=new Uint8Array(proxy.toJs());proxy.destroy();return result;};
const bridge = {
  wait(token, timeout) {
    if(waits.has(token)) throw Error('Concurrent wait on one decision queue');
    return new Promise(resolve=>{
      const timer = timeout == null ? null : setTimeout(()=>{waits.delete(token);resolve(false);},timeout*1000);
      waits.set(token,{resolve,timer});
    });
  },
  wake(token) {
    const waiting=waits.get(token);
    if(!waiting)return;
    waits.delete(token);clearTimeout(waiting.timer);
    // Let incoming keyboard messages interrupt long rest/AI sequences.
    setTimeout(()=>waiting.resolve(true),0);
  },
  spawn(token) {
    const task=new Promise((resolve,reject)=>setTimeout(async()=>{
      try {await runner.callPromising(token);resolve();}
      catch(error){reject(error);}
    },0));
    // Keep task Promises in JS. Passing one through Python and back turns it
    // into a borrowed PyodideFuture proxy whose lifetime ends during join.
    tasks.set(token,task);return token;
  },
  async join(token, timeout) {
    const task=tasks.get(token);
    if(!task)return true;
    let timer;
    try{
      const done=timeout==null?(await task,true):await Promise.race([task.then(()=>true),new Promise(resolve=>{timer=setTimeout(()=>resolve(false),timeout*1000);})]);
      if(done)tasks.delete(token);return done;
    }
    finally{clearTimeout(timer);}
  }
};
async function persist() {
  const archive=bytes(await checkpoint.callPromising());
  const digest=hex(await crypto.subtle.digest('SHA-256',archive));
  if(digest!==savedDigest){await saveStore.put(archive);savedDigest=digest;}
  return archive;
}
function folderLabels(value){
  value.browser_folders={dqk:selections.dqk?.label||'',mods:selections.mods?.label||''};
  return value;
}
function removeTree(root){
  if(!root?.startsWith('/assets/'))return;
  for(const name of pyodide.FS.readdir(root)){
    if(name==='.'||name==='..')continue;
    const path=root+'/'+name;
    if(pyodide.FS.isDir(pyodide.FS.stat(path).mode))removeTree(path);else pyodide.FS.unlink(path);
  }
  pyodide.FS.rmdir(root);
}
async function prepareAssets(kind,files){
  const catalog=new Map();
  for(const item of files){
    if(typeof item.path!=='string'||item.path.includes('\\')||item.path.split('/').some(p=>!p||p==='.'||p==='..'))throw Error('Invalid folder path');
    const key=kind==='dqk'?item.path.toUpperCase():item.path;
    if(catalog.has(key))throw Error('Duplicate file path; choose one folder');
    catalog.set(key,item);
  }
  let chosen,label;
  if(kind==='dqk'){
    const roots=[...catalog.keys()].filter(p=>p.endsWith('/DISK1/GAME.FON')).map(p=>p.slice(0,-'DISK1/GAME.FON'.length));
    if(roots.length!==1)throw Error('Choose one Dark Queen folder containing DISK1 and DISK3.');
    const root=roots[0],required=['DISK1/GAME.FON','DISK1/ALWAYS.TLB','DISK3/FRAME.TLB'];
    if(required.some(p=>!catalog.has(root+p)))throw Error('Dark Queen copy needs GAME.FON, ALWAYS.TLB and FRAME.TLB in DISK1/DISK3.');
    label=catalog.get(root+required[0]).path.slice(0,-('DISK1/GAME.FON'.length+1)).split('/').pop();
    if(catalog.has(root+'DQK.EXE'))required.push('DQK.EXE');
    chosen=required.map(path=>({file:catalog.get(root+path).file,path}));
  }else{
    const indexes=[...catalog.values()].filter(x=>x.path.split('/').pop()==='mods.json');
    if(indexes.length!==1)throw Error('Choose one Mods folder containing mods.json and its PNG files.');
    const index=indexes[0],prefix=index.path.slice(0,-'mods.json'.length);
    if(index.file.size>1024*1024)throw Error('Mods index exceeds 1 MiB');
    const entries=JSON.parse(await index.file.text());
    if(!Array.isArray(entries)||entries.length>4096)throw Error('Expected a list of at most 4096 mods');
    const paths=new Set(['mods.json']);
    for(const entry of entries){
      const png=entry?.png;
      if(typeof png!=='string'||/[\\:]/.test(png)||png.split('/').some(p=>!p||p==='.'||p==='..')||!png.toLowerCase().endsWith('.png'))
        throw Error('Use relative PNG paths inside the selected Mods folder.');
      if(!catalog.has(prefix+png))throw Error('Missing mod PNG: '+png+'. Include it inside the Mods folder.');
      paths.add(png);
    }
    label=prefix.slice(0,-1).split('/').pop()||'Mods';
    chosen=[...paths].map(path=>({file:catalog.get(prefix+path).file,path}));
  }
  if(chosen.some(x=>x.file.size>16*1024*1024)||chosen.reduce((n,x)=>n+x.file.size,0)>64*1024*1024)throw Error('Selected assets exceed the 16 MiB file or 64 MiB folder limit.');
  return {label,files:chosen};
}
async function mountAssets(kind,selection){
  const root=selection?'/assets/'+kind+'-'+(++assetSequence):'';
  try{
    if(selection)for(const {file,path} of selection.files){
      const target=root+'/'+path;pyodide.FS.mkdirTree(target.slice(0,target.lastIndexOf('/')));
      pyodide.FS.writeFile(target,new Uint8Array(await file.arrayBuffer()));
    }
    const result=JSON.parse(await requests.callPromising(kind==='dqk'?'/dqk-intake':'/preferences','POST',JSON.stringify(kind==='dqk'?{folder:root}:{mods_folder:root}),build));
    if(result.status>=400)throw Error(result.body.message||result.body.error||'Could not apply folder');
  }catch(error){if(root&&pyodide.FS.analyzePath(root).exists)removeTree(root);throw error;}
  const previous=assetRoots[kind];assetRoots[kind]=root;selections[kind]=selection;
  if(previous)removeTree(previous);
  return folderLabels(JSON.parse(await requests.callPromising('/preferences','GET','',build)).body);
}
async function boot() {
  if(typeof WebAssembly.Suspending!=='function'||typeof WebAssembly.promising!=='function')
    throw Error('This browser cannot suspend the game. Use a current Chrome or Edge.');
  runtimeStart=performance.now();
  const manifest=await (await fetch('build.json')).json(); build=manifest.build;
  importScripts('runtime/pyodide.js');
  pyodide=await loadPyodide({indexURL:'runtime/',fullStdLib:false});
  pyodide.unpackArchive(new Uint8Array(await (await fetch('engine.zip')).arrayBuffer()),'zip',{extractDir:'/code'});
  pyodide.registerJsModule('sm_browser_bridge',bridge);
  pyodide.runPython("import os,sys,json; sys.path.insert(0,'/code'); sys.dont_write_bytecode=True; os.environ.update(SM_SECRET='/content',SM_SAVE_ROOT='/saves',SM_CONFIG_HOME='/config')");
  pyodide.FS.mkdirTree('/saves');pyodide.FS.mkdirTree('/config');
  pyodide.runPython("from sm.web.session import install,run_worker; install(); from sm.web.saves import restore; from sm.web.api import Application; import threading\ndef forbidden_thread(*a,**k):\n raise AssertionError('Python thread attempted')\nthreading.Thread.start=forbidden_thread");
  runner=pyodide.globals.get('run_worker');
  const saved=await saveStore.get();
  if(saved){
    pyodide.globals.set('_restore_bytes',saved.archive);
    pyodide.runPython("restore(bytes(_restore_bytes),'/saves','/config'); del _restore_bytes");
    savedDigest=hex(await crypto.subtle.digest('SHA-256',saved.archive));
  }
  stateReady=true;
  return {build,pyodide:pyodide.version,worker:true,jspi:true,boot_ms:performance.now()-runtimeStart,
    saved:!!saved,download_bytes:manifest.bytes,python:pyodide.runPython('sys.version')};
}
async function mount(data) {
  if(!stateReady||mounted)throw Error('Reload to choose a different copy');
  const catalog=JSON.parse(pyodide.FS.readFile('/code/sm/titles/ssb/supported_versions.json',{encoding:'utf8'}));
  const wanted=new Set(catalog.versions.flatMap(v=>Object.keys(v.files)));
  const groups=new Map();
  for(const {file,path} of data.files){
    if(path.split('/').some(p=>p==='..'||p==='.'||!p)||path.includes('\\'))throw Error('Invalid folder selection');
    const at=path.lastIndexOf('/'),parent=path.slice(0,at+1),name=path.slice(at+1).toUpperCase();
    if(!wanted.has(name))continue;
    if(!groups.has(parent))groups.set(parent,new Map());
    if(groups.get(parent).has(name))throw Error('Duplicate content filename; choose one game folder');
    groups.get(parent).set(name,file);
  }
  const candidates=[...groups.values()].filter(g=>catalog.versions.some(v=>Object.keys(v.files).every(n=>g.has(n))));
  if(candidates.length!==1)throw Error('Choose exactly one complete GOG or Collector’s CD game folder');
  const start=performance.now(); let total=0;
  pyodide.FS.mkdirTree('/content');
  for(const [name,file] of candidates[0]){
    const data=new Uint8Array(await file.arrayBuffer());total+=data.byteLength;
    pyodide.FS.writeFile('/content/'+name,data);
  }
  const inspection=JSON.parse(pyodide.runPython("json.dumps(__import__('sm.titles.ssb.intake',fromlist=['inspect_folder']).inspect_folder('/content'))"));
  if(!inspection.ok){
    for(const name of pyodide.FS.readdir('/content'))if(name!=='.'&&name!=='..')pyodide.FS.unlink('/content/'+name);
    throw Error(inspection.message);
  }
  pyodide.globals.set('_build',build);pyodide.globals.set('_book',JSON.stringify(data.book));
  pyodide.runPython("application=Application(_build,json.loads(_book)); del _build,_book");
  application=pyodide.globals.get('application');requests=application.request;checkpoint=application.checkpoint;info=application.info;
  const remembered=await saveStore.read('assets')||{};
  for(const kind of ['dqk','mods'])await mountAssets(kind,remembered[kind]||null);
  await persist();
  mounted=true;
  return {edition:inspection.version_id,label:inspection.version,files:candidates[0].size,bytes:total,intake_ms:performance.now()-start,...JSON.parse(info())};
}
async function dispatch(data, fast=false) {
  if(data.type==='boot')return boot();
  if(data.type==='mount')return mount(data);
  if(!mounted)throw Error('Choose your game folder first');
  if(data.type==='assets'){
    if(!['dqk','mods'].includes(data.kind))throw Error('Unknown asset folder');
    const selection=data.files===null?null:await prepareAssets(data.kind,data.files);
    const result=await mountAssets(data.kind,selection);
    await saveStore.write('assets',selections);await persist();
    result.message=selection?(data.kind==='dqk'?result.dqk_copy.message:'Mods verified.')+' Saved in this browser.':'Folder pick cleared.';
    return result;
  }
  if(data.type==='start'){
    const start=performance.now();
    const result=await application.start.callPromising(!!data.resume);
    const value=result.toJs({dict_converter:Object.fromEntries});result.destroy();
    return {...value,start_ms:performance.now()-start,...JSON.parse(info())};
  }
  if(data.type==='info')return JSON.parse(info());
  if(data.type==='export')return {archive:bytes(await checkpoint.callPromising())};
  if(data.type==='import'){
    pyodide.globals.set('_restore_bytes',data.archive);
    pyodide.runPython("from sm.web.saves import validate,entries; validate(entries(bytes(_restore_bytes))); None");
    await saveStore.put(data.archive);
    imported=true;await application.close.callPromising();
    return {imported:true};
  }
  if(data.type==='rpc'){
    // The page reloads after import. Freeze queued old-game polling until this
    // worker is terminated, so it cannot overwrite imported saves or flash errors.
    if(imported)return new Promise(()=>{});
    const wasRest=application.interruptible();
    const result=JSON.parse(await requests.callPromising(data.path,data.method||'GET',data.body||'',data.build||build));
    if(result.body?.options)folderLabels(result.body);
    if(!fast&&result.status<400&&((data.method||'GET')==='POST'||wasRest)){
      await persist();
      result.persisted=true;
    }
    if(result.kind==='application/octet-stream')result.body=new Uint8Array(result.body);
    return result;
  }
  throw Error('Unknown worker message');
}
function respond(data, fast=false){
  return dispatch(data,fast).then(value=>postMessage({id:data.id,ok:true,value}),error=>{
    if(data.type!=='assets')console.error(error.stack||String(error));
    postMessage({id:data.id,ok:false,error:String(error)});
  });
}
self.onmessage=({data})=>{
  // Only the original rest-input FIFO path can bypass a pending frame request.
  if(application&&data.type==='rpc'&&data.path==='/key'&&data.method==='POST'&&application.interruptible()){
    try{if(!('revision' in JSON.parse(data.body))){void respond(data,true);return;}}catch{}
  }
  serial=serial.then(()=>respond(data));
};
