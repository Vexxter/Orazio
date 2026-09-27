// Boot sequence and the toolbar/footer controls that don't belong to any one feature.
import { applyStyle, priceSeriesByStyle, renderIndicators } from './chart.js';
import { loadCandles, pollQuote } from './data.js';
import { loadPrefs, savePrefs } from './prefs.js';
import { loadCas } from './cas-panel.js';
import { loadBreadth, loadConfig } from './rail.js';
import { applyTheme } from './theme.js';
import { $, state } from './state.js';
import { setIntervalUI } from './ui.js';

// Side-effect-only modules: each wires its own DOM listeners on import.
import './symbol.js';
import './futures.js';
import './options.js';
import './cas-feed.js';
import './cas-movement.js';
import './measure.js';
import './movers.js';

$('chart-state-retry').addEventListener('click', () => loadCandles());

document.querySelectorAll('#interval-seg button').forEach(btn => {
  btn.addEventListener('click', () => { setIntervalUI(btn.dataset.interval); loadCandles({ interval: btn.dataset.interval }); });
});
$('style').addEventListener('change', (e) => { applyStyle(e.target.value); savePrefs(); });
$('refresh').addEventListener('click', () => loadCandles());
for (const id of ['sma20', 'sma50', 'sma200', 'vol']) {
  $(id).addEventListener('change', () => { renderIndicators(); savePrefs(); });
}
document.querySelectorAll('#range-bar button').forEach(btn => {
  // Always request the finest interval as a baseline — the backend escalates to a
  // coarser one only if that range genuinely can't be served at 1m. Without this, a
  // range button reuses whatever interval a PREVIOUS wider range had auto-selected
  // (e.g. clicking 1D after YTD kept YTD's 1h bars instead of resetting to 1m).
  btn.addEventListener('click', () => loadCandles({ range: btn.dataset.range, interval: '1m' }));
});

// ---------- boot ----------
(function restorePrefs() {
  const p = loadPrefs();
  if (p.symbol) { state.currentSymbol = String(p.symbol).toUpperCase(); }
  $('symbol-input').value = state.currentSymbol;
  if (p.style && priceSeriesByStyle[p.style]) { $('style').value = p.style; applyStyle(p.style); }
  if (typeof p.sma20 === 'boolean') $('sma20').checked = p.sma20;
  if (typeof p.sma50 === 'boolean') $('sma50').checked = p.sma50;
  if (typeof p.sma200 === 'boolean') $('sma200').checked = p.sma200;
  if (typeof p.vol === 'boolean') $('vol').checked = p.vol;
  applyTheme(p.theme === 'light' ? 'light' : 'dark');
})();

loadConfig();
loadCas();
loadCandles();
pollQuote();
setInterval(() => { if (state.quotesInFlight === 0) pollQuote(); }, 2000);
setInterval(() => loadCandles({ preserveView: true }), 60000);
setInterval(loadBreadth, 5000);

$('theme-toggle').addEventListener('click', () => {
  applyTheme(document.documentElement.dataset.theme === 'light' ? 'dark' : 'light');
  savePrefs();
});
