// Insights › Rates: (1) a yield curve you can scrub back through five years of daily closes, drawn against
// today's curve; (2) the spreads desks watch (US 10Y−2Y and 10Y−3M, India−US 10Y, Bund 10Y−2Y) with their
// history; (3) Indian corporate bond spreads over the G-sec curve by rating, live from NSE and CCIL.
// Data: /api/bonds/global (tenor list), /api/candles (CNBC/WGB daily yields), /api/bonds/india.
import { tenorMonths } from './bonds-policy.js';
import { combineBars } from './formula.js';
import { esc } from './format.js';
import { curveAt, dayKey, ratingSpreads } from './insights-math.js';
import { historyBars, redraw, registerTab } from './insights.js';
import { legend, lines } from './minichart.js';

const SPREADS = [
  ['US 10Y − 2Y', 'US10Y', 'US2Y'], ['US 10Y − 3M', 'US10Y', 'US3M'],
  ['India 10Y − US 10Y', 'IN10Y-IN', 'US10Y'], ['Bund 10Y − 2Y', 'DE10Y-DE', 'DE2Y-DE'],
];
let country = 'US';
let dayIndex = null;   // slider position; null = latest
const tenorOf = (sym) => (/^[A-Z]{2}(\d+[MY])/.exec(sym) || [])[1];
const bp = (v) => `${v >= 0 ? '+' : ''}${Math.round(v * 100)} bp`;
const isoOf = (k) => new Date(k * 86400000).toISOString().slice(0, 10);

async function curveSection(rows) {
  const tenors = rows.filter(r => r.country === country).sort((a, b) => tenorMonths(a.tenor) - tenorMonths(b.tenor));
  const all = await Promise.all(tenors.map(t => historyBars(t.symbol, '5Y').catch(() => [])));
  const keep = tenors.map((t, i) => [t, all[i]]).filter(([, b]) => b.length);
  const days = [...new Set(keep.flatMap(([, b]) => b.map(x => dayKey(x.time))))].sort((a, b) => a - b);
  return { keep, days };
}

function curveChart(keep, days, i) {
  const bars = keep.map(([, b]) => b);
  const then = curveAt(bars, days[i]), now = curveAt(bars, days.at(-1)), yearAgo = curveAt(bars, days[i] - 365);
  const series = [
    { name: `${isoOf(days[i])}`, values: then, color: 'var(--accent)' },
    { name: 'a year before that', values: yearAgo, color: 'var(--warn)' },
    { name: `latest (${isoOf(days.at(-1))})`, values: now, color: 'var(--text-faint)' },
  ];
  const t10 = keep.findIndex(([t]) => t.tenor === '10Y'), t2 = keep.findIndex(([t]) => t.tenor === '2Y');
  const slope = t10 >= 0 && t2 >= 0 && then[t10] !== null && then[t2] !== null ? `10Y − 2Y on that day: ${bp(then[t10] - then[t2])}` : '';
  return `${legend(series)}${lines({ labels: keep.map(([t]) => t.tenor), series, w: 1100, h: 230 })}<p class="ins-note">${slope}</p>`;
}

async function render(body, ctx) {
  const [glob, gsec, corp] = await Promise.all([
    fetch('/api/bonds/global').then(r => r.json()),
    fetch('/api/bonds/india?segment=cg').then(r => r.json()).catch(() => ({ rows: [] })),
    fetch('/api/bonds/india?segment=corp').then(r => r.json()).catch(() => ({ rows: [] })),
  ]);
  const { keep, days } = await curveSection(glob.rows);
  const spreadBars = await Promise.all(SPREADS.map(([, a, b]) => Promise.all([historyBars(a, '5Y'), historyBars(b, '5Y')]).then(([x, y]) => combineBars(x, y, '-', true)).catch(() => [])));
  if (ctx.stale()) return;
  ctx.pill('Daily closes · CNBC / WGB');
  const countries = [...new Map(glob.rows.map(r => [r.country, r.name])).entries()].filter(([c]) => glob.rows.filter(r => r.country === c).length >= 4);
  const i = dayIndex === null || dayIndex >= days.length ? days.length - 1 : dayIndex;

  const spreadCards = SPREADS.map(([name], k) => {
    const s = spreadBars[k];
    if (!s.length) return '';
    const last = s.at(-1).close, monthAgo = s[Math.max(0, s.length - 22)].close;
    return `<div class="ins-card"><div class="k">${esc(name)}</div><div class="v ${last >= 0 ? 'up' : 'down'}">${bp(last).replace('+', '')}</div><div class="s">1M ${bp(last - monthAgo)}</div></div>`;
  }).join('');
  const spreadCharts = SPREADS.map(([name], k) => {
    const s = spreadBars[k].filter((_, j, a) => j % 5 === 0 || j === a.length - 1);   // weekly-ish points keep the path light
    return s.length ? `<div class="ins-sec"><h3>${esc(name)} (pct points)</h3>${lines({ labels: s.map(x => isoOf(dayKey(x.time))), series: [{ name, values: s.map(x => x.close), color: 'var(--accent)' }], withZero: true })}</div>` : '';
  }).join('');

  const gcurve = gsec.rows.filter(r => r.maturity && r.ltYield).map(r => ({ years: (Date.parse(r.maturity) - Date.now()) / 31557600000, y: r.ltYield })).sort((a, b) => a.years - b.years);
  const corpRows = ratingSpreads(corp.rows.map(r => ({ rating: r.rating, ytm: r.ytm, years: (Date.parse(r.maturity) - Date.now()) / 31557600000 })), gcurve);
  const corpTable = corpRows.length ? `<table class="opt-table"><thead><tr><th>Rating</th><th>Bonds</th><th>Median YTM %</th><th>Median spread over G-sec</th></tr></thead><tbody>${
    corpRows.map(r => `<tr><td>${esc(r.rating)}</td><td>${r.n}</td><td>${r.ytm.toFixed(2)}</td><td>${Math.round(r.bp)} bp</td></tr>`).join('')}</tbody></table>`
    : '<div class="empty-note">No traded corporate bonds with a usable yield right now.</div>';

  body.innerHTML = `<div class="ins-cards">${spreadCards}</div>
    <div class="ins-sec"><div class="ins-bar"><h3 style="margin:0">Yield curve</h3>
      <select class="select" id="rates-country" aria-label="Country">${countries.map(([c, n]) => `<option value="${esc(c)}"${c === country ? ' selected' : ''}>${esc(n)}</option>`).join('')}</select>
      <input type="range" id="rates-day" min="0" max="${days.length - 1}" value="${i}" style="flex:1;min-width:240px" aria-label="Date on the curve">
      <span class="ins-note" id="rates-day-label">${days.length ? isoOf(days[i]) : ''}</span></div>
      <div id="rates-curve">${days.length ? curveChart(keep, days, i) : '<div class="empty-note">No daily history for this country.</div>'}</div></div>
    <div class="ins-grid2">${spreadCharts}</div>
    <div class="ins-sec"><h3>India corporate bonds: spread over G-secs by rating (live)</h3>${corpTable}
      <p class="ins-note">Corporate YTMs are approximate (annual coupons, no call dates); G-sec curve from CCIL NDS-OM last trades, interpolated at each bond's maturity. Medians, so one odd print can't skew a grade. AAA includes tax-free PSU bonds (HUDCO, NHAI, IRFC), which trade below G-secs, so its spread can be negative.</p></div>`;
  body.querySelector('#rates-country').addEventListener('change', (e) => { country = e.target.value; dayIndex = null; redraw(); });
  body.querySelector('#rates-day').addEventListener('input', (e) => {
    dayIndex = +e.target.value;
    body.querySelector('#rates-day-label').textContent = isoOf(days[dayIndex]);
    body.querySelector('#rates-curve').innerHTML = curveChart(keep, days, dayIndex);
  });
}

registerTab('rates', 'Rates', render, { title: 'Yield curve history, spread monitor, corporate bond spreads by rating' });
