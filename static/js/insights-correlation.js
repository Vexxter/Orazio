// Insights › Correlation: rolling correlation and beta of daily returns across a cross-asset basket (Indian
// indices, US, rates, FX, commodities). Click a cell to open the two symbols side by side in Compare.
// The basket is editable and remembered. Math: insights-math.js dailyReturns()/pairStats().
import { esc } from './format.js';
import { dailyReturns, isYield, pairStats } from './insights-math.js';
import { historyBars, redraw, registerTab } from './insights.js';
import { heat } from './minichart.js';

const KEY = 'orazio.corr.v1';
const DEFAULT = ['NIFTY', 'BANKNIFTY', 'NIFTYIT', 'SPX', 'NASDAQ', 'INR=X', 'US10Y', 'IN10Y-IN', 'BRENT', 'GOLD', 'BTC'];
const WINDOWS = { '3M': 63, '6M': 126, '1Y': 252, '3Y': 756 };
let basket = DEFAULT, win = '1Y', metric = 'corr';
try {
  const s = JSON.parse(localStorage.getItem(KEY) || 'null');
  if (Array.isArray(s?.basket) && s.basket.length) basket = s.basket;
  if (s?.win in WINDOWS) win = s.win;
  if (s?.metric === 'beta') metric = 'beta';
} catch (e) { /* defaults */ }
const save = () => { try { localStorage.setItem(KEY, JSON.stringify({ basket, win, metric })); } catch (e) { /* not persisted */ } };

// Keep only the last `n` returns of each series so every pair is measured over the same recent window.
const lastN = (m, n) => new Map([...m].slice(-n));

async function render(body, ctx) {
  const all = await Promise.all(basket.map(s => historyBars(s, '5Y').catch(() => [])));
  if (ctx.stale()) return;
  const rets = all.map((b, i) => lastN(dailyReturns(b, isYield(basket[i])), WINDOWS[win]));
  const cells = basket.map((_, i) => basket.map((__, j) => (i === j ? { corr: 1, beta: 1, n: rets[i].size } : pairStats(rets[i], rets[j]))));
  ctx.pill(`${win} daily returns`);
  const fmt = (v) => (v === null ? '–' : v.toFixed(2));
  const head = basket.map(s => `<th>${esc(s)}</th>`).join('');
  const rows = basket.map((a, i) => `<tr><td><strong>${esc(a)}</strong>${all[i].length ? '' : ' <span class="down" title="No data for this symbol">!</span>'}</td>${basket.map((b, j) => {
    const c = cells[i][j], v = c[metric];
    return `<td class="corr-cell" style="${metric === 'corr' ? heat(v, 1) : ''}" data-a="${esc(a)}" data-b="${esc(b)}" title="${esc(`${a} vs ${b}: corr ${fmt(c.corr)}, beta ${fmt(c.beta)} over ${c.n} shared days`)}">${fmt(v)}</td>`;
  }).join('')}</tr>`).join('');
  body.innerHTML = `<div class="ins-bar">
      <div class="seg" role="group" aria-label="Window">${Object.keys(WINDOWS).map(k => `<button type="button" data-w="${k}" aria-pressed="${k === win}">${k}</button>`).join('')}</div>
      <div class="seg" role="group" aria-label="Metric"><button type="button" data-m="corr" aria-pressed="${metric === 'corr'}">Correlation</button><button type="button" data-m="beta" aria-pressed="${metric === 'beta'}" title="Row's beta to the column">Beta</button></div>
      <input class="ins-input" id="corr-add" placeholder="Add symbol (e.g. RELIANCE.NS)" aria-label="Add symbol to the basket">
      <button type="button" class="btn" id="corr-reset">Reset basket</button></div>
    <div class="ins-sec" style="overflow:auto"><table class="opt-table corr-table"><thead><tr><th></th>${head}</tr></thead><tbody>${rows}</tbody></table></div>
    <p class="ins-note">Pairs use only days both markets traded (IST calendar). Beta reads "row moves β × column". Yields use daily changes in level, so a stock's beta to a yield is % per percentage point. Click a cell to compare the pair; right-click a row label to drop it.</p>`;
  body.querySelectorAll('[data-w]').forEach(b => b.addEventListener('click', () => { win = b.dataset.w; save(); redraw(); }));
  body.querySelectorAll('[data-m]').forEach(b => b.addEventListener('click', () => { metric = b.dataset.m; save(); redraw(); }));
  body.querySelector('#corr-add').addEventListener('keydown', (e) => {
    const v = e.target.value.trim().toUpperCase();
    if (e.key === 'Enter' && v && !basket.includes(v)) { basket = [...basket, v]; save(); redraw(); }
  });
  body.querySelector('#corr-reset').addEventListener('click', () => { basket = DEFAULT; save(); redraw(); });
  body.querySelectorAll('tbody td:first-child').forEach((td, i) => td.addEventListener('contextmenu', (e) => {
    e.preventDefault();
    basket = basket.filter((_, k) => k !== i); save(); redraw();
  }));
  body.querySelectorAll('.corr-cell').forEach(td => td.addEventListener('click', () => {
    document.dispatchEvent(new CustomEvent('compare:pair', { detail: { a: td.dataset.a, b: td.dataset.b } }));
  }));
}

registerTab('correlation', 'Correlation', render, { title: 'Correlation and beta matrix across assets' });
