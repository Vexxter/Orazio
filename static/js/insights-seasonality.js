// Insights › Seasonality: average month-on-month and weekday returns for any symbol over its full daily
// history (NIFTY: since 2007), with the median and the share of positive periods, so one huge month
// can't pass for a pattern. Math: insights-math.js monthlySeasonality()/weekdaySeasonality().
import { esc } from './format.js';
import { monthlySeasonality, weekdaySeasonality } from './insights-math.js';
import { historyBars, redraw, registerTab } from './insights.js';
import { bars } from './minichart.js';
import { state } from './state.js';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const DAYS = ['', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri'];
let symbol = null;
const f = (v, d = 2) => (v === null ? '–' : v.toFixed(d));
const cls = (v) => (v > 0 ? 'up' : v < 0 ? 'down' : '');

function tableOf(rows, label) {
  return `<table class="opt-table"><thead><tr><th></th><th>Avg %</th><th>Median %</th><th>% positive</th><th>Count</th></tr></thead><tbody>${
    rows.map(r => `<tr><td>${label(r)}</td><td class="${cls(r.avg)}">${f(r.avg)}</td><td class="${cls(r.median)}">${f(r.median)}</td><td>${f(r.up, 0)}</td><td>${r.n}</td></tr>`).join('')
  }</tbody></table>`;
}

async function render(body, ctx) {
  const sym = symbol || state.currentSymbol;
  const b = await historyBars(sym, 'ALL');
  if (ctx.stale()) return;
  if (b.length < 60) { body.innerHTML = `<div class="empty-note">Not enough daily history for ${esc(sym)}.</div>`; return; }
  const m = monthlySeasonality(b), w = weekdaySeasonality(b);
  const from = new Date(b[0].time * 1000).getFullYear();
  ctx.pill(`${esc(sym)} · since ${from}`);
  const thisMonth = new Date().getMonth();
  body.innerHTML = `<div class="ins-bar"><label>Symbol <input class="ins-input" id="seas-sym" value="${esc(sym)}" aria-label="Symbol"></label>
      <span class="ins-note">${b.length} daily bars · ${MONTHS[thisMonth]} has averaged ${f(m[thisMonth].avg)}% (${f(m[thisMonth].up, 0)}% of years up)</span></div>
    <div class="ins-grid2">
      <div class="ins-sec"><h3>Average return by month</h3>${bars({ labels: MONTHS, series: [{ name: 'avg %', values: m.map(r => r.avg), color: (v) => (v >= 0 ? 'var(--up)' : 'var(--down)') }] })}${tableOf(m, r => MONTHS[r.month])}</div>
      <div class="ins-sec"><h3>Average return by weekday</h3>${bars({ labels: DAYS.slice(1), series: [{ name: 'avg %', values: w.map(r => r.avg), color: (v) => (v >= 0 ? 'var(--up)' : 'var(--down)') }] })}${tableOf(w, r => DAYS[r.weekday])}</div>
    </div>
    <p class="ins-note">Month returns are month-end close to month-end close; weekday returns are close to close. Past seasonality is a tendency, not a forecast.</p>`;
  body.querySelector('#seas-sym').addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target.value.trim()) { symbol = e.target.value.trim().toUpperCase(); redraw(); } });
}

registerTab('seasonality', 'Seasonality', render, { title: 'Average returns by month and weekday', reset: () => { symbol = null; } });
