// Insights › Calendar (:IPO): IPOs open now and coming up, how recent listings trade against their issue price, and
// corporate actions over the next 30 days (ex-dates for dividends, splits, bonuses, buybacks). Bloomberg's IPO / CACT
// on public data. Data: /api/ipos and /api/corp-actions (orazio/corp_calendar.py), prices from /api/quote.
import { esc } from './format.js';
import { redraw, registerTab } from './insights.js';
import { watchlistSymbols } from './insights-watchlist.js';

const PRICE_LISTINGS = 20;
const KINDS = { dividend: 'Dividend', split: 'Split', bonus: 'Bonus', buyback: 'Buyback', rights: 'Rights', demerger: 'Demerger', other: 'Other' };
let scope = 'all', kind = 'all';
const nf2 = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 });
const pct = (v) => (v === null || v === undefined ? '–' : `${v > 0 ? '+' : ''}${nf2.format(v)}%`);
const sign = (v) => (v > 0 ? 'up' : v < 0 ? 'down' : '');

const quote = (s) => fetch(`/api/quote?symbol=${encodeURIComponent(s)}`).then(r => (r.ok ? r.json() : null)).catch(() => null);

function issuesTable(issues) {
  if (!issues.length) return '<div class="empty-note">No IPO is open or announced on NSE right now.</div>';
  return `<table class="opt-table"><thead><tr><th style="text-align:left">Company</th><th>Status</th><th>Type</th><th>Opens</th><th>Closes</th><th>Price band</th><th>Lot</th><th>Subscribed</th></tr></thead><tbody>${
    issues.map(i => `<tr><td style="text-align:left"><strong>${esc(i.symbol)}</strong> <span class="ins-note">${esc(i.company)}</span></td>
      <td>${esc(i.status)}</td><td>${esc(i.kind || '–')}</td><td>${esc(i.open || '–')}</td><td>${esc(i.close || '–')}</td>
      <td>${esc(i.priceBand || '–')}</td><td>${i.lotSize ? nf2.format(i.lotSize) : '–'}</td><td>${i.subscribed === null ? '–' : `${nf2.format(i.subscribed)}x`}</td></tr>`).join('')}</tbody></table>`;
}

function listingsTable(listings, prices) {
  if (!listings.length) return '<div class="empty-note">No recent listings.</div>';
  return `<table class="opt-table"><thead><tr><th>Listed</th><th style="text-align:left">Company</th><th>Type</th><th>Issue price</th><th>Now</th><th>Since issue</th></tr></thead><tbody>${
    listings.map((l, i) => {
      const px = prices[i]?.price ?? null;
      const ret = px !== null && l.issuePrice ? (px / l.issuePrice - 1) * 100 : null;
      return `<tr data-symbol="${esc(l.chartSymbol)}" tabindex="0" role="button"><td style="white-space:nowrap">${esc(l.listed || '–')}</td>
        <td style="text-align:left"><strong>${esc(l.symbol)}</strong> <span class="ins-note">${esc(l.company)}</span></td><td>${esc(l.kind || '–')}</td>
        <td>${l.issuePrice === null ? '–' : nf2.format(l.issuePrice)}</td><td>${px === null ? '–' : nf2.format(px)}</td><td class="${sign(ret)}">${pct(ret)}</td></tr>`;
    }).join('')}</tbody></table>`;
}

function actionsTable(rows) {
  if (!rows.length) return '<div class="empty-note">No corporate actions match.</div>';
  return `<table class="opt-table"><thead><tr><th>Ex-date</th><th>Record</th><th style="text-align:left">Company</th><th>Action</th><th style="text-align:left">Detail</th></tr></thead><tbody>${
    rows.map(r => `<tr data-symbol="${esc(r.chartSymbol)}" tabindex="0" role="button"><td style="white-space:nowrap">${esc(r.date)}</td><td style="white-space:nowrap">${esc(r.record || '–')}</td>
      <td style="text-align:left"><strong>${esc(r.symbol)}</strong> <span class="ins-note">${esc(r.company)}</span></td><td>${esc(KINDS[r.kind])}</td>
      <td style="text-align:left"><span class="ins-note">${esc(r.subject)}</span></td></tr>`).join('')}</tbody></table>`;
}

async function render(body, ctx) {
  const [ipo, act] = await Promise.all([fetch('/api/ipos').then(r => r.json()), fetch('/api/corp-actions').then(r => r.json())]);
  const listings = ipo.listings.slice(0, PRICE_LISTINGS);
  const prices = await Promise.all(listings.map(l => quote(l.chartSymbol)));
  if (ctx.stale()) return;
  ctx.pill(ipo.available ? `${ipo.issues.length} IPOs open or upcoming` : 'NSE unavailable', ipo.available);
  const mine = new Set(watchlistSymbols());
  const rows = act.rows.filter(r => (scope === 'all' || mine.has(r.chartSymbol)) && (kind === 'all' || r.kind === kind));
  body.innerHTML = `<div class="ins-sec"><h3>IPOs open and upcoming</h3>${ipo.available ? issuesTable(ipo.issues) : '<div class="empty-note">NSE didn’t answer. It will retry.</div>'}</div>
    <div class="ins-sec"><h3>Recent listings against their issue price</h3>${listingsTable(listings, prices)}
      <p class="ins-note">Prices from Yahoo; some SME listings aren't on Yahoo and show '–'.</p></div>
    <div class="ins-sec"><h3>Corporate actions, next ${act.days || 30} days</h3><div class="ins-bar">
      <select class="select" id="cal-scope" aria-label="Which companies"><option value="all"${scope === 'all' ? ' selected' : ''}>All NSE</option><option value="watchlist"${scope === 'watchlist' ? ' selected' : ''}>My watchlist</option></select>
      <select class="select" id="cal-kind" aria-label="Which actions"><option value="all">Every action</option>${Object.entries(KINDS).map(([k, l]) => `<option value="${k}"${kind === k ? ' selected' : ''}>${esc(l)}</option>`).join('')}</select>
      <span class="ins-note">Buy before the ex-date to get the dividend, bonus or split.</span></div>
      ${act.available ? actionsTable(rows) : '<div class="empty-note">NSE didn’t answer. It will retry.</div>'}</div>`;
  body.querySelector('#cal-scope').addEventListener('change', (e) => { scope = e.target.value; redraw(); });
  body.querySelector('#cal-kind').addEventListener('change', (e) => { kind = e.target.value; redraw(); });
}

registerTab('calendar', 'Calendar', render, { pollMs: 600000, title: 'IPOs, recent listings, corporate actions ahead' });
