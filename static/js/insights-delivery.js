// Insights › Delivery: stocks whose delivered quantity jumped against their own 20-session average (a move
// backed by positions changing hands, not intraday churn), plus the latest NSE bulk and block deals.
// Data: /api/delivery (orazio/delivery.py). Click a row to chart the stock.
import { esc } from './format.js';
import { redraw, registerTab } from './insights.js';
import { nextSort, table } from './minichart.js';

let sort = { key: 'delivX', dir: -1 };
let filter = 'all';
let dealSort = { key: 'qty', dir: -1 };
const nf = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 });
const signedCls = (v) => (v > 0 ? 'up' : v < 0 ? 'down' : '');
const pctFmt = (v) => (v === null || v === undefined ? '–' : `${v > 0 ? '+' : ''}${v.toFixed(2)}%`);

const COLS = [
  { key: 'symbol', label: 'Symbol', fmt: (v) => `<strong>${esc(v)}</strong>` },
  { key: 'close', label: 'Close', fmt: (v) => nf.format(v) },
  { key: 'pChange', label: 'Chg %', fmt: pctFmt, cls: signedCls },
  { key: 'turnoverCr', label: 'Turnover ₹Cr', fmt: (v) => nf.format(v) },
  { key: 'delivPct', label: 'Deliv %', title: 'Delivered / traded quantity, latest session' },
  { key: 'avgDelivPct', label: '20D avg %', fmt: (v) => v ?? '–' },
  { key: 'delivX', label: 'Deliv × avg', title: 'Delivered quantity vs its own 20-session average', fmt: (v) => (v ? `${v}×` : '–'), cls: (v) => (v >= 3 ? 'up' : '') },
];
const DEAL_COLS = [
  { key: 'kind', label: 'Type' }, { key: 'date', label: 'Date' }, { key: 'symbol', label: 'Symbol', fmt: (v) => `<strong>${esc(v)}</strong>` },
  { key: 'client', label: 'Client', fmt: (v) => esc(v || '–') }, { key: 'side', label: 'Side', cls: (v) => (v === 'BUY' ? 'up' : 'down') },
  { key: 'qty', label: 'Qty', fmt: (v) => nf.format(v) }, { key: 'price', label: 'Price', fmt: (v) => (v ? nf.format(v) : '–') },
  { key: 'valueCr', label: 'Value ₹Cr', fmt: (v) => (v ? nf.format(v) : '–') },
];
const FILTERS = { all: 'All', up: 'Up days', down: 'Down days', spike: '≥ 3× avg' };

async function render(body, ctx) {
  const res = await fetch('/api/delivery');
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const d = await res.json();
  if (ctx.stale()) return;
  ctx.pill(d.date ? `Session ${d.date}` : 'Unavailable', !!d.date);
  const rows = d.rows.filter(r => filter === 'all' || (filter === 'up' ? r.pChange > 0 : filter === 'down' ? r.pChange < 0 : r.delivX >= 3));
  const deals = d.deals.rows.map(r => ({ ...r, chartSymbol: r.symbol ? `${r.symbol}.NS` : null, valueCr: r.price ? Math.round((r.qty * r.price) / 1e5) / 100 : null }));
  body.innerHTML = `<div class="ins-bar"><div class="seg" role="group" aria-label="Filter">${Object.entries(FILTERS).map(([k, v]) => `<button type="button" data-f="${k}" aria-pressed="${k === filter}">${v}</button>`).join('')}</div>
      <span class="ins-note">${rows.length} stocks with turnover ≥ ₹5 Cr · baseline ${d.sessions} sessions · NSE sec_bhavdata (after ~6 pm)</span></div>
    <div class="ins-sec ins-scroll" data-t="deliv">${table(COLS, rows, sort)}</div>
    <div class="ins-sec"><h3>Bulk &amp; block deals · ${esc(d.deals.asOf || '–')}</h3><div class="ins-scroll" data-t="deals">${deals.length ? table(DEAL_COLS, deals, dealSort) : '<div class="empty-note">No deals reported.</div>'}</div></div>`;
  body.querySelectorAll('[data-f]').forEach(b => b.addEventListener('click', () => { filter = b.dataset.f; redraw(); }));
  body.querySelectorAll('[data-t] .th-sort').forEach(b => b.addEventListener('click', (e) => {
    e.stopPropagation();
    if (b.closest('[data-t]').dataset.t === 'deals') dealSort = nextSort(dealSort, b.dataset.sort); else sort = nextSort(sort, b.dataset.sort);
    redraw();
  }));
}

registerTab('delivery', 'Delivery & deals', render, { title: 'Delivery spikes vs 20-day average, bulk and block deals' });
