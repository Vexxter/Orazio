// Symbol search box + the central switchSymbol() used by search, the rail, and the futures toggle.
import { loadCandles, pollQuote } from './data.js';
import { savePrefs } from './prefs.js';
import { highlightRail } from './rail.js';
import { attachSearch } from './search-box.js';
import { $, state } from './state.js';

const symbolInput = $('symbol-input');
attachSearch({
  input: symbolInput, box: $('symbol-results'), idPrefix: 'sr', onChoose: switchSymbol,
  aliases: () => state.CONFIG.quickIndices || [],
});

// "/" jumps to search from anywhere (unless you're already typing in a field).
document.addEventListener('keydown', (e) => {
  if (e.key === '/' && !e.target.closest('input, select, textarea')) { e.preventDefault(); symbolInput.focus(); }
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
