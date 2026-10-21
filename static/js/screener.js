// Screener side panel: NSE stocks filtered and sorted by price, volume, 52-week position, RSI and
// distance from the 50/200-day averages. Click a row to chart that stock. Rows come from /api/screener
// (refreshed every 10 s while the panel is open); filtering and sorting are screener-policy.js.
import { compactIN, esc, signed } from './format.js';
import { COLUMNS, PRESETS, activeFilterCount, applyFilters, sortRows } from './screener-policy.js';
import { switchSymbol } from './symbol.js';
import { $, state, visible } from './state.js';

const KEY = 'orazio.screener.v1';
const POLL_MS = 10000;
const panel = $('screener');
const tbody = $('scr-body');
const filtersEl = $('scr-filters');

let cfg = { open: false, universe: 'nifty500', preset: 'all', filters: {}, sort: PRESETS.all.sort };
try { cfg = { ...cfg, ...JSON.parse(localStorage.getItem(KEY) || '{}') }; } catch (e) { /* defaults */ }
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(cfg)); } catch (e) { /* not persisted */ } };

let data = null;        // last /api/screener payload
let lastFetch = 0;
let inFlight = false;

// ---------- static parts ----------
$('scr-preset').innerHTML = Object.entries(PRESETS).map(([k, p]) => `<option value="${k}">${esc(p.label)}</option>`).join('')
  + '<option value="custom" hidden>Custom filters</option>';
$('scr-head').innerHTML = `<tr>${COLUMNS.map(c => `<th${c.num ? '' : ' class="l"'}${c.title ? ` title="${esc(c.title)}"` : ''}><button type="button" data-sort="${c.key}">${esc(c.label)}</button></th>`).join('')}</tr>`;
filtersEl.innerHTML = COLUMNS.filter(c => c.num).map(c => `<label class="scr-f"><span>${esc(c.label)}</span>
  <input type="number" step="any" data-key="${c.key}" data-end="min" placeholder="min" aria-label="${esc(c.label)} minimum">
  <input type="number" step="any" data-key="${c.key}" data-end="max" placeholder="max" aria-label="${esc(c.label)} maximum"></label>`).join('')
  + '<button type="button" class="btn" id="scr-reset">Reset filters</button>';

function syncControls() {
  $('scr-universe').value = cfg.universe;
  $('scr-preset').value = cfg.preset;
  filtersEl.querySelectorAll('input').forEach(inp => {
    const v = cfg.filters[inp.dataset.key]?.[inp.dataset.end];
    inp.value = typeof v === 'number' ? v : '';
  });
  const n = activeFilterCount(cfg.filters);
  $('scr-filters-btn').textContent = n ? `Filters (${n})` : 'Filters';
}

// ---------- table ----------
function cell(c, r) {
  const v = r[c.key];
  if (c.key === 'symbol') {
    const tag = r.cross ? `<span class="scr-cross ${r.cross}" title="50/200-day ${r.cross} cross in the last 5 days">${r.cross === 'golden' ? 'GC' : 'DC'}</span>` : '';
    return `<td class="l"><strong>${esc(v)}</strong>${tag}<div class="mv-name">${esc(r.name || '')}</div></td>`;
  }
  if (v === null || v === undefined) return '<td class="dim">–</td>';
  if (c.key === 'volume') return `<td>${compactIN(v)}</td>`;
  if (c.key === 'rsi') return `<td class="${v >= 70 ? 'down' : v <= 30 ? 'up' : ''}">${v.toFixed(1)}</td>`;
  if (c.pct) return `<td class="${v > 0 ? 'up' : v < 0 ? 'down' : ''}">${signed(v)}</td>`;
  return `<td>${v.toLocaleString('en-IN', { maximumFractionDigits: 2 })}</td>`;
}

function render() {
  syncControls();
  document.querySelectorAll('#scr-head button').forEach(b => {
    b.dataset.dir = b.dataset.sort === cfg.sort.key ? (cfg.sort.dir > 0 ? 'asc' : 'desc') : '';
  });
  if (!data) return;
  if (!data.available) {
    tbody.innerHTML = `<tr><td colspan="${COLUMNS.length}" class="scr-empty">Screener data unavailable — NSE didn't answer. Retrying.</td></tr>`;
    $('scr-status').textContent = '';
    return;
  }
  const rows = sortRows(applyFilters(data.rows, cfg.filters), cfg.sort);
  const tech = { ready: '', loading: ' · RSI/SMA loading (first run ~15 s)…', unavailable: ' · RSI/SMA unavailable (Yahoo)' }[data.technicals] || '';
  $('scr-status').textContent = `${rows.length} of ${data.rows.length}${tech}`;
  $('scr-updated').textContent = data.asOf ? `NSE ${data.asOf.slice(11, 16)}` : '';
  const current = state.currentSymbol;
  tbody.innerHTML = rows.length
    ? rows.map(r => `<tr tabindex="0" data-chart-symbol="${esc(r.chartSymbol)}"${r.chartSymbol === current ? ' class="is-current"' : ''}>${COLUMNS.map(c => cell(c, r)).join('')}</tr>`).join('')
    : `<tr><td colspan="${COLUMNS.length}" class="scr-empty">No stocks match these filters.</td></tr>`;
}

async function load() {
  if (inFlight || !cfg.open) return;
  inFlight = true;
  const universe = cfg.universe;
  try {
    const res = await fetch(`/api/screener?universe=${encodeURIComponent(universe)}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const d = await res.json();
    if (universe !== cfg.universe) return;   // switched universe while this loaded
    data = d;
    lastFetch = Date.now();
  } catch (e) {
    if (!data) data = { available: false, rows: [] };
  } finally {
    inFlight = false;
    render();
  }
}

// ---------- controls ----------
function setOpen(open) {
  cfg.open = open;
  panel.hidden = !open;
  $('screener-btn').setAttribute('aria-pressed', String(open));
  save();
  if (open) {
    document.dispatchEvent(new CustomEvent('panel:open', { detail: 'screener' }));
    load();
  }
}

$('screener-btn').addEventListener('click', () => setOpen(!cfg.open));
// The bonds panel and this one share the right edge: opening one closes the other.
document.addEventListener('panel:open', (e) => { if (e.detail !== 'screener' && cfg.open) setOpen(false); });
$('screener-close').addEventListener('click', () => setOpen(false));
$('scr-universe').addEventListener('change', (e) => {
  cfg.universe = e.target.value;
  data = null;
  tbody.innerHTML = `<tr><td colspan="${COLUMNS.length}" class="scr-empty">Loading…</td></tr>`;
  save();
  load();
});
$('scr-preset').addEventListener('change', (e) => {
  const p = PRESETS[e.target.value];
  if (!p) return;
  cfg.preset = e.target.value;
  cfg.filters = structuredClone(p.filters);
  cfg.sort = { ...p.sort };
  save();
  render();
});
$('scr-filters-btn').addEventListener('click', () => {
  filtersEl.hidden = !filtersEl.hidden;
  $('scr-filters-btn').setAttribute('aria-expanded', String(!filtersEl.hidden));
});
filtersEl.addEventListener('input', (e) => {
  const inp = e.target.closest('input[data-key]');
  if (!inp) return;
  const f = { ...(cfg.filters[inp.dataset.key] || {}) };
  const v = inp.value === '' ? null : Number(inp.value);
  f[inp.dataset.end] = Number.isFinite(v) ? v : null;
  cfg.filters = { ...cfg.filters, [inp.dataset.key]: f };
  cfg.preset = 'custom';
  save();
  render();
});
filtersEl.addEventListener('click', (e) => {
  if (e.target.id !== 'scr-reset') return;
  cfg.filters = {};
  cfg.preset = 'all';
  save();
  render();
});
$('scr-head').addEventListener('click', (e) => {
  const b = e.target.closest('button[data-sort]');
  if (!b) return;
  const key = b.dataset.sort;
  cfg.sort = { key, dir: cfg.sort.key === key ? -cfg.sort.dir : (key === 'symbol' ? 1 : -1) };
  save();
  render();
});

function openRow(tr) {
  const sym = tr?.dataset.chartSymbol;
  if (!sym) return;
  $('symbol-input').value = sym;   // switchSymbol() itself doesn't touch the search box
  switchSymbol(sym);
  tbody.querySelectorAll('tr.is-current').forEach(r => r.classList.remove('is-current'));
  tr.classList.add('is-current');
}
tbody.addEventListener('click', (e) => openRow(e.target.closest('tr[data-chart-symbol]')));
tbody.addEventListener('keydown', (e) => {
  if (e.key !== 'Enter' && e.key !== ' ') return;
  e.preventDefault();
  openRow(e.target.closest('tr[data-chart-symbol]'));
});

setInterval(visible(() => { if (cfg.open && Date.now() - lastFetch >= POLL_MS) load(); }), 1000);
setOpen(cfg.open);
render();
