// Command line in the symbol search: type "NIFTY OPT", "RELIANCE SEAS", "BANKNIFTY 5M", "NIFTY CMP SPX" or
// ":FLOW" and press Enter. ":" anywhere on the page starts a command. Parsing is command-parse.js; this file
// resolves the symbol, charts it and opens the matching panel or Insights tab.
import { FUNCTIONS, parseCommand } from './command-parse.js';
import { loadCandles } from './data.js';
import { openInsights } from './insights.js';
import { pickTyped } from './search-box.js';
import { switchSymbol } from './symbol.js';
import { $, state } from './state.js';
import { setIntervalUI, toast } from './ui.js';

const input = $('symbol-input');

// "RELIANCE" -> "RELIANCE.NS" the same way typing it in search does; aliases and explicit tickers pass through.
async function resolve(sym) {
  const aliases = state.CONFIG.quickIndices || [];
  if (aliases.includes(sym) || /[\^.=/*+]/.test(sym) || /\s-\s/.test(sym)) return sym;
  const items = await fetch(`/api/search?q=${encodeURIComponent(sym)}`).then(r => (r.ok ? r.json() : [])).catch(() => []);
  return pickTyped(sym, items, aliases);
}

export async function runCommand(cmd) {
  const [action] = FUNCTIONS[cmd.fn];
  if (cmd.symbol) {
    const sym = await resolve(cmd.symbol);
    input.value = sym;
    switchSymbol(sym);
  }
  if (cmd.interval) { setIntervalUI(cmd.interval); loadCandles({ interval: cmd.interval }); }
  const [kind, target] = action.split(':');
  if (kind === 'tab') openInsights(target, { reset: true });
  else if (kind === 'btn') {
    const btn = document.getElementById(target);
    if (btn) btn.click(); else toast(`${cmd.fn} isn't available on this page`, 'error');
  } else if (kind === 'compare') {
    if (!cmd.arg) { toast('Compare needs a second symbol: NIFTY CMP SPX', 'error'); return; }
    const b = /[\s/*+]/.test(cmd.arg) ? cmd.arg : await resolve(cmd.arg);
    document.dispatchEvent(new CustomEvent('compare:pair', { detail: { a: state.currentSymbol, b } }));
  }
}

// Capture phase on the input itself: runs before the search box's own Enter handler, so a command never
// gets "resolved" as a ticker.
input.addEventListener('keydown', (e) => {
  const cmd = e.key === 'Enter' && parseCommand(input.value);
  if (!cmd) return;
  e.preventDefault();
  e.stopImmediatePropagation();
  input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));   // close the results list
  if (!cmd.symbol) input.value = state.currentSymbol;
  runCommand(cmd);
}, true);

document.addEventListener('keydown', (e) => {
  if (e.key !== ':' || (e.target instanceof Element && e.target.closest('input, select, textarea, [contenteditable]')) || document.querySelector('.backdrop.open')) return;
  e.preventDefault();
  input.focus();
  input.value = ':';
});
