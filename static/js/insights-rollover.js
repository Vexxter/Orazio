// Insights › Rollover: how much futures OI has moved to the next expiry, against the previous series at the
// same number of sessions before expiry, and the roll spread (next / near − 1). Data: /api/rollover
// (orazio/rollover.py, from NSE's F&O bhavcopy). Click a row to chart the underlying.
import { esc } from './format.js';
import { alignByExpiry } from './insights-math.js';
import { redraw, registerTab } from './insights.js';
import { legend, lines, nextSort, table } from './minichart.js';

let sort = { key: 'rollPct', dir: -1 };
// Index underlyings without a chart alias here get no click-through (their Yahoo tickers differ).
const INDEX_CHART = { NIFTY: 'NIFTY', BANKNIFTY: 'BANKNIFTY', FINNIFTY: null, MIDCPNIFTY: null, NIFTYNXT50: null };
const fmt = (v, d = 2) => (v === null || v === undefined ? '–' : v.toFixed(d));
const COLS = [
  { key: 'symbol', label: 'Symbol', fmt: (v) => `<strong>${esc(v)}</strong>` },
  { key: 'expiry', label: 'Near expiry' },
  { key: 'sessionsLeft', label: 'Sessions left' },
  { key: 'rollPct', label: 'Rollover %', fmt: (v) => fmt(v) },
  { key: 'prevRollPct', label: 'Prev series, same point', title: 'The previous series, the same number of sessions before its expiry', fmt: (v) => fmt(v) },
  { key: 'diff', label: 'vs prev', fmt: (v) => (v === null ? '–' : `${v > 0 ? '+' : ''}${v.toFixed(2)}`), cls: (v) => (v > 0 ? 'up' : v < 0 ? 'down' : '') },
  { key: 'prevFinalPct', label: 'Prev series final %', fmt: (v) => fmt(v) },
  { key: 'spreadPct', label: 'Roll spread %', title: 'Next-month close / near-month close − 1', fmt: (v) => fmt(v, 3), cls: (v) => (v < 0 ? 'down' : '') },
];

async function render(body, ctx) {
  const res = await fetch('/api/rollover');
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const d = await res.json();
  if (ctx.stale()) return;
  if (!d.available) { body.innerHTML = '<div class="empty-note">F&amp;O bhavcopy unavailable right now.</div>'; ctx.pill('Unavailable', false); return; }
  ctx.pill(`Bhavcopy ${d.date}`);
  const rows = d.rows.map(r => ({ ...r, chartSymbol: r.symbol in INDEX_CHART ? INDEX_CHART[r.symbol] : `${r.symbol}.NS`, diff: r.prevRollPct === null ? null : r.rollPct - r.prevRollPct }));
  const charts = Object.entries(d.series).map(([sym, s]) => {
    const { prev, cur, labels } = alignByExpiry(s.previous, s.current, s.sessionsLeft);
    const series = [
      { name: `Current (${s.currentExpiry})`, values: cur, color: 'var(--accent)' },
      { name: `Previous (${s.previousExpiry || '–'})`, values: prev, color: 'var(--text-faint)' },
    ];
    return `<div class="ins-sec"><h3>${esc(sym)} rollover % by sessions to expiry</h3>${legend(series)}${lines({ labels, series })}</div>`;
  }).join('');
  body.innerHTML = `<div class="ins-grid2">${charts}</div>
    <p class="ins-note">Rollover means most in expiry week; earlier in the series it mostly shows next-month positions opened early.</p>
    <div class="ins-sec ins-scroll">${table(COLS, rows, sort)}</div>`;
  body.querySelectorAll('.th-sort').forEach(b => b.addEventListener('click', (e) => { e.stopPropagation(); sort = nextSort(sort, b.dataset.sort); redraw(); }));
}

registerTab('rollover', 'Rollover', render, { title: 'Futures rollover vs the previous series, roll spread' });
