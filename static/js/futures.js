// Cash <-> futures toggle (only for symbols yfinance actually covers).
import { $, displayName, state } from './state.js';
import { switchSymbol } from './symbol.js';

const symbolInput = $('symbol-input');

export function futuresCounterpart(sym) {
  if (state.CONFIG.futuresMap[sym]) return { mode: 'cash', to: state.CONFIG.futuresMap[sym] };
  const cash = Object.keys(state.CONFIG.futuresMap).find(k => state.CONFIG.futuresMap[k] === sym);
  // Go back via the friendly alias (SPX) rather than the raw ticker (^GSPC).
  return cash ? { mode: 'futures', to: (state.CONFIG.futuresMeta[sym] || {}).alias || cash } : null;
}

export function updateFuturesToggle() {
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
