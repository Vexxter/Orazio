// Symbol search box + the central switchSymbol() used by search, the rail, and the futures toggle.
import { loadCandles, pollQuote } from './data.js';
import { savePrefs } from './prefs.js';
import { highlightRail } from './rail.js';
import { attachSearch } from './search-box.js';
import { $, state } from './state.js';

const symbolInput = $('symbol-input');
attachSearch({
  input: symbolInput, box: $('symbol-results'), idPrefix: 'sr', onChoose: switchSymbol,
  aliases: () => state.CONFIG.quickIndices || [], current: () => state.currentSymbol,
});

// "/" or Ctrl+K jumps to search; typing a letter or digit anywhere starts a search with it (as on TradingView).
// Not while typing in a field, or while a dialog is open.
document.addEventListener('keydown', (e) => {
  if ((e.target instanceof Element && e.target.closest('input, select, textarea, [contenteditable]')) || document.querySelector('.backdrop.open')) return;
  if ((e.key === '/' && !e.ctrlKey && !e.metaKey) || (e.key.toLowerCase() === 'k' && (e.ctrlKey || e.metaKey))) {
    e.preventDefault();
    symbolInput.focus();
  } else if (/^[a-z0-9]$/i.test(e.key) && !e.ctrlKey && !e.metaKey && !e.altKey) {
    e.preventDefault();
    symbolInput.focus();
    symbolInput.value = e.key.toUpperCase();
    symbolInput.dispatchEvent(new Event('input'));
  }
});

export function switchSymbol(symbol) {
  if (!symbol || symbol.toUpperCase() === state.currentSymbol) return;
  state.currentSymbol = symbol.toUpperCase();
  state.lastPolledPrice = null;
  state.tickChangedAt = 0;
  state.lineAreaUp = null;
  savePrefs();
  loadCandles();
  pollQuote();
  highlightRail();
}
