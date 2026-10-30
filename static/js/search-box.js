// A symbol search box with a results dropdown — used by the main toolbar search and the Compare pane.
// Ranked locally on every keystroke against /api/symbols (NSE stocks, F&O futures, indices, commodities,
// crypto, bonds) with search-rank.js; Yahoo's search fills in global listings a moment later.
// Typing a bare NSE ticker and pressing Enter (ADANIENT, RELIANCE) resolves to its NSE listing.
import { esc } from './format.js';
import { highlightRanges, matchesKind, parseQuery, prepare, rank, TIER } from './search-rank.js';

// Pure (tests/frontend/search-box.test.mjs): what typed text should load, given /api/search results.
// Order: an exchange prefix (NSE:X / BSE:X); our own aliases and explicit tickers as typed; then the NSE listing
// (an Indian app first); then an exact match elsewhere (AAPL); then the BSE listing; otherwise the text as typed.
export function pickTyped(text, items, aliases = []) {
  const { text: t, exch } = parseQuery(text);
  if (t && exch === 'NSE') return `${t}.NS`;
  if (t && exch === 'BSE') return `${t}.BO`;
  if (!t || aliases.includes(t) || /[\^.=]/.test(t) || t.endsWith('-FUT')) return t;
  const syms = new Set((items || []).map(it => String(it.symbol || '').toUpperCase()));
  if (syms.has(`${t}.NS`)) return `${t}.NS`;
  if (syms.has(t)) return t;
  if (syms.has(`${t}.BO`)) return `${t}.BO`;
  return t;
}

const CHIPS = [['all', 'All'], ['stock', 'Stocks'], ['index', 'Indices'], ['future', 'Futures'],
  ['commodity', 'Commodities'], ['bond', 'Bonds'], ['crypto', 'Crypto']];
const TYPE_LABEL = { stock: 'Stock', etf: 'ETF', index: 'Index', future: 'Futures', commodity: 'Commodity', bond: 'Bond', crypto: 'Crypto', fx: 'Forex' };
const SHOWN = 40;
const RECENT_KEY = 'orazio.recent.v1';
const MAJOR_EXCH = new Set(['NSE', 'BSE', 'NASDAQ', 'NYSE']);

// ---- data: the local master (once per page) and Yahoo results (cached per query) ----
let master = [];
let known = new Set();   // every master symbol and synonym: Yahoo rows already covered are dropped
let masterLoad = null;
function loadMaster() {
  masterLoad ||= fetch('/api/symbols').then(r => (r.ok ? r.json() : Promise.reject())).then((list) => {
    master = list.map(prepare);
    known = new Set(master.flatMap(it => it._alt));
  }).catch(() => { masterLoad = null; });   // retried on the next focus
  return masterLoad;
}

const yahooCache = new Map();
function fromYahoo(it) {
  const exch = String(it.exchange || '');
  return prepare({
    symbol: it.symbol, ticker: it.symbol.replace(/\.[A-Z]{1,3}$/, ''), name: it.name, exch, type: it.type,
    pop: it.type === 'index' || MAJOR_EXCH.has(exch) ? 3 : 1, remote: true,
  });
}
function yahoo(q) {
  if (!yahooCache.has(q)) {
    const p = fetch(`/api/search?q=${encodeURIComponent(q)}`).then(r => (r.ok ? r.json() : Promise.reject()))
      .then(list => list.map(fromYahoo).filter(it => !known.has(it._alt[0])));
    p.catch(() => yahooCache.delete(q));
    yahooCache.set(q, p);
    if (yahooCache.size > 100) yahooCache.delete(yahooCache.keys().next().value);
  }
  return yahooCache.get(q);
}

// ---- recents ----
function loadRecent() {
  try { return (JSON.parse(localStorage.getItem(RECENT_KEY) || '[]') || []).filter(r => r && r.symbol).slice(0, 8); } catch (e) { return []; }
}
function remember(item) {
  const entry = { symbol: item.symbol, ticker: item.ticker || item.symbol, name: item.name || '', exch: item.exch || '', type: item.type || '', fno: !!item.fno };
  const next = [entry, ...loadRecent().filter(r => r.symbol !== entry.symbol)].slice(0, 8);
  try { localStorage.setItem(RECENT_KEY, JSON.stringify(next)); } catch (e) { /* private mode: no recents */ }
}

function marked(text, query) {
  const s = String(text || '');
  let out = '', at = 0;
  for (const [a, b] of query ? highlightRanges(s, query) : []) {
    out += esc(s.slice(at, a)) + `<mark>${esc(s.slice(a, b))}</mark>`;
    at = b;
  }
  return out + esc(s.slice(at));
}

// Wires `input` + `box` (an element with class "results") and calls onChoose(symbol).
// current(): the symbol to put back in the box when the search is dismissed without a pick.
export function attachSearch({ input, box, idPrefix, onChoose, aliases = () => [], current = null }) {
  const listId = `${idPrefix}-list`;
  let debounce = null;
  let kind = 'all';
  let rows = [];          // [{ item, tier }] currently shown
  let active = 0;
  let moved = false;      // the user picked a row with the arrows/mouse: Enter takes it, not the top hit
  const yahooFor = {};    // query -> Yahoo items once they arrive

  box.removeAttribute('role');
  input.setAttribute('role', 'combobox');
  input.setAttribute('aria-autocomplete', 'list');
  input.setAttribute('aria-expanded', 'false');
  input.setAttribute('aria-controls', listId);

  const isOpen = () => box.classList.contains('open');
  const open = () => { box.classList.add('open'); input.setAttribute('aria-expanded', 'true'); };
  const close = (restore = true) => {
    clearTimeout(debounce);
    box.classList.remove('open');
    input.setAttribute('aria-expanded', 'false');
    input.removeAttribute('aria-activedescendant');
    if (restore && current) input.value = current();
  };

  const ranked = (text) => rank(master.concat(yahooFor[parseQuery(text).text] || []), text);

  function rowHtml({ item }, i, query) {
    return `<div class="result" role="option" id="${idPrefix}-${i}" data-i="${i}" aria-selected="${i === active}">`
      + `<span class="sym">${marked(item.ticker, query)}</span>`
      + `<span class="nm" title="${esc(item.name || '')}">${marked(item.name, query)}</span>`
      + `<span class="tags">${item.fno ? '<span class="tag fno" title="Has futures &amp; options on NSE">F&amp;O</span>' : ''}`
      + `<span class="tag">${esc(TYPE_LABEL[item.type] || item.type || '')}</span><span class="ex">${esc(item.exch || '')}</span></span></div>`;
  }

  function paint(html) {
    box.innerHTML = html;
    open();
    syncActive();
  }
  function syncActive() {
    const els = box.querySelectorAll('.result');
    els.forEach((r, idx) => r.setAttribute('aria-selected', String(idx === active)));
    if (els[active]) {
      input.setAttribute('aria-activedescendant', els[active].id);
      els[active].scrollIntoView({ block: 'nearest' });
    } else input.removeAttribute('aria-activedescendant');
  }

  function showRecent() {
    const recent = loadRecent();
    rows = recent.map(item => ({ item, tier: TIER.EXACT }));
    active = 0; moved = false;
    if (!rows.length) { close(false); return; }
    paint(`<div class="sr-head">Recent</div><div class="sr-list" role="listbox" id="${listId}" aria-label="Recent symbols">${rows.map((r, i) => rowHtml(r, i, '')).join('')}</div>`
      + `<div class="sr-foot">${hint()}</div>`);
  }

  const hint = () => '<span><kbd>↑</kbd><kbd>↓</kbd> move</span><span><kbd>↵</kbd> open</span><span><kbd>Esc</kbd> close</span><span class="sr-tip">Exchange: <code>NSE:INFY</code> <code>BSE:INFY</code></span>';

  function render() {
    const text = input.value.trim();
    if (!text) { showRecent(); return; }
    const all = ranked(text);
    const counts = {};
    for (const h of all) {
      const k = h.item.type === 'etf' ? 'stock' : h.item.type;
      counts[k] = (counts[k] || 0) + 1;
    }
    const keepSym = moved && rows[active] ? rows[active].item.symbol : null;
    rows = all.filter(h => matchesKind(h.item, kind)).slice(0, SHOWN);
    const kept = keepSym ? rows.findIndex(r => r.item.symbol === keepSym) : -1;
    if (kept >= 0) active = kept; else { active = 0; moved = false; }

    const chips = CHIPS.filter(([k]) => k === 'all' || k === kind || counts[k]).map(([k, label]) =>
      `<button type="button" class="sr-chip" data-kind="${k}" aria-pressed="${k === kind}">${label}${k === 'all' ? '' : `<span>${counts[k] || 0}</span>`}</button>`).join('');
    const searching = !(parseQuery(text).text in yahooFor);   // Yahoo hasn't answered this query yet
    const empty = rows.length ? '' : `<div class="sr-empty">${searching ? 'Searching…' : `No match for “${esc(text)}”${kind === 'all' ? '' : ' in this filter'}. <kbd>↵</kbd> loads it as a ticker.`}</div>`;
    paint(`<div class="sr-chips" role="group" aria-label="Filter by type">${chips}</div>`
      + `<div class="sr-list" role="listbox" id="${listId}" aria-label="Symbols">${rows.map((r, i) => rowHtml(r, i, text)).join('')}</div>${empty}`
      + `<div class="sr-foot">${searching && rows.length ? '<span class="sr-busy">Searching global markets…</span>' : hint()}</div>`);
  }

  function askYahoo(text) {
    const q = parseQuery(text).text;
    if (!q || yahooFor[q]) return Promise.resolve();
    return yahoo(q).then((items) => { yahooFor[q] = items; }).catch(() => { yahooFor[q] = []; })
      .finally(() => { if (document.activeElement === input && parseQuery(input.value).text === q) render(); });
  }

  const choose = (item) => {
    const sym = typeof item === 'string' ? item : item.symbol;
    if (!sym) return;
    remember(typeof item === 'string' ? { symbol: sym } : item);
    close(false);
    input.value = sym;
    input.blur();
    onChoose(sym);
  };

  // Enter with no row picked: an exact hit opens at once; otherwise let Yahoo answer (≤ 2.5 s) and take the best.
  async function chooseTyped() {
    const text = input.value.trim();
    if (!text) { if (rows[active]) choose(rows[active].item); return; }
    if (/[\^.=]/.test(text) || /-FUT$/i.test(text) || /^(NSE|BSE):/i.test(text)) {   // explicit: load what was typed
      const sym = pickTyped(text, [], aliases());
      choose(master.find(it => it.symbol.toUpperCase() === sym) || sym);
      return;
    }
    if (rows[0] && rows[0].tier === TIER.EXACT) { choose(rows[0].item); return; }
    await Promise.race([askYahoo(text), new Promise(r => setTimeout(r, 2500))]);
    if (input.value.trim() !== text) return;            // typed on while waiting
    const best = ranked(text).find(h => matchesKind(h.item, kind));
    choose(best ? best.item : pickTyped(text, [], aliases()));
  }

  input.addEventListener('input', () => {
    clearTimeout(debounce);
    moved = false;
    const text = input.value.trim();
    render();
    if (!master.length) loadMaster().then(() => { if (input.value.trim() === text && document.activeElement === input) render(); });
    if (text) debounce = setTimeout(() => askYahoo(text), 150);
  });
  loadMaster();   // at boot, so the first keystroke already has it
  input.addEventListener('focus', () => {
    input.select();
    if (!master.length) loadMaster();
    if (!isOpen()) showRecent();
  });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      if (!isOpen()) { render(); return; }
      if (!rows.length) return;
      active = (active + (e.key === 'ArrowDown' ? 1 : -1) + rows.length) % rows.length;
      moved = true;
      syncActive();
    } else if (e.key === 'Escape') {
      close(); input.blur();
    } else if (e.key === 'Enter') {
      e.preventDefault();
      clearTimeout(debounce);   // a pending search must not reopen stale results after the pick
      if (moved && rows[active]) choose(rows[active].item); else chooseTyped();
    }
  });
  box.addEventListener('mousedown', e => e.preventDefault());   // rows, chips, scrollbar: focus (and the query) stay in the input
  box.addEventListener('click', (e) => {
    const chip = e.target.closest('.sr-chip');
    if (chip) {
      kind = chip.dataset.kind;
      render();
      if (e.detail === 0) box.querySelector(`.sr-chip[data-kind="${kind}"]`)?.focus();   // keyboard: stay on the chips
      return;
    }
    const row = e.target.closest('.result');
    if (row && rows[+row.dataset.i]) choose(rows[+row.dataset.i].item);
  });
  box.addEventListener('mousemove', (e) => {
    const row = e.target.closest('.result');
    if (!row || +row.dataset.i === active) return;
    active = +row.dataset.i; moved = true;
    box.querySelectorAll('.result').forEach((r, idx) => r.setAttribute('aria-selected', String(idx === active)));
  });
  document.addEventListener('click', (e) => { if (isOpen() && !box.parentElement.contains(e.target)) close(); });
  box.parentElement.addEventListener('focusout', (e) => {   // tabbed away (a pick closes first, so it isn't undone here)
    if (isOpen() && !box.parentElement.contains(e.relatedTarget)) close();
  });
}
