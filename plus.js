"use strict";
(() => {
  const transport = (...args) => window.smTransport ? window.smTransport.request(...args) : fetch(...args);
  const build = "bb4eae3bfc6de720";
  const message = document.querySelector("#message");
  const controls = {
    effect_scale: document.querySelector("#effect-scale"),
    message_hold: document.querySelector("#message-hold"),
    equipment_icon: document.querySelector("#equipment-icon"),
    look: document.querySelector("#look"),
    vga_frame: document.querySelector("#vga-frame")
  };
  let saved, dqkAvailable = false;
  async function request(path, value) {
    const response = await transport(path, {cache: "no-store", ...(path === '/browse' ? {} : {signal: AbortSignal.timeout(15000)}),
      headers: {"X-SM-Build": build, "Content-Type": "application/json"},
      ...(value === undefined ? {} : {method: "POST", body: JSON.stringify(value)})});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error === "build-mismatch" ? "The server changed. Reload this page." : result.message || result.error || "Request failed. Try again.");
    return result;
  }
  function display() {
    for (const [key, control] of Object.entries(controls)) {
      if (control.type === "checkbox") control.checked = saved[key];
      else {
        if (![...control.options].some(o => String(o.value) === String(saved[key]))) control.add(new Option(`×${saved[key]}`, saved[key]));
        control.value = String(saved[key]);
        if (key === 'vga_frame' && !dqkAvailable) control.value = 'ssb';
      }
    }
  }
  async function start() {
    try {
      let state = await request("/preferences");
      const folder = document.querySelector('#mods-folder');
      const browse = document.querySelector('#mods-browse'), apply = document.querySelector('#mods-apply'), clear = document.querySelector('#mods-clear');
      const dqkFolder = document.querySelector('#dqk-folder'), dqkMessage = document.querySelector('#dqk-message');
      const dqkBrowse = document.querySelector('#dqk-browse'), dqkApply = document.querySelector('#dqk-apply'), dqkClear = document.querySelector('#dqk-clear');
      function refresh(next) {
        state = next; saved = state.options; dqkAvailable = Boolean(state.dqk_frame);
        folder.value = state.browser_folders?.mods ?? (saved.mods_folder || '');
        dqkFolder.value = state.browser_folders?.dqk ?? (state.dqk_copy?.folder || '');
        dqkMessage.textContent = state.dqk_copy?.message || '';
        document.querySelector('#look-note').textContent = state.look_note || '';
        controls.vga_frame.querySelector('[value=dqk]').disabled = !dqkAvailable;
        controls.vga_frame.querySelector('[value=dqk]').hidden = !dqkAvailable;
        display();
      }
      function enable(busy = false) {
        for (const [key, control] of Object.entries(controls)) control.disabled = busy || !state.supported.includes(key) || key === 'vga_frame' && saved.look !== 'vga';
        for (const control of [folder, browse, apply, clear]) control.disabled = busy || !state.supported.includes('mods_folder') || saved.look !== 'vga';
        for (const control of [dqkFolder, dqkBrowse, dqkApply, dqkClear]) control.disabled = busy || !state.dqk_copy || state.dqk_copy.source !== 'settings';
      }
      async function setCopy(value) {
        enable(true); dqkMessage.textContent = value ? 'Checking Dark Queen frame and font…' : 'Clearing Dark Queen copy…';
        try { const result = await request('/dqk-intake', {folder: value}); refresh(result); dqkMessage.textContent = result.message; }
        catch (error) { dqkMessage.textContent = error.message; }
        finally { enable(); }
      }
      dqkApply.onclick = () => dqkFolder.value.trim() ? setCopy(dqkFolder.value.trim()) :
        (dqkMessage.textContent = 'Choose your Dark Queen folder first.');
      dqkClear.onclick = () => setCopy('');
      dqkBrowse.onclick = async () => {
        enable(true); dqkMessage.textContent = 'Choose your Dark Queen folder in the native folder dialog.';
        try {
          const result = await request('/browse', {});
          if (!result.cancelled && result.folder) dqkFolder.value = result.folder;
          dqkMessage.textContent = result.cancelled ? 'Cancelled. The saved copy is unchanged.' : 'Folder selected. Verify and save it to continue.';
        } catch (error) { dqkMessage.textContent = error.message; }
        finally { enable(); }
      };
      refresh(state);
      async function setFolder(value) {
        enable(true);
        try { await request('/preferences', {mods_folder: value}); saved.mods_folder = value; folder.value = value; message.textContent = value ? 'Mods folder saved.' : 'Mods cleared.'; }
        catch (error) { message.textContent = error.message; }
        finally { enable(); }
      }
      apply.onclick = () => setFolder(folder.value.trim());
      clear.onclick = () => setFolder('');
      browse.onclick = async () => {
        enable(true);
        try { const result = await request('/browse', {}); if (result.folder) await setFolder(result.folder); }
        catch (error) { message.textContent = error.message; }
        finally { enable(); }
      };
      if (window.smTransport?.folders) {
        window.smTransport.folders.connect({kind:'dqk',folder:dqkFolder,browse:dqkBrowse,apply:dqkApply,clear:dqkClear,message:dqkMessage,refresh,enable});
        window.smTransport.folders.connect({kind:'mods',folder,browse,apply,clear,message,refresh,enable});
      }
      display();
      for (const [key, control] of Object.entries(controls)) {
        control.addEventListener("change", async () => {
          const value = control.type === "checkbox" ? control.checked : ['look', 'vga_frame'].includes(key) ? control.value : Number(control.value);
          enable(true);
          try {
            await request(key === "effect_scale" ? "/speed" : "/preferences", key === "effect_scale" ? {scale: value} : {[key]: value});
            saved[key] = value;
            message.textContent = state.persistent ? "Saved." : "Applied to this session.";
          } catch (error) { display(); message.textContent = error.message; }
          finally { enable(); }
        });
      }
      enable();
      message.textContent = state.persistent ? "Settings save automatically." : state.supported.length ? "Effect time applies to this session." : "Plus settings are not available for this title yet.";
    } catch (error) { message.textContent = error.message; }
  }
  const el = (tag, text, cls) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (cls) node.className = cls;
    return node;
  };
  const button = (text, action) => { const b = el("button", text); b.type = "button"; b.onclick = action; return b; };
  const data = (tab, values = {}) => request("/plus/data?" + new URLSearchParams({tab, ...values}));
  function table(headers, rows) {
    const wrap = el("div", undefined, "scroll"), t = el("table"), head = el("thead"), tr = el("tr"), body = el("tbody");
    for (const h of headers) { const th = el("th", h); th.scope = "col"; tr.append(th); }
    head.append(tr); t.append(head, body);
    for (const row of rows) { const r = el("tr"); for (const c of row) r.append(el("td", c)); body.append(r); }
    wrap.append(t); return wrap;
  }
  function search(label, changed) {
    const input = el("input"); input.type = "search"; input.placeholder = label; input.setAttribute("aria-label", label);
    input.oninput = () => changed(input.value.toLowerCase().trim()); return input;
  }
  function source(root, text) { root.append(el("p", "Reads from: " + text, "source")); }
  function choices(root, names, render) {
    const bar = el("div", undefined, "subtabs"), body = el("div");
    names.forEach((name, i) => bar.append(button(name, () => show(i))));
    function show(i) { [...bar.children].forEach((b, j) => b.setAttribute("aria-pressed", String(i === j))); body.replaceChildren(); render(body, i); }
    root.append(bar, body); show(0);
  }
  async function mapTab(root) {
    root.append(el("h2", "Area map"));
    const info = el("p"), toolbar = el("div", undefined, "toolbar"), view = el("div", undefined, "map-viewport"), detail = el("p");
    info.setAttribute("role", "status"); view.tabIndex = 0; view.setAttribute("aria-label", "Scrollable area map");
    const zoom = el("select"); zoom.setAttribute("aria-label", "Map zoom");
    for (const scale of [.5, 1, 1.5, 2]) zoom.add(new Option(`${scale * 100}%`, scale, scale === 1, scale === 1));
    toolbar.append(button("Refresh current area", () => refresh().catch(e => { info.textContent = e.message; })), zoom);
    root.append(info, toolbar, view, detail);
    source(root, "your current GEO map and the doors opened during this visit.");
    root.append(el("p", "North is up. All 256 cells are shown. Gold arrow: party and facing. White: wall; cyan gap: open passage; red: locked door; magenta: magically locked door. Each cell side is drawn separately.", "note"));
    async function refresh() {
      const m = await data("map"); view.replaceChildren();
      if (!m.available) { info.textContent = m.message; return; }
      info.textContent = `Area ${m.area} · Party (${m.x}, ${m.y}), facing ${m.directions[m.facing / 2]} · 16 × 16`;
      const canvas = el("canvas"), ctx = canvas.getContext("2d"); canvas.width = canvas.height = 552;
      canvas.setAttribute("role", "img"); canvas.setAttribute("aria-label", info.textContent + ". Reveal-all area map."); view.append(canvas);
      ctx.fillStyle = "#0a141d"; ctx.fillRect(0, 0, 552, 552); ctx.font = "12px system-ui"; ctx.textAlign = "center";
      const unit = 32, offset = 28;
      for (let n = 0; n < 16; n++) { ctx.fillStyle = "#b6c5d3"; ctx.fillText(n, offset + n*unit + 16, 17); ctx.fillText(n, 12, offset + n*unit + 20); }
      for (const cell of m.cells) {
        const x = offset + cell.x*unit, y = offset + cell.y*unit;
        ctx.fillStyle = cell.attribute >= 128 ? "#182b42" : "#13212b"; ctx.fillRect(x+1, y+1, 30, 30);
        [[x+3,y+3,x+29,y+3],[x+29,y+3,x+29,y+29],[x+3,y+29,x+29,y+29],[x+3,y+3,x+3,y+29]].forEach((line, d) => {
          if (!cell.walls[d]) return;
          const p = cell.passages[d]; ctx.strokeStyle = ["#e8edf2", "#76d8e6", "#ff7e82", "#ed9cff"][p]; ctx.lineWidth = 2;
          ctx.setLineDash(p === 1 ? [5, 6] : []); ctx.beginPath(); ctx.moveTo(line[0], line[1]); ctx.lineTo(line[2], line[3]); ctx.stroke();
        });
      }
      ctx.setLineDash([]); ctx.save(); ctx.translate(offset + m.x*unit + 16, offset + m.y*unit + 16); ctx.rotate(m.facing * Math.PI/4);
      ctx.fillStyle = "#ffd275"; ctx.beginPath(); ctx.moveTo(0,-11); ctx.lineTo(9,9); ctx.lineTo(0,5); ctx.lineTo(-9,9); ctx.closePath(); ctx.fill(); ctx.restore();
      zoom.onchange = () => { canvas.style.width = `${552*Number(zoom.value)}px`; canvas.style.height = `${552*Number(zoom.value)}px`; }; zoom.onchange();
      canvas.onpointermove = e => { const r = canvas.getBoundingClientRect(), x = Math.floor(((e.clientX-r.left)*552/r.width-offset)/unit), y = Math.floor(((e.clientY-r.top)*552/r.height-offset)/unit);
        detail.textContent = x>=0 && y>=0 && x<16 && y<16 ? `Cell (${x}, ${y})${x===m.x&&y===m.y ? " · Party" : ""}` : ""; };
    }
    await refresh();
  }
  function helpTab(root) {
    root.append(el("h2", "Help")); source(root, "our keyboard, menu and Plus implementation; this help is written by us.");
    const sections = [
      ["Keys and focus", "Click the game to restore keyboard and mouse control. Use the highlighted menu letters or click a command. Arrow keys select rows or move in the current movement mode; Enter accepts the selected command or continues text. Escape backs out when the current menu allows it. Page Up and Page Down move through longer lists."],
      ["Exploring and combat", "Choose Move while exploring, then use the arrows to walk or turn. Area or F2 switches the native small map. In combat, choose the active character’s command and follow its target prompt. The full map in Plus shows the current area without moving the party."],
      ["Save and load", "F10 opens Save, Load, Quit and Resume. Save while exploring or in camp. Choose a letter slot; existing slots can be replaced by the normal game save flow. Loading returns to that saved game. Keep the slot name when reporting a problem."],
      ["Reading Plus", "Journal holds missions, numbered journal references and conversation history. The booklet comes from your own copy; a CD without a PDF points you to your printed journal. Rules shows our summary and your game’s tables. Gallery browses your game pictures. Guide lists possible area events and Campaign roster shows your current party and saved characters."],
      ["Plus options", "Effect time scales animation holds; ×1 is the original timing. Message hold sets service notices to 400, 800, 1200 or 2000 milliseconds; 400 is the original. Effect time also scales these holds. Icon follows readied weapon and shield changes the combat drawing only; your explicit Alter > Icon choice takes priority. The icon option starts off. Open Plus options below to change these settings."],
      ["Look and Mods", "Original is the default SSB presentation. VGA preserves SSB content and enables full-colour PNG art from your Mods folder. Its frame and font can come from your own configured Dark Queen copy; otherwise it uses SSB’s. Mods need a mods.json index mapping container and record ids to PNG paths. Switching back to Original disables mods."],
      ["Your files and bug reports", "Game folder chooses your own supported copy. Plus reads pictures and rules from that folder. Bug saves your description, save slot, version and build to a local report and offers a download you can attach yourself. Nothing is sent to a reporting service. Party transfer and a side-quest reward list are not available in this alpha."]
    ];
    const list = el("div"), input = search("Search help", q => show(q)); root.append(input, list);
    function show(q="") { list.replaceChildren(); for (const [title, text] of sections) if ((title+" "+text).toLowerCase().includes(q)) {
      const s = el("section"); s.append(el("h3", title), el("p", text)); list.append(s);
    } if (!list.children.length) list.append(el("p", "No matching help. Try fewer words.")); }
    show();
  }
  async function rulesTab(root) {
    root.append(el("h2", "Rules"));
    const r = await data("rules"); source(root, r.source);
    choices(root, ["Summary", "THAC0", "Saving throws", "Spells"], (body, view) => {
      if (view === 0) { body.append(el("h3", "Attacks, protection and magic"),
        el("p", "An attack uses a twenty-sided roll. Lower THAC0 makes a character more likely to hit; lower armor class makes the target harder to hit. Before other modifiers, the roll needed is THAC0 minus the target’s armor class. A natural 1 misses and a natural 20 hits."),
        el("p", "Saving throws test resistance to particular dangers. Their thresholds depend on class and level, with further adjustments from the character and equipment. The tables here show base values; the game applies the actual circumstances."),
        el("p", "Spell availability depends on class, level, learned spells and memorization. Rest prepares selected spells. The spell list below distinguishes spells usable in camp and in combat. These short explanations are ours; spell names and table values are read from your copy.")); return; }
      if (view === 1) { body.append(el("p", "Base THAC0 by class level, before equipment and temporary effects."), table(["Level", ...r.classes], r.attacks.map(x => [x.level,...x.values]))); return; }
      const output = el("div");
      if (view === 2) {
        const select = el("select"); select.setAttribute("aria-label", "Saving throw class"); r.classes.forEach(c => select.add(new Option(c,c)));
        const show = () => output.replaceChildren(table(["Level", "Save 1", "Save 2", "Save 3", "Save 4", "Save 5"], r.saves.filter(x=>x.class_name===select.value).map(x=>[x.level,...x.values])));
        body.append(el("p", "Base saving throw thresholds in the engine’s five table columns; temporary bonuses are excluded."), select, output); select.onchange=show; show();
      } else {
        const show = (q="") => { const rows=r.spells.filter(x=>(x.name+" "+x.class_name+" "+x.level).toLowerCase().includes(q));
          output.replaceChildren(table(["Spell", "Class", "Level", "Camp", "Combat"], rows.map(x=>[x.name,x.class_name,x.level,x.camp?"Yes":"—",x.combat?"Yes":"—"]))); };
        body.append(search("Search spells by name, class or level", show), output); show();
      }
    });
  }
  function bugTab(root) {
    root.append(el("h2", "Bug report")); source(root, "your description and this running build’s diagnostic metadata.");
    root.append(el("p", "Save a local file to attach to your report. Include the slot needed to reproduce the problem. Nothing is sent anywhere."));
    const form=el("form"), fields={};
    for (const [key,title] of [["slot","Save slot"],["steps","Steps to reproduce"],["expected","What you expected"],["actual","What happened"]]) {
      const label=el("label",title), input=el(key==="slot"?"input":"textarea"); input.id="bug-"+key; input.name=key; input.maxLength=key==="slot"?32:8000;
      label.htmlFor=input.id; input.required=key==="steps"||key==="actual"; fields[key]=input; form.append(label,input);
    }
    const submit=el("button","Save report locally"), status=el("p"), download=el("a","Download report"); submit.type="submit";
    status.setAttribute("role","status"); download.hidden=true; form.append(el("p",`Version Browser demo · Build ${build}`), submit, status, download); root.append(form);
    let url;
    form.onsubmit=async e=>{ e.preventDefault(); submit.disabled=true; try {
      const result=await request("/plus/bug",Object.fromEntries(Object.entries(fields).map(([k,v])=>[k,v.value])));
      status.textContent="Saved on this computer: "+result.path; if(url)URL.revokeObjectURL(url);
      url=URL.createObjectURL(new Blob([JSON.stringify(result.report,null,2)+"\n"],{type:"application/json"}));
      download.href=url; download.download=result.name; download.hidden=false;
    } catch(error) { status.textContent=error.message; } finally { submit.disabled=false; } };
  }
  async function galleryTab(root) {
    root.append(el("h2", "Gallery")); const g=await data("gallery"); source(root,g.source);
    const layout=el("div",undefined,"gallery-layout"), list=el("div",undefined,"gallery-list"), figure=el("figure",undefined,"gallery-view"), status=el("p"), toolbar=el("div",undefined,"toolbar");
    status.setAttribute("role","status"); let visible=g.pictures, current=0, generation=0;
    const filter=search("Filter pictures by archive or record",q=>{generation++;visible=g.pictures.filter(p=>(p.file+" "+p.record).toLowerCase().includes(q)); current=0; showList(); if(visible.length)void show(0);else figure.replaceChildren(el("p","No matching pictures."));});
    function showList(){list.replaceChildren();visible.forEach((p,i)=>list.append(button(`${p.file} · ${p.record}`,()=>void show(i))));status.textContent=`${visible.length} pictures. Select a picture to view it.`;}
    async function show(index,frame=0){if(!visible.length)return;current=(index+visible.length)%visible.length;const p=visible[current],token=++generation;
      try { const img=await data("picture",{file:p.file,record:p.record,frame});if(token!==generation)return;
        const canvas=el("canvas");canvas.width=img.width;canvas.height=img.height;canvas.setAttribute("role","img");canvas.setAttribute("aria-label",`${p.file} picture ${p.record}, frame ${frame+1}`);
        const rgba=new Uint8ClampedArray(img.width*img.height*4);img.pixels.flat().forEach((v,i)=>{rgba.set([...img.palette[v],255],i*4);});canvas.getContext("2d").putImageData(new ImageData(rgba,img.width,img.height),0,0);
        const frames=el("select");frames.setAttribute("aria-label","Picture frame");for(let n=0;n<img.frames;n++)frames.add(new Option(`Frame ${n+1} of ${img.frames}`,n,n===frame,n===frame));frames.onchange=()=>void show(current,Number(frames.value));
        figure.replaceChildren(canvas,el("figcaption",`${p.file} · picture ${p.record} · ${img.width} × ${img.height}`),frames);
        status.textContent=`Picture ${current+1} of ${visible.length}`;
      }catch(error){if(token===generation)status.textContent=error.message;}
    }
    toolbar.append(button("Previous picture",()=>void show(current-1)),button("Next picture",()=>void show(current+1)));
    layout.append(list,figure);root.append(filter,status,toolbar,layout);showList();if(visible.length)await show(0);
  }
  async function guideTab(root) {
    root.append(el("h2","Guide & Campaign roster"));
    const [g,r]=await Promise.all([data("guide"),data("roster")]);
    choices(root,["Guide","Campaign roster"],(body,view)=>{
      if(view===0){source(body,g.source);body.append(el("p",g.note));const cards=el("div",undefined,"cards"), label=el("label"),all=el("input");all.type="checkbox";all.id="guide-all";label.append(all,"Show all areas (reveals possible events)");
        let query="";const show=()=>{cards.replaceChildren();for(const a of g.areas.filter(a=>(all.checked||a.current)&&[a.area,...a.monsters,...a.rewards].join(" ").toLowerCase().includes(query))){const card=el("article");
          card.append(el("h3",`Area ${a.area}${a.current?" · Current":""}`),el("p",`Possible combat sites: ${a.encounters}. Treasure sites: ${a.treasures}.`),
            el("p",`Numbered journal references: ${a.entries.join(", ")||"Variable; see Journal for entries cited as you play"}.`),el("p",`Exit area numbers: ${a.exits.join(", ")||"No fixed exits found"}.`));
          for(const [title,rows] of [["Possible encounters",a.monsters],["Possible treasure",a.rewards]]){const details=el("details"),list=el("ul");details.append(el("summary",title));for(const row of rows)list.append(el("li",row));if(!rows.length)list.append(el("li","No fixed entries found."));details.append(list);card.append(details);}cards.append(card);
        }if(!cards.children.length)cards.append(el("p","No matching area."));};
        body.append(label,search("Search areas, encounters or treasure",q=>{query=q;show();}),cards);all.onchange=show;show();
      }else{source(body,r.source);body.append(el("p",r.transfer),el("h3","Current party"));
        const members=rows=>table(["Character","Class","Levels","HP","AC","THAC0"],rows.map(c=>[c.name,c.class_name,c.levels,`${c.hp}/${c.max_hp}`,c.ac,c.thac0]));
        body.append(r.party.length?members(r.party):el("p","No active party."));
        body.append(el("h3","Saved parties"));if(!r.saved.length)body.append(el("p","No letter slots have been saved in this save folder."));
        for(const s of r.saved){const d=el("details");d.append(el("summary",`Slot ${s.slot}`),s.error?el("p",s.error):members(s.members));body.append(d);}
        body.append(el("h3","Saved individual characters"));if(!r.characters.length)body.append(el("p","No individual character files in this save folder."));
        for(const c of r.characters)body.append(el("p",c.error?`${c.file}: ${c.error}`:`${c.name} · ${c.class_name} · Level ${c.levels} · ${c.file}`));
      }
    });
  }
  const renderers={map:mapTab,help:helpTab,rules:rulesTab,bug:bugTab,gallery:galleryTab,guide:guideTab};
  const tabs=[...document.querySelectorAll(".tabs [data-tab]")];
  async function select(id){if(!tabs.some(b=>b.dataset.tab===id))id="journal";
    tabs.forEach(b=>{const on=b.dataset.tab===id;b.setAttribute("aria-selected",String(on));b.tabIndex=on?0:-1;document.getElementById(b.dataset.tab).hidden=!on;});
    const root=document.getElementById(id);if(id==="journal"||root.dataset.loaded)return;root.dataset.loaded="true";root.replaceChildren();
    try{await renderers[id](root);}catch(error){root.dataset.loaded="";root.replaceChildren(el("h2",tabs.find(b=>b.dataset.tab===id).textContent),el("p",error.message),button("Retry",()=>void select(id)));}
  }
  tabs.forEach((b,i)=>{b.onclick=()=>{location.hash=b.dataset.tab;void select(b.dataset.tab);};b.onkeydown=e=>{if(!["ArrowLeft","ArrowRight","Home","End"].includes(e.key))return;e.preventDefault();const n=e.key==="Home"?0:e.key==="End"?tabs.length-1:(i+(e.key==="ArrowRight"?1:tabs.length-1))%tabs.length;tabs[n].click();tabs[n].focus();};});
  addEventListener("hashchange",()=>void select(location.hash.slice(1)));
  void select(location.hash.slice(1));
  void start();
})();
