// Insights › Watchlist: your symbols with live price and change, plus columns computed from daily history
// (52-week position, RSI, distance from the 50/200-day averages, volume vs its 20-day average) and NSE delivery
// %. Sortable; click a row to chart it. Stored in localStorage. Live quotes every 10 s.
import { withLive } from './alert-rules.js';
import { esc } from './format.js';
import { watchStats } from './insights-math.js';
import { historyBars, redraw, registerTab } from './insights.js';
import { nextSort, table } from './minichart.js';
import { state } from './state.js';

const KEY = 'orazio.watchlist.v1';
let list = ['NIFTY', 'BANKNIFTY', 'RELIANCE.NS', 'HDFCBANK.NS', 'ICICIBANK.NS', 'TCS.NS', 'INFY.NS', 'GOLD', 'BTC'];
let sort = null;
try {
  const saved = JSON.parse(localStorage.getItem(KEY) || 'null');
  if (Array.isArray(saved?.list)) list = saved.list;
  if (saved?.sort) sort = saved.sort;
} catch (e) { /* default list */ }
const save = () => { try { localStorage.setItem(KEY, JSON.stringify({ list, sort })); } catch (e) { /* not persisted */ } };
const nf = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 });
const pctCell = (v) => (v === null || v === undefined ? '–' : `${v > 0 ? '+' : ''}${v.toFixed(2)}%`);
const sign = (v) => (v > 0 ? 'up' : v < 0 ? 'down' : '');

const COLS = [
  { key: 'symbol', label: 'Symbol', fmt: (v) => `<strong>${esc(v)}</strong>` },
  { key: 'price', label: 'Price', fmt: (v) => (v === undefined ? '–' : nf.format(v)) },
  { key: 'chg', label: 'Chg %', fmt: pctCell, cls: sign },
  { key: 'fromHigh', label: 'From 52W high', fmt: pctCell, cls: (v) => (v > -2 ? 'up' : '') },
  { key: 'rsi', label: 'RSI 14', fmt: (v) => (v === null || v === undefined ? '–' : v.toFixed(1)), cls: (v) => (v >= 70 ? 'down' : v <= 30 ? 'up' : '') },
  { key: 'vsSma50', label: 'vs SMA50', fmt: pctCell, cls: sign },
  { key: 'vsSma200', label: 'vs SMA200', fmt: pctCell, cls: sign },
  { key: 'relVol', label: 'Vol × 20D', title: "Today's volume vs its 20-day average", fmt: (v) => (v ? `${v.toFixed(2)}×` : '–'), cls: (v) => (v >= 2 ? 'up' : '') },
  { key: 'delivPct', label: 'Deliv %', title: 'NSE delivery %, last session', fmt: (v) => (v === undefined || v === null ? '–' : v.toFixed(1)) },
  { key: 'remove', label: '', fmt: (_, r) => `<button type="button" class="btn icon wl-del" data-del="${esc(r.symbol)}" aria-label="Remove ${esc(r.symbol)}">✕</button>` },
];

let delivery = null, deliveryAt = 0;
async function deliveryMap() {
  if (!delivery || Date.now() - deliveryAt > 600000) {
    const d = await fetch('/api/delivery').then(r => (r.ok ? r.json() : null)).catch(() => null);
    delivery = new Map((d?.rows || []).map(r => [`${r.symbol}.NS`, r.delivPct]));
    deliveryAt = Date.now();
  }
  return delivery;
}

async function row(symbol, deliv) {
  const [bars, q] = await Promise.all([
    historyBars(symbol, '1Y').catch(() => []),
    fetch(`/api/quote?symbol=${encodeURIComponent(symbol)}`).then(r => (r.ok ? r.json() : null)).catch(() => null),
  ]);
  const live = q ? withLive(bars, q.price, q.marketTime || q.time || Date.now() / 1000) : bars;
  return { symbol, chartSymbol: symbol, price: q?.price, chg: q?.changePercent ?? null, delivPct: deliv.get(symbol), ...watchStats(live) };
}

async function render(body, ctx) {
  const deliv = await deliveryMap();
  const rows = await Promise.all(list.map(s => row(s, deliv)));
  if (ctx.stale()) return;
  ctx.pill(`${list.length} symbols · live`);
  body.innerHTML = `<div class="ins-bar"><input class="ins-input" id="wl-add" placeholder="Add symbol (RELIANCE.NS, SPX, IN10Y-IN…)" style="width:280px" aria-label="Add symbol">
      <button type="button" class="btn" id="wl-cur">Add ${esc(state.currentSymbol)}</button></div>
    <div class="ins-sec">${table(COLS, rows, sort)}</div>
    <p class="ins-note">Technical columns use daily bars with today's live price; delivery % is NSE's last published session.</p>`;
  const add = (s) => { s = s.trim().toUpperCase(); if (s && !list.includes(s)) { list = [...list, s]; save(); redraw(); } };
  body.querySelector('#wl-add').addEventListener('keydown', (e) => { if (e.key === 'Enter') add(e.target.value); });
  body.querySelector('#wl-cur').addEventListener('click', () => add(state.currentSymbol));
  body.querySelectorAll('[data-del]').forEach(b => b.addEventListener('click', (e) => { e.stopPropagation(); list = list.filter(s => s !== b.dataset.del); save(); redraw(); }));
  body.querySelectorAll('.th-sort').forEach(b => b.addEventListener('click', (e) => { e.stopPropagation(); sort = nextSort(sort, b.dataset.sort); save(); redraw(); }));
}

registerTab('watchlist', 'Watchlist', render, { pollMs: 10000, title: 'Your symbols with live and technical columns' });
