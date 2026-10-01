// Chart-legend pieces that need no DOM: the session-stats string and the per-bar volume lookup.
// Unit-tested in Node (tests/frontend/legend-html.test.mjs).
import { compactIN, esc, signed } from './format.js';

// Binary search for a bar's volume by time (bars are sorted ascending). undefined if absent.
export function volumeAt(bars, time) {
  let lo = 0, hi = bars.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (bars[mid].time === time) return bars[mid].volume;
    if (bars[mid].time < time) lo = mid + 1; else hi = mid - 1;
  }
  return undefined;
}

// 52-week range, 30-day change and the day's volume/value — only for the symbol they belong to,
// so a slow response can never show up under another chart.
export function statsHtml(stats, currentSymbol) {
  if (!stats || stats.symbol !== currentSymbol || !stats.available) return '';
  const has = (v) => v !== null && v !== undefined;
  const item = (k, v, cls = '') => `<span><span class="lg-k">${esc(k)}</span><span class="num ${cls}">${esc(v)}</span></span>`;
  const out = [];
  if (has(stats.yearHigh)) out.push(item('52W High', stats.yearHigh.toFixed(2)));
  if (has(stats.yearLow)) out.push(item('52W Low', stats.yearLow.toFixed(2)));
  if (has(stats.change30d)) out.push(item('30D', `${signed(stats.change30d)}%`, stats.change30d >= 0 ? 'up' : 'down'));
  if (has(stats.volume)) out.push(item('Day Vol', compactIN(stats.volume)));
  if (has(stats.value)) out.push(item('Day Value', `₹${(stats.value / 1e7).toLocaleString('en-IN', { maximumFractionDigits: 0 })} Cr`));
  return out.join('');
}
