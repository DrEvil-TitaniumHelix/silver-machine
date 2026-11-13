"use strict";

(() => {
  const transport = (...args) => window.smTransport ? window.smTransport.request(...args) : fetch(...args);
  const build = "__SM_BUILD_ID__";
  const canvas = document.querySelector("canvas");
  const focusHint = document.querySelector("#focus-hint");
  const context = canvas.getContext("2d", {alpha: false});
  const pixels = context.createImageData(canvas.width, canvas.height);
  const keysyms = new Map(Object.entries({
    ArrowLeft: "Left", ArrowRight: "Right", ArrowUp: "Up", ArrowDown: "Down",
    Enter: "Return", Escape: "Escape", Backspace: "BackSpace",
    PageUp: "Prior", PageDown: "Next", Home: "Home", End: "End",
    F2: "F2", F10: "F10"
  }));
  const keys = [];
  let palette, basePalette, timer, combatTimer, layout, pointer, frameFormat;
  let running = true;
  let busy = false;
  let restFrame = false, restInputBusy = false, restFlight = Promise.resolve();
  let frameRequested = true;
  let lastKey = performance.now();
  const pageStart = lastKey;
  let reconnectTimer, reconnectBusy = false, reloadHandled = false, instance;
  const sound = (() => {
    let audio = null, cues = null, loading = null, last = null, wanted = false;
    const playing = [], log = window.smSoundLog = [];
    function unlock() {
      if (!wanted || audio || !window.AudioContext) return;
      audio = new AudioContext(); void audio.resume();
    }
    async function table() {
      loading ??= request("/sound").then(r => r.json()).then(v => { cues = v.cues || {}; }).catch(() => { cues = {}; });
      await loading;
    }
    function cut() { while (playing.length) { try { playing.pop().stop(); } catch (e) {} } }
    function schedule(seq, command) {
      cut();
      if (command === 0 || command === 255) { log.push({seq, command, stop: true}); return; }
      const cue = cues[String(command)];
      if (!cue) { log.push({seq, command, missing: true}); return; }
      const start = audio ? audio.currentTime : 0;
      let t = start, osc, gain;
      if (audio) {
        osc = audio.createOscillator(); gain = audio.createGain(); osc.type = "square";
        osc.connect(gain).connect(audio.destination); gain.gain.setValueAtTime(0, start);
      }
      for (const [hz, ms] of cue) {
        log.push({seq, command, t: Math.round((t - start) * 1000 * 1000) / 1000, hz, ms, audible: Boolean(audio)});
        if (audio) {
          if (hz > 0) osc.frequency.setValueAtTime(hz, t);
          gain.gain.setValueAtTime(hz > 0 ? 0.04 : 0, t);
        }
        t += ms / 1000;
      }
      if (audio) { osc.start(start); osc.stop(t); playing.push(osc); osc.onended = () => { const i = playing.indexOf(osc); if (i >= 0) playing.splice(i, 1); }; }
    }
    async function play(events) {
      wanted = true;
      if (last === null) { last = events.length ? Math.max(...events.map(e => e[0])) : 0; return; }
      if (!events.length) return;
      const fresh = events.filter(e => e[0] > last);
      if (!fresh.length) return;
      last = Math.max(...fresh.map(e => e[0]));
      if (cues === null) await table();
      for (const [seq, command] of fresh) schedule(seq, command);
    }
    return {unlock, play};
  })();
  let blurred = !(document.hasFocus?.() ?? true), focusAt = -Infinity, swallowClick = false;
  const REFOCUS_MS = 400;
  const focusText = focusHint.textContent;
  let modCanvas, modFrame, modToken, modObserver;
  const modImages = new Map();

  async function modImage(source) {
    if (!modImages.has(source)) {
      const image = new Image(); image.src = source;
      modImages.set(source, image.decode().then(() => image));
      if (modImages.size > 96) modImages.delete(modImages.keys().next().value);
    }
    return modImages.get(source);
  }

  async function prepareMods(token) {
    if (!token) return null;
    if (token === modToken) return modFrame;
    const response = await request(`/overlay?id=${encodeURIComponent(token)}`, {}, [404]);
    if (response.status === 404) return undefined;
    const data = await response.json();
    const draws = await Promise.all(data.draws.map(async draw => ({...draw,
      bitmap: draw.image ? await modImage(draw.image) : null})));
    return {...data, draws};
  }

  function paintMods() {
    if (!modFrame) {
      if (modCanvas) { modCanvas.getContext('2d').clearRect(0, 0, modCanvas.width, modCanvas.height); modCanvas.hidden = true; }
      return;
    }
    if (!modCanvas) {
      modCanvas = document.createElement('canvas'); modCanvas.id = 'mod-overlay';
      modCanvas.setAttribute('aria-hidden', 'true');
      Object.assign(modCanvas.style, {position: 'absolute', pointerEvents: 'none', imageRendering: 'auto', margin: '0'});
      document.body.appendChild(modCanvas);
      modObserver = new ResizeObserver(() => paintMods());
      modObserver.observe(canvas);
    }
    const bounds = canvas.getBoundingClientRect();
    modCanvas.width = Math.round(bounds.width); modCanvas.height = Math.round(bounds.height);
    Object.assign(modCanvas.style, {left: `${bounds.left + window.scrollX}px`, top: `${bounds.top + window.scrollY}px`,
      width: `${bounds.width}px`, height: `${bounds.height}px`});
    modCanvas.hidden = false;
    const ctx = modCanvas.getContext('2d'), sx = modCanvas.width / 320, sy = modCanvas.height / 200;
    ctx.scale(sx, sy); ctx.beginPath(); ctx.rect(...modFrame.clip); ctx.clip();
    for (const draw of modFrame.draws) {
      ctx.save();
      if (draw.clip) { ctx.beginPath(); ctx.rect(...draw.clip); ctx.clip(); }
      let [x, y, width, height] = draw.rect;
      if (draw.fill) { ctx.fillStyle = draw.fill; ctx.fillRect(x, y, width, height); }
      else {
        ctx.imageSmoothingEnabled = !!draw.fit; ctx.imageSmoothingQuality = 'high';
        if (draw.fit) {
          const scale = Math.min(width / draw.bitmap.width, height / draw.bitmap.height);
          const w = draw.bitmap.width * scale, h = draw.bitmap.height * scale;
          x += (width - w) / 2; y += height - h; width = w; height = h;
        }
        if (draw.mirror) { ctx.translate(2*x+width, 0); ctx.scale(-1, 1); }
        ctx.drawImage(draw.bitmap, x, y, width, height);
      }
      ctx.restore();
    }
    modCanvas.dataset.token = modToken;
    modCanvas.dataset.icons = JSON.stringify(modFrame.icons);
  }

  const cursors = Object.fromEntries(Object.entries({
    "turn-left": "M5 6 L1 11 L5 16 V13 H10 Q18 13 18 21 H23 Q23 8 10 8 H5 Z",
    forward: "M12 2 L3 12 H9 V23 H15 V12 H21 Z",
    "turn-right": "M19 6 L23 11 L19 16 V13 H14 Q6 13 6 21 H1 Q1 8 14 8 H19 Z",
    door: "M5 23 V2 H20 V23 H15 V6 H9 V23 Z M12 11 L18 15 L12 19 V16 H2 V14 H12 Z"
  }).map(([name, path]) => [name, `url("data:image/svg+xml,${encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="26" height="26"><path d="${path}" fill="white" stroke="black" stroke-width="1.5"/></svg>`
  )}") 12 12, pointer`]));

  function focusGame() {
    if (!running) return;
    canvas.focus({preventScroll: true});
    focusHint.hidden = true;
  }

  function hover(event) {
    if (event) pointer = {clientX: event.clientX, clientY: event.clientY};
    const region = pointer && hit(pointer);
    canvas.style.cursor = region?.cursor ? cursors[region.cursor] : region ? "pointer" : "default";
  }

  function hit(event) {
    if (!layout || !running) return;
    const bounds = canvas.getBoundingClientRect();
    const x = (event.clientX - bounds.left) * canvas.width / bounds.width;
    const y = (event.clientY - bounds.top) * canvas.height / bounds.height;
    return layout.regions.find(({rect: [left, top, width, height]}) =>
      x >= left && x < left + width && y >= top && y < top + height);
  }

  function resize() {
    const scale = Math.max(1, Math.floor(Math.min(
      window.innerWidth / canvas.width, (window.innerHeight - (document.querySelector("#alpha")?.offsetHeight || 0) - (document.querySelector("#under")?.offsetHeight || 0)) / canvas.height
    )));
    canvas.style.width = `${canvas.width * scale}px`;
    canvas.style.height = `${canvas.height * scale}px`;
    paintMods();
  }

  function stop() {
    running = false;
    clearInterval(timer);
    clearInterval(combatTimer);
    keys.length = 0;
    window.removeEventListener("keydown", keydown);
    canvas.removeEventListener("click", click);
    canvas.style.cursor = "default";
  }

  function closed() {
    reloadHandled = true;
    focusHint.textContent = "SilverMachine has closed. You can close this window.";
    focusHint.hidden = false;
    try { window.close(); } catch (_) {   }
  }

  function reconnect() {
    if (reconnectTimer || reloadHandled) return;
    focusHint.textContent = "Connection lost. Reconnecting…";
    focusHint.hidden = false;
    reconnectTimer = setInterval(async () => {
      if (reconnectBusy) return;
      reconnectBusy = true;
      try {
        const response = await transport("/version", {cache: "no-store", signal: AbortSignal.timeout(3000)});
        if (response.ok) recovered(await response.json());
      } catch (_) {   }
      finally { reconnectBusy = false; }
    }, 1000);
  }

  function recovered(version) {
    if (version.build === build && (instance === undefined || version.instance === instance)) resume(version);
    else reloadOnce(version);
  }

  function resume(version) {
    instance = version.instance;
    clearInterval(reconnectTimer);
    reconnectTimer = undefined;
    focusHint.textContent = focusText;
    focusHint.hidden = true;
    running = true;
    frameRequested = true;
    window.addEventListener("keydown", keydown);
    canvas.addEventListener("click", click);
    void start();
  }

  function reloadOnce(version) {
    const target = `${version.build}:${version.instance}`;
    if (sessionStorage.getItem("sm-reload") === target) {
      focusHint.textContent = "Waiting for the game…";
      focusHint.hidden = false;
      reconnect();
      return;
    }
    reloadHandled = true;
    clearInterval(reconnectTimer);
    sessionStorage.setItem("sm-reload", target);
    location.reload();
  }

  function fail(error) {
    stop();
    console.error("SilverMachine connection stopped:", error);
    if (window.smTransport?.onError) { window.smTransport.onError(error); return; }
    reconnect();
  }

  async function request(path, options = {}, accepted = []) {
    const response = await transport(path, {cache: "no-store", signal: AbortSignal.timeout(15000), ...options,
      headers: {"X-SM-Build": build, ...options.headers}});
    if (response.status === 409) {
      stop();
      reloadOnce(await response.json());
      throw new Error("Server build changed");
    }
    if (!response.ok && !accepted.includes(response.status)) throw new Error(`${path}: HTTP ${response.status}`);
    return response;
  }

  async function frame() {
    const elapsed = Math.max(0, performance.now() - pageStart);
    const response = await request(`/frame?t=${Math.floor(elapsed)}`);
    const packet = new Uint8Array(await response.arrayBuffer());
    let indices = packet, revision, rgb;
    if (packet.length !== 64000) {
      if (packet.length !== 64784 && packet.length !== 256784) throw new Error('Invalid VGA frame length');
      const header = new DataView(packet.buffer, packet.byteOffset, 16);
      if (String.fromCharCode(...packet.subarray(0, 4)) !== 'SMV1' ||
          header.getUint16(4, true) !== canvas.width || header.getUint16(6, true) !== canvas.height ||
          header.getUint16(8, true) !== 256 || header.getUint16(10, true) !== (packet.length === 256784 ? 1 : 0)) {
        throw new Error('Invalid VGA frame header');
      }
      revision = header.getUint32(12, true);
      palette = Array.from({length: 256}, (_, i) => Array.from(packet.subarray(16 + i*3, 19 + i*3)));
      indices = packet.subarray(784, 64784);
      if (packet.length === 256784) rgb = packet.subarray(64784);
    } else palette = basePalette;
    if (indices.length !== canvas.width * canvas.height) {
      throw new Error("Invalid frame length");
    }
    for (let i = 0, offset = 0; i < indices.length; i++, offset += 4) {
      const colour = rgb ? rgb.subarray(i*3, i*3+3) : palette[indices[i]];
      if (!colour) throw new Error("Invalid palette index");
      pixels.data[offset] = colour[0];
      pixels.data[offset + 1] = colour[1];
      pixels.data[offset + 2] = colour[2];
      pixels.data[offset + 3] = 255;
    }
    const nextLayout = await (await request("/layout")).json();
    if (revision !== undefined && revision !== (nextLayout.frame_revision ?? nextLayout.revision)) {
      frameRequested = true;
      return;
    }
    const nextModToken = response.headers?.get('X-SM-Overlay') || null;
    const nextMods = await prepareMods(nextModToken);
    if (nextMods === undefined) { frameRequested = true; return; }
    if (running) {
      layout = nextLayout;
      const lookStatus = document.querySelector('#look-status');
      if (lookStatus && lookStatus.textContent !== (layout.look_status || '')) {
        lookStatus.textContent = layout.look_status || '';
        lookStatus.hidden = !layout.look_status;
        resize();
      }
      const keyHint = document.querySelector('#key-hint');
      const hintRows = JSON.stringify(layout.key_hint || []);
      if (keyHint && keyHint.smRows !== hintRows && typeof document.createElement === 'function') {
        keyHint.smRows = hintRows;
        const rows = layout.key_hint || [];
        keyHint.hidden = !rows.length;
        keyHint.textContent = '';
        const cell = (key, arrow) => `<span><b>${arrow}</b><i>${key}</i></span>`;
        for (const [key, meaning] of rows) {
          const row = document.createElement('div');
          row.className = 'row';
          if (key === 'compass') {
            row.innerHTML = '<div class="pad">' +
              cell('7', '↖') + cell('8', '↑') + cell('9', '↗') +
              cell('4', '←') + '<span class="mid"></span>' + cell('6', '→') +
              cell('1', '↙') + cell('2', '↓') + cell('3', '↘') +
              '</div><small>keypad, or Home ↑ PgUp / ← → / End ↓ PgDn</small>';
          } else {
            const cap = document.createElement('kbd'); cap.textContent = key; row.append(cap);
          }
          const text = document.createElement('em'); text.textContent = meaning; row.append(text);
          keyHint.append(row);
        }
      }
      const links = document.querySelector('#journal-links');
      const cited = JSON.stringify(layout.journal || []);
      if (links?.replaceChildren && links.dataset.cited !== cited) {
        links.dataset.cited = cited;
        links.replaceChildren(...(layout.journal || []).map(number => {
          const link = document.createElement('a');
          link.textContent = `Read journal entry ${number}`;
          link.href = `/plus?entry=${number}#journal`;
          return link;
        }));
        links.hidden = !(layout.journal || []).length;
        resize();
      }
      context.putImageData(pixels, 0, 0);
      modFrame = nextMods; modToken = nextModToken; paintMods();
      window.smTransport?.onFrame?.(layout);
      if (layout.sound) void sound.play(layout.sound);
      hover();
    }
  }

  function clickKeys(region) {
    if (region.keys) return region.keys;
    if (region.key) return [region.key];
    const roster = region.roster !== undefined;
    const delta = roster ? region.roster - layout.roster_selected : region.select - layout.selected;
    const result = Array.from({length: Math.abs(delta)}, () => ({
      keysym: delta < 0 ? "Up" : "Down", char: ""
    }));
    if (!roster) result.push({keysym: "Return", char: ""});
    return result;
  }

  async function sendKey(body) {
    lastKey = performance.now();
    const response = await request("/key", {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)
    });
    const result = await response.json();
    if (result.quit) { stop(); if (window.smTransport?.onQuit) window.smTransport.onQuit(); else closed(); }
    return result;
  }

  function restKeys() {
    if (!restFrame || restInputBusy || !running) return restFlight;
    restInputBusy = true;
    restFlight = (async () => {
      try {
        while (restFrame && running && keys.length && !keys[0].click) await sendKey(keys.shift());
      } catch (error) { fail(error); }
      finally { restInputBusy = false; }
    })();
    return restFlight;
  }

  async function pump() {
    if (busy || !running || !palette) return;
    busy = true;
    try {
      while (running && (keys.length || frameRequested)) {
        const input = keys.shift();
        if (input?.click && input.revision !== JSON.stringify(layout.revision)) continue;
        const batch = input?.click ? clickKeys(input.click) : input ? [input] : [];
        if (batch.length) {
          const body = input.click ? {keys: batch, revision: layout.revision} : input;
          const result = await sendKey(body);
          restFrame = result.decision?.kind === "INPUT";
        }
        if (!running) break;
        frameRequested = false;
        void restKeys();
        try { await frame(); }
        finally { restFrame = false; }
        await restFlight;
      }
    } catch (error) {
      fail(error);
    } finally {
      busy = false;
    }
  }

  function mousedown() {
    swallowClick = blurred || performance.now() - focusAt < REFOCUS_MS;
    blurred = false;
  }

  function click(event) {
    sound.unlock();
    focusGame();
    if (swallowClick || performance.now() - focusAt < REFOCUS_MS) { swallowClick = false; return; }
    if (!running || !layout || event.button !== 0 || event.detail > 1 ||
        event.ctrlKey || event.metaKey || event.altKey) return;
    const region = hit(event);
    if (!region) return;
    event.preventDefault();
    keys.push({click: region, revision: JSON.stringify(layout.revision)});
    void pump();
  }

  function keydown(event) {
    sound.unlock();
    if (event.target?.closest?.("a, input, button, select")) return;
    if (!running || event.isComposing || event.ctrlKey || event.metaKey) return;
    if (event.repeat && event.key === "Enter") { event.preventDefault(); return; }
    let key;
    if (event.altKey) {
      if (!/^[a-z]$/i.test(event.key)) return;
      key = {keysym: "Alt-" + event.key.toLowerCase(), char: ""};
    } else if (/^F(?:[1-4]|[6-9]|1[01])$/.test(event.key)) {
      key = {keysym: event.key, char: ""};
    } else if (keysyms.has(event.key)) {
      key = {keysym: keysyms.get(event.key), char: ""};
    } else if ([...event.key].length === 1 && event.key >= " " && event.key !== "\x7f") {
      key = {keysym: event.key, char: event.key};
    } else {
      return;
    }
    event.preventDefault();
    keys.push(key);
    if (restFrame) void restKeys();
    else void pump();
  }

  async function start() {
    try {
      const version = await (await request("/version")).json();
      if (version.build !== build) { stop(); reloadOnce(version); return; }
      instance = version.instance;
      frameFormat = version.frame_format;
      if (frameFormat !== undefined && frameFormat !== 'indexed-vga-v1') throw new Error('Unknown frame format');
      const response = await request("/palette");
      const colours = await response.json();
      if (!Array.isArray(colours) || colours.length < 1 || colours.length > 256 || colours.some(colour =>
        !Array.isArray(colour) || colour.length !== 3 || colour.some(value =>
          !Number.isInteger(value) || value < 0 || value > 255))) {
        throw new Error("Invalid palette");
      }
      if (!running) return;
      palette = basePalette = colours;
      timer = setInterval(() => {
        if (layout?.animating) return;
        frameRequested = true;
        void pump();
      }, 100);
      combatTimer = setInterval(() => {
        if (!layout?.animating) return;
        frameRequested = true;
        void pump();
      }, 10);
      void pump();
    } catch (error) {
      fail(error);
    }
  }

  resize();
  window.addEventListener("resize", resize);
  window.addEventListener("keydown", keydown);
  canvas.addEventListener("click", click);
  canvas.addEventListener("mousemove", hover);
  canvas.addEventListener("mouseleave", () => {pointer = null; canvas.style.cursor = "default";});
  window.addEventListener("blur", () => {blurred = true; if (running) focusHint.hidden = false;});
  window.addEventListener("focus", () => {blurred = false; focusAt = performance.now(); focusGame();});
  canvas.addEventListener("mousedown", mousedown);
  window.addEventListener("pagehide", stop);
  void start();
  focusGame();
})();
