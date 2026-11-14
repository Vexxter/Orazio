// Insights › Macro: this week's scheduled releases (times in IST, filter by impact and currency) and Indian
// banking liquidity from RBI's daily money-market release: net liquidity, overnight rates, SDF and MSF use.
// Data: /api/macro (orazio/macro.py).
import { esc } from './format.js';
import { redraw, registerTab } from './insights.js';
import { bars, legend, lines } from './minichart.js';

const IMPACTS = { High: 'High', Medium: 'High + Medium', All: 'All' };
let impact = 'High', ccy = 'ALL';
const ist = new Intl.DateTimeFormat('en-IN', { timeZone: 'Asia/Kolkata', weekday: 'short', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false });
const istDay = new Intl.DateTimeFormat('en-IN', { timeZone: 'Asia/Kolkata', weekday: 'long', day: '2-digit', month: 'short' });
const nf = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 });
const short = (iso) => iso.slice(5).split('-').reverse().join('/');

function calendarHtml(rows) {
  const now = Date.now();
  const keep = rows.filter(r => (impact === 'All' || r.impact === 'High' || (impact === 'Medium' && r.impact === 'Medium')) && (ccy === 'ALL' || r.country === ccy))
    .sort((a, b) => Date.parse(a.time) - Date.parse(b.time));
  if (!keep.length) return '<div class="empty-note">No events match.</div>';
  let lastDay = '';
  return `<table class="opt-table"><thead><tr><th>Time (IST)</th><th>Ccy</th><th>Event</th><th>Impact</th><th>Forecast</th><th>Previous</th></tr></thead><tbody>${keep.map(r => {
    const t = Date.parse(r.time), day = istDay.format(t);
    const head = day !== lastDay ? `<tr class="cal-day"><td colspan="6">${esc(day)}</td></tr>` : '';
    lastDay = day;
    const soon = t > now && t - now < 86400000;
    return `${head}<tr class="${t < now ? 'dim' : soon ? 'cal-soon' : ''}"><td>${esc(ist.format(t).split(', ').pop())}</td><td>${esc(r.country)}</td><td style="text-align:left">${esc(r.title)}</td><td class="${r.impact === 'High' ? 'down' : ''}">${esc(r.impact)}</td><td>${esc(r.forecast || '–')}</td><td>${esc(r.previous || '–')}</td></tr>`;
  }).join('')}</tbody></table>`;
}

async function render(body, ctx) {
  const res = await fetch('/api/macro');
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const { calendar, liquidity } = await res.json();
  if (ctx.stale()) return;
  const last = liquidity.at(-1);
  ctx.pill(last ? `RBI data for ${last.date}` : 'Calendar only', !!last);
  const ccys = ['ALL', ...new Set(calendar.map(r => r.country))].sort();
  const card = (k, v, s = '', cls = '') => `<div class="ins-card"><div class="k">${esc(k)}</div><div class="v ${cls}">${v}</div><div class="s">${s}</div></div>`;
  const labels = liquidity.map(r => short(r.date));
  const rateSeries = [
    { name: 'Call money', values: liquidity.map(r => r.call ?? null), color: 'var(--accent)' },
    { name: 'TREPS', values: liquidity.map(r => r.treps ?? null), color: 'var(--warn)' },
    { name: 'Market repo', values: liquidity.map(r => r.repo ?? null), color: 'var(--reb)' },
  ];
  body.innerHTML = `${last ? `<div class="ins-cards">
      ${card('Net liquidity (₹ Cr)', nf.format(last.net), last.net >= 0 ? 'RBI injecting: system short of cash' : 'RBI absorbing: system has surplus cash', last.net >= 0 ? 'down' : 'up')}
      ${card('Call money (WAR)', `${last.call}%`, `TREPS ${last.treps}% · repo ${last.repo}%`)}
      ${card('SDF parked (₹ Cr)', nf.format(last.sdf ?? 0), 'banks lending surplus to RBI')}
      ${card('MSF borrowed (₹ Cr)', nf.format(last.msf ?? 0), 'banks borrowing at the penal rate', (last.msf || 0) > 10000 ? 'down' : '')}
    </div>
    <div class="ins-grid2">
      <div class="ins-sec"><h3>Net liquidity injected (+) / absorbed (−), ₹ Cr</h3>${bars({ labels, series: [{ name: 'net', values: liquidity.map(r => r.net), color: (v) => (v >= 0 ? 'var(--down)' : 'var(--up)') }] })}</div>
      <div class="ins-sec"><h3>Overnight rates (%)</h3>${legend(rateSeries)}${lines({ labels, series: rateSeries })}</div>
    </div>${liquidity.length < 20 ? '<p class="ins-note">RBI lists only recent releases; liquidity history builds up here day by day.</p>' : ''}` : ''}
    <div class="ins-sec"><div class="ins-bar"><h3 style="margin:0">Economic calendar</h3>
      <div class="seg" role="group" aria-label="Impact">${Object.entries(IMPACTS).map(([k, v]) => `<button type="button" data-i="${k}" aria-pressed="${k === impact}">${v}</button>`).join('')}</div>
      <select class="select" id="cal-ccy" aria-label="Currency">${ccys.map(c => `<option${c === ccy ? ' selected' : ''}>${esc(c)}</option>`).join('')}</select>
      <span class="ins-note">ForexFactory feed: forecasts and previous values, no actuals; no INR events.</span></div>
      ${calendarHtml(calendar)}</div>`;
  body.querySelectorAll('[data-i]').forEach(b => b.addEventListener('click', () => { impact = b.dataset.i; redraw(); }));
  body.querySelector('#cal-ccy').addEventListener('change', (e) => { ccy = e.target.value; redraw(); });
}

registerTab('macro', 'Macro', render, { title: 'Economic calendar and RBI liquidity' });
