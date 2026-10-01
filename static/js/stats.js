// Polls /api/stats for the current symbol and repaints the legend with it.
import { renderIndicators, updateLegend } from './chart.js';
import { state } from './state.js';

let inFlight = false;

// Yahoo's index bars have no volume; the server differences NSE's running total into
// per-bar volume. Fold it into the bars on screen (including live-built ones) and repaint
// the histogram only when something actually changed.
function mergeVolumeBars(bars) {
  let changed = false;
  for (const c of state.latestCandles) {
    const v = bars[c.time];
    if (v !== undefined && v !== c.volume) { c.volume = v; changed = true; }
  }
  if (changed) renderIndicators();
}

async function pollStats() {
  if (inFlight) return;
  inFlight = true;
  const symbol = state.currentSymbol;
  try {
    const res = await fetch(`/api/stats?symbol=${encodeURIComponent(symbol)}&interval=${state.currentInterval}`);
    if (!res.ok) throw new Error();
    const d = await res.json();
    // Drop a response for a symbol the user has already moved off.
    if (symbol === state.currentSymbol) {
      state.stats = { ...d, symbol };
      updateLegend(null);
      if (d.volumeBars) mergeVolumeBars(d.volumeBars);
    }
  } catch (e) { /* the legend simply shows no stats until the next poll succeeds */ }
  inFlight = false;
}

pollStats();
setInterval(pollStats, 3000);
