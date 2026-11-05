"use strict";
const byId=id=>document.getElementById(id);
const state=window.smDemo={frames:0,ready:false,playing:false,events:[]};
const status=byId('status'),worker=new Worker('worker.js'),pending=new Map();
let sequence=0,pdfURL=null,build,selected=false,hasLock=false;
function notice(text,error=false){status.textContent=text;status.classList.toggle('error',error);}
function call(type,fields={}){
  return new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});worker.postMessage({id,type,...fields});});
}
worker.onmessage=({data})=>{
  const task=pending.get(data.id);if(!task)return;pending.delete(data.id);
  data.ok?task.resolve(data.value):task.reject(Error(data.error));
};
worker.onerror=event=>{for(const task of pending.values())task.reject(Error(event.message));pending.clear();notice('The game stopped. Reload this page to restore your saved progress.',true);};
window.smTransport={
  async request(path,options={}){
    if(options.signal?.aborted)throw options.signal.reason;
    const value=await call('rpc',{path,method:options.method||'GET',body:options.body||'',build:options.headers?.['X-SM-Build']||build});
    if(value.persisted)notice('Saved in this browser.');
    return new Response(value.kind==='application/octet-stream'?value.body:JSON.stringify(value.body),{status:value.status,headers:{'Content-Type':value.kind,...(value.overlay?{'X-SM-Overlay':value.overlay}:{})}});
  },
  assetURL:path=>path==='/journal.pdf'?pdfURL:null,
  folders:{connect:connectFolder},
  onFrame:layout=>{state.frames++;state.layout=layout;},
  onError:error=>notice('The game stopped: '+error.message+'. Export your saves or reload to resume.',true),
  onQuit:()=>notice('Game closed. Your last safe progress is saved in this browser. Reload to resume.')
};
async function filesFromHandle(handle,prefix=''){
  if(handle.kind==='file')return [{file:await handle.getFile(),path:prefix+handle.name}];
  const result=[];
  for await(const child of handle.values())result.push(...await filesFromHandle(child,prefix+handle.name+'/'));
  return result;
}
async function filesFromEntry(entry,prefix=''){
  if(entry.isFile)return [{file:await new Promise((yes,no)=>entry.file(yes,no)),path:prefix+entry.name}];
  const result=[],reader=entry.createReader();
  while(true){const batch=await new Promise((yes,no)=>reader.readEntries(yes,no));if(!batch.length)break;for(const child of batch)result.push(...await filesFromEntry(child,prefix+entry.name+'/'));}
  return result;
}
function connectFolder({kind,folder,browse,apply,clear,message,refresh,enable}){
  folder.readOnly=true;folder.placeholder='No folder selected';browse.textContent='Choose folder…';apply.hidden=true;
  const doc=folder.ownerDocument,drop=doc.createElement('div'),compat=doc.createElement('input');
  drop.id=kind+'-drop';drop.className='browser-folder-drop';drop.tabIndex=0;
  drop.textContent=`Drag your ${kind==='dqk'?'Dark Queen':'Mods'} folder here (from Explorer or Finder)`;
  const note=doc.createElement('p');note.className='meta';
  note.textContent='Files stay in this browser, including after reload. Nothing uploads. Clear removes this pick.';
  folder.parentElement.before(drop);folder.parentElement.after(note);
  compat.type='file';compat.webkitdirectory=true;compat.multiple=true;compat.hidden=true;compat.id=kind+'-compatibility';note.after(compat);
  const failed=new Set();const failure=path=>{failed.add(path);if(failed.size===2)compat.hidden=false;};
  async function choose(files){
    if(browse.disabled)return;
    enable(true);message.textContent='Checking local files…';
    try{const next=await call('assets',{kind,files});refresh(next);message.textContent=next.message;}
    catch(error){message.textContent=error.message;}
    finally{enable();}
  }
  browse.onclick=async()=>{
    if(!window.showDirectoryPicker){compat.hidden=false;compat.click();return;}
    try{await choose(await filesFromHandle(await showDirectoryPicker({mode:'read'})));}
    catch(error){message.textContent='This dialog cannot open Program Files, where GOG installs. Drag the folder here instead.';failure('choose');}
  };
  compat.onchange=()=>void choose([...compat.files].map(file=>({file,path:file.webkitRelativePath||file.name})));
  drop.ondragover=event=>{event.preventDefault();drop.classList.add('over');};
  drop.ondragleave=()=>drop.classList.remove('over');
  drop.ondrop=event=>{
    event.preventDefault();drop.classList.remove('over');
    if(browse.disabled){message.textContent='Choose VGA to enable Mods, or wait for the current check.';return;}
    // Capture legacy entries while the drop is live; Program Files refuses the handle API.
    const work=[...event.dataTransfer.items].filter(i=>i.kind==='file').map(item=>{
      const entry=item.webkitGetAsEntry?.(),file=entry?null:item.getAsFile();
      return entry?filesFromEntry(entry):Promise.resolve(file?[{file,path:file.name}]:[]);
    });
    void Promise.all(work).then(groups=>choose(groups.flat())).catch(error=>{message.textContent=error.message;failure('drop');});
  };
  clear.onclick=()=>void choose(null);
  if(kind==='mods')note.textContent+=' Use relative PNG paths inside this folder in mods.json.';
}
async function select(files){
  if(selected||!state.ready||!hasLock)return;
  byId('choose').disabled=byId('folder').disabled=true;
  notice('Checking your game files. Nothing is uploaded.');
  try{
    const pdfs=files.filter(x=>x.file.name.toLowerCase()==='adventurers journal.pdf');
    let book={available:false,mapped:false};
    if(pdfs.length===1&&pdfs[0].file.size<=128*1024*1024){
      const file=pdfs[0].file,digest=await crypto.subtle.digest('SHA-256',await file.arrayBuffer());
      const hash=[...new Uint8Array(digest)].map(b=>b.toString(16).padStart(2,'0')).join('');
      book={available:true,mapped:hash==='f26c90627c1cdb2dfacf92ad3f795545a659c7b8c6d0f44a8996f8f3a9a48a74',file:file.name};
      if(pdfURL)URL.revokeObjectURL(pdfURL);pdfURL=URL.createObjectURL(file);
    }
    const result=await call('mount',{files,book});state.intake=result;selected=true;
    byId('welcome').hidden=true;byId('start-options').hidden=false;byId('resume').hidden=!result.resume;
    byId('copy').textContent=result.edition==='gog'?'GOG copy verified.':'Collector’s CD copy verified.';
    notice(result.resume?'Your saved game is ready. Resume it, or create a new party.':'Your copy is verified. Create a party to begin.');
  }catch(error){notice(error.message,true);byId('choose').disabled=byId('folder').disabled=false;}
}
async function start(resume){
  byId('resume').disabled=byId('new-game').disabled=true;
  notice(resume?'Restoring your saved game…':'Starting a new party…');
  try{
    state.start=await call('start',{resume});state.playing=true;
    byId('start-options').hidden=true;byId('playing').hidden=false;byId('plus-tile').hidden=false;
    const script=document.createElement('script');script.src='app.js';document.head.append(script);
    notice('Ready. Use the highlighted keys or click the game commands. F10 opens Save and Load.');
    void navigator.storage?.persist?.();
  }catch(error){notice(error.message,true);byId('resume').disabled=byId('new-game').disabled=false;}
}
state.closePlus=()=>{byId('plus-view').hidden=true;byId('playing').hidden=false;window.dispatchEvent(new Event('resize'));document.querySelector('canvas').focus();};
state.openPlus=(entry='')=>{
  byId('playing').hidden=true;byId('plus-view').hidden=false;
  byId('plus-frame').src='plus.html'+(entry?'?entry='+encodeURIComponent(entry)+'#journal':'');
};
state.info=()=>call('info');
document.addEventListener('click',event=>{
  const a=event.target.closest('a');if(a?.getAttribute('href')?.startsWith('/plus')){
    event.preventDefault();state.openPlus(new URL(a.href).searchParams.get('entry')||'');
  }
});
const failures=new Set();
function failed(path){failures.add(path);if(failures.size===2)byId('compatibility').hidden=false;}
byId('choose').onclick=async()=>{
  if(!window.showDirectoryPicker){byId('compatibility').hidden=false;byId('folder').click();return;}
  try{await select(await filesFromHandle(await showDirectoryPicker({mode:'read'})));}
  // Chrome reports a refused system folder (Program Files) and a cancel the same way.
  catch(error){
    notice('This dialog cannot open Program Files, where GOG installs. Drag the folder here instead.');
    failed('choose');
  }
};
byId('folder').onchange=()=>void select([...byId('folder').files].map(file=>({file,path:file.webkitRelativePath||file.name})));
const drop=byId('drop-zone');
drop.ondragover=event=>{event.preventDefault();drop.classList.add('over');};
drop.ondragleave=()=>drop.classList.remove('over');
drop.ondrop=event=>{
  event.preventDefault();drop.classList.remove('over');
  const items=[...event.dataTransfer.items].filter(i=>i.kind==='file');
  // Entries, not getAsFileSystemHandle: the handle API refuses Program Files. Capture them before awaiting any traversal.
  const work=items.map(item=>{const entry=item.webkitGetAsEntry?.();return entry?filesFromEntry(entry):Promise.resolve([{file:item.getAsFile(),path:item.getAsFile().name}]);});
  void Promise.all(work).then(groups=>select(groups.flat())).catch(error=>{notice(error.message,true);failed('drop');});
};
byId('resume').onclick=()=>void start(true);byId('new-game').onclick=()=>void start(false);
byId('plus-tile').onclick=()=>state.openPlus();byId('close-plus').onclick=state.closePlus;
byId('restart').onclick=()=>location.reload();
byId('export-save').onclick=async()=>{
  try{const {archive}=await call('export');const url=URL.createObjectURL(new Blob([archive],{type:'application/zip'}));
    const a=document.createElement('a');a.href=url;a.download='silvermachine-saves.zip';a.click();setTimeout(()=>URL.revokeObjectURL(url),60000);
    notice('Save file exported. Keep it as your backup.');
  }catch(error){notice('Could not export: '+error.message,true);}
};
byId('import-save').onchange=async()=>{
  const file=byId('import-save').files[0];if(!file)return;
  if(file.size>32*1024*1024){notice('Save file is too large.',true);return;}
  try{await call('import',{archive:new Uint8Array(await file.arrayBuffer())});location.reload();}
  catch(error){notice('Import failed: '+error.message,true);}
  finally{byId('import-save').value='';}
};
window.addEventListener('pagehide',()=>{worker.terminate();if(pdfURL)URL.revokeObjectURL(pdfURL);});
async function init(){
  try{
    if(!navigator.locks)throw Error('Use a current Chrome or Edge to keep saves safe between tabs.');
    await new Promise((resolve,reject)=>{
      void navigator.locks.request('silvermachine-active-game',{ifAvailable:true},async lock=>{
        if(!lock){reject(Error('Another tab has SilverMachine open. Close it before starting here.'));return;}
        hasLock=true;resolve();await new Promise(()=>{});
      });
    });
    const timeout=setTimeout(()=>{
      const error=Error('Runtime loading timed out. Reload the page to try again.');
      for(const task of pending.values())task.reject(error);pending.clear();worker.terminate();
    },30000);
    let ready;try{ready=await call('boot');}finally{clearTimeout(timeout);}
    state.ready=true;state.runtime=ready;build=ready.build;
    byId('choose').disabled=byId('folder').disabled=false;
    notice(ready.saved?'Saved progress found. Choose your game folder again to resume.':'Ready. Drop your game folder or choose it below.');
  }catch(error){
    state.error=error.message==='[object Object]'?'Could not load the game runtime. Reload this page to try again.':error.message;
    notice(state.error,true);
  }
}
void init();
