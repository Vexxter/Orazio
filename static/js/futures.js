// Cash <-> futures toggle (only for symbols yfinance actually covers).
import { $, displayName, state } from './state.js';
import { updateFeedToggle } from './commodity-feed.js';
import { switchSymbol } from './symbol.js';

const symbolInput = $('symbol-input');

// NSE: NIFTY, BANKNIFTY and every stock with F&O contracts have a front-month future, charted as
// "<NAME>-FUT". The stock list comes from NSE itself (/api/fno/symbols).
const NSE_INDEX_FUTURES = { '^NSEI': 'NIFTY', '^NSEBANK': 'BANKNIFTY' };
fetch('/api/fno/symbols').then(r => r.json()).then(d => { state.fnoStocks = new Set(d.stocks); updateFuturesToggle(); }).catch(() => {});

export function futuresCounterpart(sym) {
  if (sym.endsWith('-FUT')) {
    const base = sym.slice(0, -4);
    return { mode: 'futures', to: base === 'NIFTY' || base === 'BANKNIFTY' ? base : `${base}.NS` };
  }
  if (NSE_INDEX_FUTURES[sym]) return { mode: 'cash', to: `${NSE_INDEX_FUTURES[sym]}-FUT` };
  if (sym.endsWith('.NS') && state.fnoStocks.has(sym.slice(0, -3)) && /^[A-Z0-9-]+$/.test(sym.slice(0, -3))) {
    return { mode: 'cash', to: `${sym.slice(0, -3)}-FUT` };
  }
  if (state.CONFIG.futuresMap[sym]) return { mode: 'cash', to: state.CONFIG.futuresMap[sym] };
  const cash = Object.keys(state.CONFIG.futuresMap).find(k => state.CONFIG.futuresMap[k] === sym);
  // Go back via the friendly alias (SPX) rather than the raw ticker (^GSPC).
  return cash ? { mode: 'futures', to: (state.CONFIG.futuresMeta[sym] || {}).alias || cash } : null;
}

export function updateFuturesToggle() {
  updateFeedToggle();
  const info = state.resolvedSymbol ? futuresCounterpart(state.resolvedSymbol) : null;
  $('futures-toggle').classList.toggle('shown', !!info);
  $('futures').checked = !!info && info.mode === 'futures';
  // Keep the search box readable when the symbol is a raw futures ticker.
  if (document.activeElement !== symbolInput && state.CONFIG.futuresMeta[state.currentSymbol]) symbolInput.value = displayName(state.currentSymbol);
}

$('futures').addEventListener('change', () => {
  const info = state.resolvedSymbol ? futuresCounterpart(state.resolvedSymbol) : null;
  if (info) { symbolInput.value = displayName(info.to); switchSymbol(info.to); }
});
