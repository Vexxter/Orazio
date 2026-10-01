// Left index rail: quick-access index list, grouped by region.
import { formatVolume } from './format.js';
import { $, esc, state } from './state.js';
import { toast } from './ui.js';
import { switchSymbol } from './symbol.js';

const symbolInput = $('symbol-input');

const INDEX_META = {
  NIFTY: ['Nifty 50', 'India'], BANKNIFTY: ['Bank Nifty', 'India'], NIFTYIT: ['Nifty IT', 'India'], SENSEX: ['BSE Sensex', 'India'], GIFTNIFTY: ['GIFT Nifty (futures)', 'India'],
  SPX: ['S&P 500', 'US'], NASDAQ: ['Nasdaq Composite', 'US'], DOWJONES: ['Dow Jones', 'US'],
  CRUDE: ['WTI Crude Oil', 'Commodities'], BRENT: ['Brent Crude', 'Commodities'], GOLD: ['Gold', 'Commodities'],
  SILVER: ['Silver', 'Commodities'], NATGAS: ['Natural Gas', 'Commodities'], COPPER: ['Copper', 'Commodities'],
  BTC: ['Bitcoin', 'Crypto'], ETH: ['Ethereum', 'Crypto'], BNB: ['BNB', 'Crypto'], SOL: ['Solana', 'Crypto'],
  XRP: ['XRP', 'Crypto'], DOGE: ['Dogecoin', 'Crypto'],
  KOSPI: ['KOSPI', 'Asia'], TAIEX: ['Taiwan Weighted', 'Asia'], CHINA: ['CSI 300', 'Asia'], SSE: ['Shanghai Composite', 'Asia'],
};
const RAIL_GROUPS = ['India', 'US', 'Commodities', 'Asia', 'Crypto', 'Other'];
// NIFTY/BANKNIFTY/NIFTYIT: free from NSE's own allIndices payload (orazio/cas.py
// breadth_from_all_indices). SENSEX/DOWJONES/SPX/CHINA: computed from their own
// constituents (orazio/constituents.py) since nobody publishes it for them. NASDAQ and
// TAIEX come from their exchanges (orazio/market_breadth.py); KOSPI counts the KOSPI 200.
// SSE is counted over every Shanghai A-share (orazio/global_movers.py).
const BREADTH_ALIASES = new Set(['NIFTY', 'BANKNIFTY', 'NIFTYIT', 'SENSEX', 'DOWJONES', 'SPX', 'CHINA', 'NASDAQ', 'KOSPI', 'TAIEX', 'SSE']);
// These count a different set than the name on the rail suggests, so say so on hover.
const BREADTH_BASIS = {
  NASDAQ: 'Counts the Nasdaq-100 stocks, not the whole Composite',
  KOSPI: 'Counts the KOSPI 200 stocks, not every KOSPI-listed stock',
  SSE: 'Shanghai-listed A-shares (main board + STAR)',
  TAIEX: 'All TWSE-listed stocks, from the exchange itself — published after the close, so this is the last finished session',
};

export function highlightRail() {
  // While on ES=F the rail should still show SPX as the active index.
  const cur = state.currentSymbol.endsWith('-FUT') ? state.currentSymbol.slice(0, -4) : state.currentSymbol;
  const active = (state.CONFIG.futuresMeta[cur] || {}).alias || cur;
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
      if (BREADTH_BASIS[row.alias]) el.title = BREADTH_BASIS[row.alias];
    }
  } catch (e) { /* breadth is a nicety on top of the rail; failing quietly is fine */ }
}
