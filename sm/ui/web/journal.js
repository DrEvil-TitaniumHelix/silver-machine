"use strict";
(() => {
  const transport = (...args) => window.smTransport ? window.smTransport.request(...args) : fetch(...args);
  const panel = document.querySelector('#journal-panel');
  if (!panel) return;
  const headers = {'X-SM-Build': '__SM_BUILD_ID__', 'Content-Type': 'application/json'};
  const requested = Number(new URLSearchParams(location.search).get('entry'));
  let data, selected = requested || null, subtab = 'entries';
  function el(tag, text, parent) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    parent?.append(node);
    return node;
  }
  el('h2', 'Journal', panel);
  const status = el('p', 'Loading journal…', panel);
  status.setAttribute('role', 'status');
  const source = el('p', '', panel);
  const nav = el('div', undefined, panel);
  nav.className = 'journal-tabs'; nav.setAttribute('role', 'tablist'); nav.setAttribute('aria-label', 'Journal sections');
  const panes = {}, tabs = {};
  for (const [key, label] of [['missions', 'Missions'], ['entries', 'Journal Entries'], ['history', 'Conversation History']]) {
    const button = el('button', label, nav); button.type = 'button'; button.id = 'journal-tab-' + key;
    button.setAttribute('role', 'tab'); button.setAttribute('aria-controls', 'journal-' + key);
    const pane = el('section', undefined, panel); pane.id = 'journal-' + key;
    pane.setAttribute('role', 'tabpanel'); pane.setAttribute('aria-labelledby', button.id);
    tabs[key] = button; panes[key] = pane;
    button.onclick = () => { subtab = key; show(); };
    button.onkeydown = event => {
      const keys = Object.keys(tabs), i = keys.indexOf(key);
      const next = event.key === 'ArrowRight' ? keys[(i + 1) % 3] : event.key === 'ArrowLeft' ? keys[(i + 2) % 3] : event.key === 'Home' ? keys[0] : event.key === 'End' ? keys[2] : null;
      if (next) { event.preventDefault(); subtab = next; show(); tabs[next].focus(); }
    };
  }
  function show() {
    for (const key of Object.keys(panes)) {
      panes[key].hidden = key !== subtab;
      tabs[key].setAttribute('aria-selected', String(key === subtab));
      tabs[key].tabIndex = key === subtab ? 0 : -1;
    }
  }
  show();
  el('h3', 'Briefings with a journal reference', panes.missions);
  el('p', 'Briefings recorded as you play. Mission completion is not inferred from a citation.', panes.missions);
  const missions = el('div', undefined, panes.missions);
  el('h3', 'Entries referenced in this game', panes.entries);
  const index = el('nav', undefined, panes.entries); index.id = 'journal-index'; index.setAttribute('aria-label', 'Entry numbers');
  const readerBox = el('div', undefined, panes.entries);
  const readerNote = el('p', '', readerBox);
  const pdfLink = el('a', 'Open your journal PDF', readerBox); pdfLink.hidden = true;
  pdfLink.target = '_blank'; pdfLink.rel = 'noopener';
  const reader = el('iframe', undefined, readerBox); reader.id = 'journal-reader'; reader.hidden = true;
  const entries = el('div', undefined, panes.entries);
  const historyList = el('div', undefined, panes.history);
  const form = el('form', undefined, panes.history);
  el('label', 'Your note', form).htmlFor = 'journal-note';
  const note = el('textarea', undefined, form); note.id = 'journal-note'; note.maxLength = 4000; note.required = true;
  const pinLabel = el('label', undefined, form); pinLabel.className = 'journal-pin';
  const pin = el('input', undefined, pinLabel); pin.type = 'checkbox';
  pinLabel.append(document.createTextNode('Pin to current map cell'));
  const add = el('button', 'Add note', form); add.type = 'submit';
  function where(c) { return `Day ${c.day}, ${String(c.hour).padStart(2, '0')}:${String(c.minute).padStart(2, '0')} · Area ${c.area}/${c.block}, square ${c.x},${c.y}`; }
  function article(parent, text, c) {
    const item = el('article', undefined, parent);
    el('small', where(c) + (c.kind === 'personal' ? ' · Your note' : '') + (c.pin ? ' · Map pin' : ''), item);
    el('p', text, item);
    return item;
  }
  function read(number, scroll = false) {
    const entry = data.entries.find(e => e.number === number);
    selected = number;
    reader.hidden = pdfLink.hidden = true;
    if (!entry) { readerNote.textContent = number ? `Journal entry ${number} has not been referenced in this game.` : 'Choose an entry number to read it.'; return; }
    if (!data.book.available) {
      readerNote.textContent = `Journal entry ${number}: see your printed Adventurer's Journal`;
      reader.removeAttribute('src');
    } else {
      const url = (window.smTransport?.assetURL?.('/journal.pdf') || '/journal.pdf') + (entry.page ? `#page=${entry.page}&view=FitH` : '');
      readerNote.textContent = entry.page ? `Journal entry ${number} · PDF page ${entry.page}. Scroll within the booklet if the entry continues onto the next page.` : `Journal entry ${number}: this PDF edition has no measured page index. Find the entry number in your booklet.`;
      pdfLink.href = url; pdfLink.hidden = false;
      reader.title = `Journal entry ${number} from your own booklet`;
      if (reader.getAttribute('src') !== url) reader.src = url;
      reader.hidden = false;
    }
    for (const item of entries.children) item.classList.toggle('journal-selected', Number(item.dataset.entry) === number);
    if (scroll) readerBox.scrollIntoView({block: 'start'});
  }
  function display() {
    status.textContent = `Save: ${data.slot}. ${data.entries.length} journal entries referenced. ${data.history_count} history items. ${data.error || ''}`;
    source.textContent = data.book.available ? `Booklet: your ${data.book.file}, read from your game folder. ${data.book.mapped ? '' : 'Page locations are unavailable for this PDF edition.'}` : 'No journal PDF in this game folder. Use your printed Adventurer’s Journal.';
    index.replaceChildren(); entries.replaceChildren(); missions.replaceChildren(); historyList.replaceChildren();
    for (const entry of [...data.entries].sort((a, b) => a.number - b.number)) {
      const b = el('button', String(entry.number), index); b.type = 'button'; b.setAttribute('aria-label', `Read journal entry ${entry.number}`);
      b.onclick = () => read(entry.number, true);
    }
    const newest = [...data.entries].sort((a, b) => (b.citations.at(-1)?.order || 0) - (a.citations.at(-1)?.order || 0));
    for (const entry of newest) {
      const item = el('article', undefined, entries); item.dataset.entry = String(entry.number);
      const b = el('button', `Read journal entry ${entry.number}`, item); b.type = 'button'; b.onclick = () => read(entry.number, true);
      for (const c of [...entry.citations].reverse()) { el('small', where(c), item); el('p', c.text, item); }
      if (!data.book.available) el('p', `Journal entry ${entry.number}: see your printed Adventurer's Journal`, item);
    }
    const briefings = newest.flatMap(e => e.citations.map(c => ({...c, number: e.number}))).sort((a, b) => b.order - a.order);
    const seen = new Set();
    for (const c of briefings) {
      if (seen.has(c.text)) continue;
      seen.add(c.text); const item = article(missions, c.text, c);
      const b = el('button', `Read journal entry ${c.number}`, item); b.type = 'button';
      b.onclick = () => { subtab = 'entries'; show(); read(c.number, true); };
    }
    if (!newest.length) { el('p', 'No journal entry has been referenced yet. Entries appear when the game cites them.', entries); el('p', 'No briefing recorded yet.', missions); }
    if (data.history_count > data.history.length) el('p', `Showing the last ${data.history.length} of ${data.history_count} items.`, historyList);
    for (const c of data.history) article(historyList, c.text, c);
    if (!data.history.length) el('p', 'No conversation recorded yet.', historyList);
    read(selected);
  }
  async function request(body) {
    const response = await transport(body ? '/journal/note' : '/journal', {headers, cache: 'no-store',
      ...(body ? {method: 'POST', body: JSON.stringify(body)} : {})});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Journal unavailable. Reload the page.');
    data = result; display();
  }
  form.onsubmit = async event => {
    event.preventDefault(); add.disabled = true;
    try { await request({text: note.value, pin: pin.checked}); note.value = ''; }
    catch (error) { status.textContent = error.message; }
    finally { add.disabled = false; }
  };
  window.addEventListener('focus', () => { void request().catch(error => { status.textContent = error.message; }); });
  void request().catch(error => { status.textContent = error.message; });
})();
