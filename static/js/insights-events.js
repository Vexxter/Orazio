// Insights › Event study: what a symbol did 1, 5, 10 and 20 sessions after a kind of event — RBI repo-rate
// hikes or cuts, big up/down days, opening gaps, or your own list of dates — with the average path, the hit
// rate and every event in a table. Math: insights-math.js eventStudy()/priceEvents().
import { esc } from './format.js';
import { dayKey, eventStudy, priceEvents } from './insights-math.js';
import { historyBars, redraw, registerTab } from './insights.js';
import { lines } from './minichart.js';
import { RBI_DECISIONS } from './rbi-dates.js';
import { state } from './state.js';

const RBI = {
  hike: RBI_DECISIONS.filter(([, bp]) => bp > 0).map(([d]) => d),
  cut: RBI_DECISIONS.filter(([, bp]) => bp < 0).map(([d]) => d),
};
const KINDS = {
  drop: 'Down day ≥ X%', rise: 'Up day ≥ X%', gapdown: 'Gap down ≥ X%', gapup: 'Gap up ≥ X%',
  hike: 'RBI rate hike', cut: 'RBI rate cut', custom: 'Custom dates',
};
const HORIZONS = [1, 5, 10, 20];
let symbol = null, kind = 'drop', threshold = 2, custom = '';
const f = (v, d = 2) => (v === null || v === undefined ? '–' : v.toFixed(d));
const cls = (v) => (v > 0 ? 'up' : v < 0 ? 'down' : '');
const isoDay = (iso) => dayKey(Date.parse(`${iso}T09:15:00+05:30`) / 1000);
const dayIso = (k) => new Date(k * 86400000).toISOString().slice(0, 10);

function eventDays(b) {
  if (kind in RBI) return RBI[kind].map(isoDay);
  if (kind === 'custom') return custom.split(/[\s,;]+/).filter(s => /^\d{4}-\d{2}-\d{2}$/.test(s)).map(isoDay);
  return priceEvents(b, kind, threshold);
}

async function render(body, ctx) {
  const sym = symbol || state.currentSymbol;
  const b = await historyBars(sym, 'ALL');
  if (ctx.stale()) return;
  const r = eventStudy(b, eventDays(b), HORIZONS);
  ctx.pill(`${esc(sym)} · ${r.events.length} events`);
  const stats = r.stats.map(s => `<div class="ins-card"><div class="k">+${s.h} session${s.h > 1 ? 's' : ''}</div><div class="v ${cls(s.avg)}">${f(s.avg)}%</div><div class="s">median ${f(s.median)}% · up ${f(s.up, 0)}% of ${s.n}</div></div>`).join('');
  const events = [...r.events].reverse().slice(0, 200).map(e => `<tr><td>${dayIso(e.day)}</td>${HORIZONS.map(h => `<td class="${cls(e.fwd[h])}">${f(e.fwd[h])}</td>`).join('')}</tr>`).join('');
  const needsX = ['drop', 'rise', 'gapdown', 'gapup'].includes(kind);
  body.innerHTML = `<div class="ins-bar">
      <label>Symbol <input class="ins-input" id="ev-sym" value="${esc(sym)}" aria-label="Symbol"></label>
      <label>Event <select class="select" id="ev-kind">${Object.entries(KINDS).map(([k, v]) => `<option value="${k}"${k === kind ? ' selected' : ''}>${v}</option>`).join('')}</select></label>
      ${needsX ? `<label>X % <input class="ins-input" id="ev-x" type="number" step="0.5" min="0.1" value="${threshold}" style="width:70px"></label>` : ''}
      ${kind === 'custom' ? `<input class="ins-input" id="ev-dates" style="flex:1;min-width:260px" placeholder="YYYY-MM-DD, YYYY-MM-DD, …" value="${esc(custom)}" aria-label="Event dates">` : ''}
    </div>
    ${r.events.length ? `<div class="ins-cards">${stats}</div>
    <div class="ins-grid2">
      <div class="ins-sec"><h3>Average path after the event (% from the event-day close)</h3>${lines({ labels: r.path.map((_, k) => `D+${k}`), series: [{ name: 'avg', values: r.path, color: 'var(--accent)' }], withZero: true })}</div>
      <div class="ins-sec ins-scroll"><table class="opt-table"><thead><tr><th>Event day</th>${HORIZONS.map(h => `<th>+${h}</th>`).join('')}</tr></thead><tbody>${events}</tbody></table></div>
    </div>` : '<div class="empty-note">No events of this kind in the history.</div>'}
    <p class="ins-note">Moves are measured from the close of the event day (an event on a holiday counts from the next session). RBI dates are announcement days.</p>`;
  const on = (id, ev, fn) => body.querySelector(id)?.addEventListener(ev, fn);
  on('#ev-sym', 'keydown', (e) => { if (e.key === 'Enter' && e.target.value.trim()) { symbol = e.target.value.trim().toUpperCase(); redraw(); } });
  on('#ev-kind', 'change', (e) => { kind = e.target.value; redraw(); });
  on('#ev-x', 'change', (e) => { const v = +e.target.value; if (v > 0) { threshold = v; redraw(); } });
  on('#ev-dates', 'change', (e) => { custom = e.target.value; redraw(); });
}

registerTab('events', 'Event study', render, { title: 'Forward returns after RBI decisions, big moves, gaps or your own dates', reset: () => { symbol = null; } });
