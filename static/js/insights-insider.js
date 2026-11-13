// Insights › Insider: open-market buys and sells by promoters, directors and key managers (SEBI PIT disclosures),
// netted per company so the stocks insiders are putting their own money into rise to the top. ESOPs, gifts,
// pledges and off-market transfers are left out. Data: /api/insider (orazio/insider.py).
import { esc } from './format.js';
import { redraw, registerTab } from './insights.js';

let everyone = false, view = 'companies';
const nf = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 });
const nf0 = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 });
const cr = (v) => `${v < 0 ? '−' : ''}₹${nf.format(Math.abs(v))} Cr`;
const sign = (v) => (v > 0 ? 'up' : v < 0 ? 'down' : '');

const companyRows = (list) => list.slice(0, 60).map(c => `<tr data-symbol="${esc(c.chartSymbol)}" tabindex="0" role="button">
  <td style="text-align:left"><strong>${esc(c.symbol)}</strong> <span class="ins-note">${esc(c.company)}</span></td>
  <td class="${sign(c.netCr)}">${cr(c.netCr)}</td><td>${cr(c.buyCr)}</td><td>${cr(c.sellCr)}</td>
  <td>${c.buyers} / ${c.sellers}</td><td style="white-space:nowrap">${esc(c.last)}</td></tr>`).join('');

const tradeRows = (list) => list.slice(0, 150).map(t => `<tr data-symbol="${esc(t.chartSymbol)}" tabindex="0" role="button">
  <td style="white-space:nowrap">${esc(t.date)}</td><td style="text-align:left"><strong>${esc(t.symbol)}</strong></td>
  <td style="text-align:left">${esc(t.name)} <span class="ins-note">${esc(t.category)}</span></td>
  <td class="${t.side === 'buy' ? 'up' : 'down'}">${t.side === 'buy' ? 'Buy' : 'Sell'}</td>
  <td>${nf0.format(t.qty)}</td><td>${cr(t.valueCr)}</td><td style="white-space:nowrap">${esc(t.filed || '–')}</td></tr>`).join('');

async function render(body, ctx) {
  const d = await fetch(`/api/insider${everyone ? '?all=1' : ''}`).then(r => r.json());
  if (ctx.stale()) return;
  if (!d.available) { ctx.pill('NSE unavailable', false); body.innerHTML = '<div class="empty-note">NSE didn\'t answer. It will retry.</div>'; return; }
  ctx.pill(`${d.rows.length} trades · last ${d.days} days`);
  const buyers = d.companies.filter(c => c.netCr > 0).length, sellers = d.companies.filter(c => c.netCr < 0).length;
  body.innerHTML = `<div class="ins-bar">
      <select class="select" id="ins-view" aria-label="View"><option value="companies"${view === 'companies' ? ' selected' : ''}>Net by company</option><option value="trades"${view === 'trades' ? ' selected' : ''}>Every trade</option></select>
      <label><input type="checkbox" id="ins-all"${everyone ? ' checked' : ''}> Include employees and relatives</label>
      <span class="ins-note">${buyers} companies net bought, ${sellers} net sold${d.latest ? ` · latest trade ${esc(d.latest)}` : ''}</span></div>
    ${!d.rows.length ? '<div class="empty-note">No open-market insider trades in this window.</div>' : view === 'companies'
      ? `<table class="opt-table"><thead><tr><th style="text-align:left">Company</th><th>Net</th><th>Bought</th><th>Sold</th><th>Buyers / sellers</th><th>Last trade</th></tr></thead><tbody>${companyRows(d.companies)}</tbody></table>`
      : `<table class="opt-table"><thead><tr><th>Traded</th><th style="text-align:left">Stock</th><th style="text-align:left">Who</th><th>Side</th><th>Shares</th><th>Value</th><th>Filed</th></tr></thead><tbody>${tradeRows(d.rows)}</tbody></table>`}
    <p class="ins-note">Open-market purchases and sales only. Insiders sell for many reasons; clustered buying by several insiders is the stronger signal. Click a row to chart it, then switch on <b>Events</b> to see the trades as markers.</p>`;
  body.querySelector('#ins-view').addEventListener('change', (e) => { view = e.target.value; redraw(); });
  body.querySelector('#ins-all').addEventListener('change', (e) => { everyone = e.target.checked; redraw(); });
}

registerTab('insider', 'Insider', render, { pollMs: 600000, title: 'Promoter and director open-market buys and sells (SEBI PIT)' });
