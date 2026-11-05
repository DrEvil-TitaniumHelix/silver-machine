"use strict";
importScripts('storage.js');
let pyodide, runner, application, requests, checkpoint, info, serial = Promise.resolve(), mounted = false;
let savedDigest, build, runtimeStart, stateReady = false, imported = false;
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
  mounted=true;
  return {edition:inspection.version_id,label:inspection.version,files:candidates[0].size,bytes:total,intake_ms:performance.now()-start,...JSON.parse(info())};
}
async function dispatch(data, fast=false) {
  if(data.type==='boot')return boot();
  if(data.type==='mount')return mount(data);
  if(!mounted)throw Error('Choose your game folder first');
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
    console.error(error.stack||String(error));
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
