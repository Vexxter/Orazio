// Insights › Journal: log trades (date, symbol, side, qty, price, setup, note) and see realised P&L matched FIFO,
// win rate and profit factor, P&L by setup, the equity curve and open positions marked to the live price.
// Trades also appear as Buy/Sell markers on the main chart (chart-events.js). Stored in localStorage; export CSV.
import { esc } from './format.js';
import { redraw, registerTab } from './insights.js';
import { fifo, stats } from './journal-math.js';
import { bars, lines } from './minichart.js';
import { state } from './state.js';
import { toast } from './ui.js';

const KEY = 'orazio.journal.v1';
export function loadTrades() {
  try { return JSON.parse(localStorage.getItem(KEY) || '[]'); } catch (e) { return []; }
}
function saveTrades(list) {
  try { localStorage.setItem(KEY, JSON.stringify(list)); } catch (e) { toast('Could not save the journal (storage full or blocked)', 'error'); }
  document.dispatchEvent(new CustomEvent('journal:changed'));
}
const nf = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 });
const money = (v) => (v === null || v === undefined ? '–' : `${v >= 0 ? '+' : '−'}${nf.format(Math.abs(v))}`);
const cls = (v) => (v > 0 ? 'up' : v < 0 ? 'down' : '');
const today = () => new Date(Date.now() + 19800000).toISOString().slice(0, 10);

function csv(trades) {
  const head = 'date,symbol,side,qty,price,setup,note';
  const q = (s) => `"${String(s ?? '').replace(/"/g, '""')}"`;
  return [head, ...trades.map(t => [t.date, t.symbol, t.side, t.qty, t.price, q(t.setup), q(t.note)].join(','))].join('\n');
}

async function render(body, ctx) {
  const trades = loadTrades();
  const { closed, open } = fifo(trades);
  const s = stats(closed);
  const quotes = await Promise.all(open.map(o => fetch(`/api/quote?symbol=${encodeURIComponent(o.symbol)}`).then(r => (r.ok ? r.json() : null)).catch(() => null)));
  if (ctx.stale()) return;
  ctx.pill(`${trades.length} trades`);
  const setups = [...new Set(trades.map(t => t.setup).filter(Boolean))];
  const card = (k, v, c = '') => `<div class="ins-card"><div class="k">${esc(k)}</div><div class="v ${c}">${v}</div></div>`;
  const openRows = open.map((o, i) => {
    const px = quotes[i]?.price, u = px ? (px - o.avg) * o.qty : null;
    return `<tr data-symbol="${esc(o.symbol)}" tabindex="0"><td>${esc(o.symbol)}</td><td>${o.qty > 0 ? 'Long' : 'Short'} ${nf.format(Math.abs(o.qty))}</td><td>${nf.format(o.avg)}</td><td>${px ? nf.format(px) : '–'}</td><td class="${cls(u)}">${money(u)}</td></tr>`;
  }).join('');
  body.innerHTML = `<div class="ins-bar">
      <input class="ins-input" id="jr-date" type="date" value="${today()}" aria-label="Date">
      <input class="ins-input" id="jr-sym" value="${esc(state.currentSymbol)}" style="width:120px" aria-label="Symbol">
      <select class="select" id="jr-side" aria-label="Side"><option value="buy">Buy</option><option value="sell">Sell</option></select>
      <input class="ins-input" id="jr-qty" type="number" min="0" step="any" placeholder="qty" style="width:80px" aria-label="Quantity">
      <input class="ins-input" id="jr-px" type="number" min="0" step="any" placeholder="price" style="width:100px" aria-label="Price">
      <input class="ins-input" id="jr-setup" list="jr-setups" placeholder="setup (breakout, fade…)" style="width:160px" aria-label="Setup">
      <datalist id="jr-setups">${setups.map(x => `<option value="${esc(x)}">`).join('')}</datalist>
      <input class="ins-input" id="jr-note" placeholder="note" style="flex:1;min-width:120px" aria-label="Note">
      <button type="button" class="btn primary" id="jr-add">Log trade</button>
      <button type="button" class="btn" id="jr-csv"${trades.length ? '' : ' disabled'}>Export CSV</button></div>
    <div class="ins-cards">${card('Realised P&L', money(s.total), cls(s.total))}${card('Closed trades', s.trades)}${card('Win rate', s.winRate === null ? '–' : `${s.winRate.toFixed(0)}%`)}${card('Avg win / loss', `${money(s.avgWin)} / ${money(s.avgLoss)}`)}${card('Profit factor', s.profitFactor === null ? '–' : s.profitFactor.toFixed(2))}</div>
    ${closed.length ? `<div class="ins-grid2">
      <div class="ins-sec"><h3>Equity curve (realised)</h3>${lines({ labels: s.equity.map(e => e.date), series: [{ name: 'P&L', values: s.equity.map(e => e.value), color: 'var(--accent)' }], withZero: true })}</div>
      <div class="ins-sec"><h3>P&amp;L by setup</h3>${bars({ labels: s.bySetup.map(x => x.setup), series: [{ name: 'P&L', values: s.bySetup.map(x => x.pnl), color: (v) => (v >= 0 ? 'var(--up)' : 'var(--down)') }] })}
        <table class="opt-table"><thead><tr><th>Setup</th><th>Trades</th><th>Win %</th><th>P&amp;L</th></tr></thead><tbody>${s.bySetup.map(x => `<tr><td>${esc(x.setup)}</td><td>${x.trades}</td><td>${x.winRate.toFixed(0)}</td><td class="${cls(x.pnl)}">${money(x.pnl)}</td></tr>`).join('')}</tbody></table></div>
    </div>` : ''}
    ${open.length ? `<div class="ins-sec"><h3>Open positions</h3><table class="opt-table"><thead><tr><th>Symbol</th><th>Position</th><th>Avg</th><th>Last</th><th>Unrealised</th></tr></thead><tbody>${openRows}</tbody></table></div>` : ''}
    <div class="ins-sec ins-scroll"><h3>Trades</h3>${trades.length ? `<table class="opt-table"><thead><tr><th>Date</th><th>Symbol</th><th>Side</th><th>Qty</th><th>Price</th><th>Setup</th><th style="text-align:left">Note</th><th></th></tr></thead><tbody>${
      [...trades].reverse().map(t => `<tr><td>${esc(t.date)}</td><td>${esc(t.symbol)}</td><td class="${t.side === 'buy' ? 'up' : 'down'}">${t.side}</td><td>${nf.format(t.qty)}</td><td>${nf.format(t.price)}</td><td>${esc(t.setup || '–')}</td><td style="text-align:left">${esc(t.note || '')}</td><td><button type="button" class="btn icon" data-del="${t.id}" aria-label="Delete trade">✕</button></td></tr>`).join('')
    }</tbody></table>` : '<div class="empty-note">No trades logged yet.</div>'}</div>`;

  body.querySelector('#jr-add').addEventListener('click', () => {
    const v = (id) => body.querySelector(id).value.trim();
    const qty = parseFloat(v('#jr-qty')), price = parseFloat(v('#jr-px'));
    if (!v('#jr-sym') || !(qty > 0) || !(price > 0) || !v('#jr-date')) { toast('Date, symbol, quantity and price are required', 'error'); return; }
    saveTrades([...trades, { id: Date.now(), date: v('#jr-date'), symbol: v('#jr-sym').toUpperCase(), side: v('#jr-side'), qty, price, setup: v('#jr-setup'), note: v('#jr-note') }]);
    redraw();
  });
  body.querySelector('#jr-csv').addEventListener('click', () => {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([csv(trades)], { type: 'text/csv' }));
    a.download = `orazio-journal-${today()}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  });
  body.querySelectorAll('[data-del]').forEach(b => b.addEventListener('click', (e) => {
    e.stopPropagation();
    saveTrades(trades.filter(t => String(t.id) !== b.dataset.del));
    redraw();
  }));
}

registerTab('journal', 'Journal', render, { title: 'Trade journal: P&L by setup, equity curve, open positions' });
