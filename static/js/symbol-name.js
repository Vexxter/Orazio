// Fetches the company's real name for the symbol on the chart, so a bare ticker like
// 688185.SS or 457190.KS is recognisable. Shown in the chart legend.
import { updateLegend } from './chart.js';
import { state } from './state.js';

let requested = null;

async function load(symbol) {
  requested = symbol;
  try {
    const res = await fetch(`/api/name?symbol=${encodeURIComponent(symbol)}`);
    if (!res.ok) throw new Error();
    const d = await res.json();
    if (symbol !== state.currentSymbol) return;
    state.symbolName = { symbol, name: d.name };
    updateLegend(null);
  } catch (e) { requested = null; /* try again on the next tick */ }
}

setInterval(() => {
  if (state.currentSymbol !== requested) load(state.currentSymbol);
}, 1000);
