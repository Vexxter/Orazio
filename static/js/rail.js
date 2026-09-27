// Left index rail: quick-access index list, grouped by region.
import { $, esc, state } from './state.js';
import { toast } from './ui.js';
import { switchSymbol } from './symbol.js';

const symbolInput = $('symbol-input');

const INDEX_META = {
  NIFTY: ['Nifty 50', 'India'], BANKNIFTY: ['Bank Nifty', 'India'], NIFTYIT: ['Nifty IT', 'India'], SENSEX: ['BSE Sensex', 'India'],
  SPX: ['S&P 500', 'US'], NASDAQ: ['Nasdaq Composite', 'US'], DOWJONES: ['Dow Jones', 'US'],
  KOSPI: ['KOSPI', 'Asia'], TAIEX: ['Taiwan Weighted', 'Asia'], CHINA: ['CSI 300', 'Asia'], SSE: ['Shanghai Composite', 'Asia'],
};
const RAIL_GROUPS = ['India', 'US', 'Asia', 'Other'];
// NIFTY/BANKNIFTY/NIFTYIT: free from NSE's own allIndices payload (orazio/cas.py
// breadth_from_all_indices). SENSEX/DOWJONES/SPX/CHINA: computed from their own
// constituents (orazio/constituents.py) since nobody publishes it for them. NASDAQ,
// KOSPI, TAIEX and SSE have no accurate free constituent list to compute it from, so
// they simply get no breadth line rather than a guessed one.
const BREADTH_ALIASES = new Set(['NIFTY', 'BANKNIFTY', 'NIFTYIT', 'SENSEX', 'DOWJONES', 'SPX', 'CHINA']);

export function highlightRail() {
  // While on ES=F the rail should still show SPX as the active index.
  const active = (state.CONFIG.futuresMeta[state.currentSymbol] || {}).alias || state.currentSymbol;
  document.querySelectorAll('.rail-item').forEach(b => {
    b.setAttribute('aria-current', String(b.dataset.sym === active));
  });
}

export async function loadConfig() {
  try {
    const res = await fetch('/api/config');
    if (!res.ok) throw new Error();
    state.CONFIG = await res.json();
  } catch (e) {
    toast('Couldn\'t load the index list — search still works', 'error');
    return;
  }
  const byGroup = Object.fromEntries(RAIL_GROUPS.map(g => [g, []]));
  for (const sym of state.CONFIG.quickIndices) byGroup[(INDEX_META[sym] || [null, 'Other'])[1]].push(sym);
  $('rail-groups').innerHTML = RAIL_GROUPS.filter(g => byGroup[g].length).map(g =>
    `<div class="rail-group"><div class="rail-title">${g}</div>${byGroup[g].map(sym =>
      `<button type="button" class="rail-item" data-sym="${esc(sym)}"><span class="rail-sym">${esc(sym)}</span><span class="rail-name">${esc((INDEX_META[sym] || [sym])[0])}</span>${
        BREADTH_ALIASES.has(sym) ? `<span class="rail-breadth" data-breadth-for="${esc(sym)}"></span>` : ''
      }</button>`
    ).join('')}</div>`).join('');
  $('rail-groups').addEventListener('click', (e) => {
    const btn = e.target.closest('.rail-item');
    if (!btn) return;
    symbolInput.value = btn.dataset.sym;
    switchSymbol(btn.dataset.sym);
  });
  highlightRail();
  loadBreadth();
}

function formatVolume(n) {
  if (n >= 1e9) return (n / 1e9).toFixed(2) + 'B';
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
  if (n >= 1e3) return (n / 1e3).toFixed(0) + 'K';
  return String(n);
}

// Live advances/declines for the indices NSE publishes it for (see BREADTH_ALIASES).
export async function loadBreadth() {
  try {
    const res = await fetch('/api/breadth');
    if (!res.ok) throw new Error();
    const d = await res.json();
    for (const row of d.indices) {
      const el = document.querySelector(`.rail-breadth[data-breadth-for="${row.alias}"]`);
      if (!el) continue;
      // volume is only present for the constituent-computed indices (SENSEX/DOWJONES/
      // SPX/CHINA) — it's the sum of their constituents' own volume, not a published
      // "index volume" (indices don't have one), hence the honest label on hover.
      const vol = row.volume ? `<span class="rail-vol" title="Combined volume of tracked constituents, today so far — not an official index figure">· ${formatVolume(row.volume)}</span>` : '';
      el.innerHTML = `<span class="up">▲${row.advances}</span> <span class="down">▼${row.declines}</span>${vol}`;
    }
  } catch (e) { /* breadth is a nicety on top of the rail; failing quietly is fine */ }
}
