// Bonds side panel, two tabs:
//   Global — government bond yields for 37 countries (CNBC, real time). Find a country, line every country up on
//            one maturity (2Y/5Y/10Y/30Y, or the nearest), order by region, yield or day change. Each country
//            opens to its curve (drawn, plus every maturity); click any maturity to chart it.
//   India  — CCIL NDS-OM, live: central govt (G-sec) / state govt (SDL) / T-bills / when-issued, and NSE-listed
//            corporate bonds. Click a G-sec, SDL or T-bill to chart its yield (recorded by this app from the day
//            it first saw the security trade).
// Only one of the screener and this panel is open at a time.
import { esc } from './format.js';
import { browseCountries, changedYields, curveGeometry, yearsTo, yieldMap } from './bonds-policy.js';
import { sortRows } from './screener-policy.js';
import { switchSymbol } from './symbol.js';
import { $, state, visible } from './state.js';

const KEY = 'orazio.bonds.v2';
const panel = $('bonds');
const POLL = { global: 15000, india: 5000, corp: 15000 };
const GSEC_COLS = [
  { key: 'security', label: 'Security', l: true },
  { key: 'maturity', label: 'Mat.', title: 'Years to maturity' },
  { key: 'ltYield', label: 'Yield', title: 'Last traded yield (%)' },
  { key: 'ltPrice', label: 'Price', title: 'Last traded price' },
  { key: 'bidYield', label: 'Bid', title: 'Best bid yield' },
  { key: 'askYield', label: 'Ask', title: 'Best offer yield' },
  { key: 'traded', label: '₹ Cr', title: 'Traded today (₹ crore)' },
];
const CORP_COLS = [
  { key: 'symbol', label: 'Bond', l: true },
  { key: 'rating', label: 'Rating', l: true },
  { key: 'coupon', label: 'Cpn', title: 'Coupon (%)' },
  { key: 'maturity', label: 'Mat.', title: 'Years to maturity' },
  { key: 'ltPrice', label: 'Price', title: 'Last traded price' },
  { key: 'ytm', label: 'YTM', title: 'Yield to maturity (%). ≈ = worked out here from price, coupon and maturity' },
  { key: 'tradedLakh', label: '₹ L', title: 'Traded today (₹ lakh)' },
];

let cfg = { open: false, tab: 'global', seg: 'cg', tradedOnly: true, sort: { key: 'traded', dir: -1 }, expanded: ['IN', 'US'], tenor: '10Y', order: 'region' };
try { cfg = { ...cfg, ...JSON.parse(localStorage.getItem(KEY) || '{}') }; } catch (e) { /* defaults */ }
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(cfg)); } catch (e) { /* not persisted */ } };

let globalRows = null;
let india = null;            // last /api/bonds/india payload (for cfg.seg)
let prevYields = null;
let lastFetch = { global: 0, india: 0 };
let inFlight = false;

const f = (v, d = 2) => (v == null ? '–' : v.toFixed(d));
const bp = (v) => (v == null ? '–' : `${v > 0 ? '+' : ''}${v.toFixed(1)}`);
const dir = (v) => (v > 0 ? 'up' : v < 0 ? 'down' : '');
const age = (iso) => {
  if (!iso) return '';
  const s = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 1000));
  return s < 60 ? `${s}s` : s < 3600 ? `${Math.floor(s / 60)}m` : s < 86400 ? `${Math.floor(s / 3600)}h` : `${Math.floor(s / 86400)}d`;
};

// ---------- global ----------
const CURVE_W = 380, CURVE_H = 72;

// The country's curve as a small chart: one dot per maturity, each a button that charts it.
function curveSvg(c) {
  const g = curveGeometry(c.curve, CURVE_W, CURVE_H, 10);
  if (!g) return '';
  const line = g.map(p => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
  const inverted = g[0].r.yield > g[g.length - 1].r.yield;
  return `<svg class="bc-svg" viewBox="0 0 ${CURVE_W} ${CURVE_H}" preserveAspectRatio="none" role="img" aria-label="${esc(c.name)} yield curve, ${inverted ? 'inverted' : 'upward sloping'}">
    <polyline points="${line}" fill="none" vector-effect="non-scaling-stroke"/>
    ${g.map(p => `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="3" vector-effect="non-scaling-stroke"${p.r.symbol === state.currentSymbol ? ' class="is-current"' : ''}/>`).join('')}
  </svg>`;
}

function renderGlobal() {
  const box = $('bond-global');
  document.querySelectorAll('#bond-tenor button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.tenor === cfg.tenor)));
  document.querySelectorAll('#bond-sort button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.sort === cfg.order)));
  if (!globalRows) { box.innerHTML = '<div class="scr-empty">Loading yields…</div>'; return; }
  if (!globalRows.length) { box.innerHTML = '<div class="scr-empty">Yields unavailable (CNBC didn’t answer). Retrying.</div>'; return; }
  const groups = browseCountries(globalRows, { q: $('bond-q').value, tenor: cfg.tenor, sort: cfg.order });
  if (!groups.length) { box.innerHTML = `<div class="scr-empty">No country matches “${esc($('bond-q').value)}”.</div>`; return; }
  const open = new Set(cfg.expanded);
  const head = `<div class="bc-head" aria-hidden="true"><span>Country</span><span>Tenor</span><span>Yield</span><span>Day</span><span></span></div>`;
  box.innerHTML = head + groups.map(g => `${g.region ? `<h3 class="bond-sec">${esc(g.region)}</h3>` : ''}${g.countries.map(c => {
    const h = c.headline;
    const isOpen = open.has(c.country);
    const near = h.tenor !== cfg.tenor;
    const curve = isOpen ? `<div class="bc-open">${curveSvg(c)}<div class="bc-curve">${c.curve.map(r => `<button type="button" class="bc-pt${r.symbol === state.currentSymbol ? ' is-current' : ''}" data-symbol="${esc(r.symbol)}" title="Chart the ${esc(r.label)} yield (last tick ${esc(age(r.time))} ago)">
        <span class="bc-t">${esc(r.tenor)}</span><span class="num">${f(r.yield, 3)}</span><span class="num ${dir(r.changeBp)}">${bp(r.changeBp)}</span></button>`).join('')}</div></div>` : '';
    return `<div class="bc${isOpen ? ' open' : ''}"><button type="button" class="bc-row" data-country="${esc(c.country)}" aria-expanded="${isOpen}" title="${isOpen ? 'Hide' : 'Show'} the ${esc(c.name)} curve">
      <span class="bc-name">${esc(c.name)}</span><span class="bc-ten${near ? ' near' : ''}"${near ? ` title="No ${esc(cfg.tenor)}: nearest maturity shown"` : ''}>${esc(h.tenor)}</span>
      <span class="num bc-y">${f(h.yield, 3)}%</span><span class="num bc-c ${dir(h.changeBp)}">${h.changeBp == null ? "–" : `${bp(h.changeBp)} bp`}</span>
      <svg class="bc-chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg></button>${curve}</div>`;
  }).join('')}`).join('');
}

// ---------- india ----------
function cols() { return cfg.seg === 'corp' ? CORP_COLS : GSEC_COLS; }

function renderIndia(flash = new Map()) {
  document.querySelectorAll('#bond-seg button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.seg === cfg.seg)));
  $('bond-traded-only').checked = cfg.tradedOnly;
  const c = cols();
  $('bond-head').innerHTML = `<tr>${c.map(col => `<th${col.l ? ' class="l"' : ''}${col.title ? ` title="${esc(col.title)}"` : ''}><button type="button" data-sort="${col.key}" data-dir="${col.key === cfg.sort.key ? (cfg.sort.dir > 0 ? 'asc' : 'desc') : ''}">${esc(col.label)}</button></th>`).join('')}</tr>`;
  const pill = $('bond-status');
  if (!india) { $('bond-body').innerHTML = `<tr><td colspan="${c.length}" class="scr-empty">Loading…</td></tr>`; return; }
  if (!india.available) {
    pill.textContent = 'Unavailable';
    pill.dataset.live = 'false';
    const src = cfg.seg === 'corp' ? 'NSE' : 'CCIL';
    $('bond-body').innerHTML = `<tr><td colspan="${c.length}" class="scr-empty">${cfg.seg === 'wi' ? 'No when-issued securities today.' : `${src} didn't answer. Retrying.`}</td></tr>`;
    $('bond-count').textContent = '';
    return;
  }
  if (cfg.seg === 'corp') { pill.textContent = 'NSE · listed bonds'; pill.dataset.live = 'true'; }
  else { pill.textContent = india.open ? 'NDS-OM · open' : 'NDS-OM · closed'; pill.dataset.live = String(!!india.open); }
  const traded = cfg.seg === 'corp' ? (r) => r.tradedLakh > 0 : (r) => r.traded > 0;
  const rows = india.rows.map(r => ({ ...r, maturity: yearsTo(r.maturity) }));
  const shown = sortRows(cfg.tradedOnly ? rows.filter(traded) : rows, cfg.sort);
  $('bond-count').textContent = `${shown.length} of ${rows.length}`;
  if (!shown.length) { $('bond-body').innerHTML = `<tr><td colspan="${c.length}" class="scr-empty">No trades yet today.</td></tr>`; return; }
  const mat = (m) => (m == null ? '–' : `${m}y`);
  $('bond-body').innerHTML = shown.map(r => {
    if (cfg.seg === 'corp') {
      const fl = flash.get(r.symbol);
      return `<tr title="${esc(`${r.isin || ''} · ${r.agency || ''}`)}"><td class="l"><strong>${esc(r.symbol)}</strong></td><td class="l dim">${esc(r.rating || '–')}</td>
        <td>${f(r.coupon)}</td><td>${mat(r.maturity)}</td><td>${f(r.ltPrice)}</td>
        <td class="yld${fl ? ` flash-${fl}` : ''}">${r.ytm == null ? '–' : `${r.ytmApprox ? '≈' : ''}${r.ytm.toFixed(2)}`}</td>
        <td>${r.tradedLakh ? r.tradedLakh.toLocaleString('en-IN', { maximumFractionDigits: 1 }) : '–'}</td></tr>`;
    }
    const fl = flash.get(r.security);
    return `<tr data-symbol="${esc(r.id)}" tabindex="0"${r.id === state.currentSymbol ? ' class="is-current"' : ''} title="Chart ${esc(r.security)}"><td class="l"><strong>${esc(r.security)}</strong></td><td>${mat(r.maturity)}</td>
      <td class="yld${fl ? ` flash-${fl}` : ''}">${f(r.ltYield, 4)}</td><td>${f(r.ltPrice, 3)}</td>
      <td class="dim">${f(r.bidYield, 4)}</td><td class="dim">${f(r.askYield, 4)}</td>
      <td>${r.traded ? r.traded.toLocaleString('en-IN', { maximumFractionDigits: 0 }) : '–'}</td></tr>`;
  }).join('');
}

function renderTab() {
  document.querySelectorAll('#bond-tabs button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.tab === cfg.tab)));
  $('bond-global').hidden = cfg.tab !== 'global';
  $('bond-browse').hidden = cfg.tab !== 'global';
  $('bond-india').hidden = cfg.tab !== 'india';
  if (cfg.tab === 'global') {
    $('bond-status').textContent = 'real time · CNBC';
    $('bond-status').dataset.live = String(!!globalRows?.length);
    renderGlobal();
  } else renderIndia();
}

// ---------- loading ----------
async function load(force = false) {
  if (inFlight || !cfg.open) return;
  const which = cfg.tab;
  const every = which === 'global' ? POLL.global : cfg.seg === 'corp' ? POLL.corp : POLL.india;
  if (!force && Date.now() - lastFetch[which] < every) return;
  inFlight = true;
  const seg = cfg.seg;
  try {
    const res = await fetch(which === 'global' ? '/api/bonds/global' : `/api/bonds/india?segment=${seg}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const d = await res.json();
    lastFetch[which] = Date.now();
    if (which === 'global') {
      globalRows = d.rows;
      if (cfg.tab === 'global') renderTab();
    } else if (seg === cfg.seg) {
      const key = seg === 'corp' ? 'symbol' : 'security';
      const val = seg === 'corp' ? 'ytm' : 'ltYield';
      const flash = changedYields(prevYields, d.rows || [], key, val);
      prevYields = yieldMap(d.rows || [], key, val);
      india = d;
      if (cfg.tab === 'india') renderIndia(flash);
    }
  } catch (e) {
    if (which === 'global' && !globalRows) { globalRows = []; renderTab(); }
    if (which === 'india' && !india) { india = { available: false, rows: [] }; renderTab(); }
  } finally {
    inFlight = false;
  }
}

function setOpen(open) {
  cfg.open = open;
  panel.hidden = !open;
  $('bonds-btn').setAttribute('aria-pressed', String(open));
  save();
  if (open) {
    document.dispatchEvent(new CustomEvent('panel:open', { detail: 'bonds' }));
    renderTab();
    load(true);
  }
}

function chart(sym) {
  $('symbol-input').value = sym;   // switchSymbol() itself doesn't touch the search box
  switchSymbol(sym);
}

// ---------- wiring ----------
$('bonds-btn').addEventListener('click', () => setOpen(!cfg.open));
$('bonds-close').addEventListener('click', () => setOpen(false));
// The screener and this panel share the right edge: opening one closes the other.
document.addEventListener('panel:open', (e) => { if (e.detail !== 'bonds' && cfg.open) setOpen(false); });

$('bond-tabs').addEventListener('click', (e) => {
  const b = e.target.closest('button[data-tab]');
  if (!b || b.dataset.tab === cfg.tab) return;
  cfg.tab = b.dataset.tab;
  save();
  renderTab();
  load(true);
});
$('bond-global').addEventListener('click', (e) => {
  const pt = e.target.closest('button[data-symbol]');
  if (pt) { chart(pt.dataset.symbol); renderGlobal(); return; }
  const row = e.target.closest('button[data-country]');
  if (!row) return;
  const cc = row.dataset.country;
  cfg.expanded = cfg.expanded.includes(cc) ? cfg.expanded.filter(c => c !== cc) : [...cfg.expanded, cc];
  save();
  renderGlobal();
});
$('bond-q').addEventListener('input', renderGlobal);
// Enter charts the first match at the chosen maturity: "jap" + Enter = Japan 10Y.
$('bond-q').addEventListener('keydown', (e) => {
  if (e.key !== 'Enter' || !globalRows?.length) return;
  const first = browseCountries(globalRows, { q: e.target.value, tenor: cfg.tenor, sort: cfg.order })[0]?.countries[0];
  if (first) { chart(first.headline.symbol); renderGlobal(); }
});
$('bond-tenor').addEventListener('click', (e) => {
  const b = e.target.closest('button[data-tenor]');
  if (!b) return;
  cfg.tenor = b.dataset.tenor;
  save();
  renderGlobal();
});
$('bond-sort').addEventListener('click', (e) => {
  const b = e.target.closest('button[data-sort]');
  if (!b) return;
  cfg.order = b.dataset.sort;
  save();
  renderGlobal();
});
$('bond-seg').addEventListener('click', (e) => {
  const b = e.target.closest('button[data-seg]');
  if (!b || b.dataset.seg === cfg.seg) return;
  cfg.seg = b.dataset.seg;
  cfg.sort = { key: cfg.seg === 'corp' ? 'tradedLakh' : 'traded', dir: -1 };
  india = null;
  prevYields = null;
  $('bond-count').textContent = '';
  save();
  renderIndia();
  load(true);
});
$('bond-traded-only').addEventListener('change', (e) => { cfg.tradedOnly = e.target.checked; save(); renderIndia(); });
$('bond-head').addEventListener('click', (e) => {
  const b = e.target.closest('button[data-sort]');
  if (!b) return;
  const key = b.dataset.sort;
  const text = key === 'security' || key === 'symbol' || key === 'rating';
  cfg.sort = { key, dir: cfg.sort.key === key ? -cfg.sort.dir : (text ? 1 : -1) };
  save();
  renderIndia();
});
const openRow = (tr) => { if (tr?.dataset.symbol) { chart(tr.dataset.symbol); renderIndia(); } };
$('bond-body').addEventListener('click', (e) => openRow(e.target.closest('tr[data-symbol]')));
$('bond-body').addEventListener('keydown', (e) => {
  if (e.key !== 'Enter' && e.key !== ' ') return;
  e.preventDefault();
  openRow(e.target.closest('tr[data-symbol]'));
});

setInterval(visible(() => load()), 1000);
setOpen(cfg.open);
