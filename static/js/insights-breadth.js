// Insights › Breadth: how much of the market is taking part. Advance/decline, % of stocks above their
// 50/200-day averages, near 52-week highs/lows, RSI extremes, fresh golden/death crosses, and the spread
// of today's % changes. Data: /api/screener rows (the same feed and technicals the Screener panel uses).
import { esc } from './format.js';
import { breadthSummary, histogram } from './insights-math.js';
import { redraw, registerTab } from './insights.js';
import { bars } from './minichart.js';

const UNIVERSES = { nifty50: 'NIFTY 50', bank: 'NIFTY BANK', nifty500: 'NIFTY 500', total: 'Total market' };
const EDGES = [-5, -3, -2, -1, -0.5, 0, 0.5, 1, 2, 3, 5];
let universe = 'nifty500';
const card = (k, v, s = '', cls = '') => `<div class="ins-card"><div class="k">${esc(k)}</div><div class="v ${cls}">${v}</div><div class="s">${s}</div></div>`;
const tone = (p) => (p === null ? '' : p >= 60 ? 'up' : p <= 40 ? 'down' : '');

async function render(body, ctx) {
  const res = await fetch(`/api/screener?universe=${universe}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const d = await res.json();
  if (ctx.stale()) return;
  ctx.pill(d.asOf ? `As of ${d.asOf}` : 'Unavailable', d.available);
  const s = breadthSummary(d.rows);
  const counts = histogram(d.rows.map(r => r.pChange), EDGES);
  const labels = ['< −5', ...EDGES.slice(0, -1).map((e, i) => `${e}…${EDGES[i + 1]}`), '> 5'];
  const tech = d.technicals === 'ready' ? '' : '<p class="ins-note">Daily technicals (averages, RSI) are still loading for this universe; those cards fill in on the next refresh.</p>';
  const crosses = (list, kind) => (list.length ? list.map(x => `<span class="scr-cross ${kind}">${esc(x)}</span>`).join(' ') : '<span class="dim">none</span>');
  body.innerHTML = `<div class="ins-bar"><div class="seg" role="group" aria-label="Universe">${Object.entries(UNIVERSES).map(([k, v]) => `<button type="button" data-u="${k}" aria-pressed="${k === universe}">${v}</button>`).join('')}</div>
      <span class="ins-note">${s.total} stocks</span></div>
    <div class="ins-cards">
      ${card('Advance / decline', `<span class="up">${s.advances}</span> / <span class="down">${s.declines}</span>`, `ratio ${s.declines ? (s.advances / s.declines).toFixed(2) : '–'}`)}
      ${card('Above 50-day avg', s.above50 === null ? '–' : `${s.above50}%`, 'short-term participation', tone(s.above50))}
      ${card('Above 200-day avg', s.above200 === null ? '–' : `${s.above200}%`, 'long-term trend', tone(s.above200))}
      ${card('Within 2% of 52W high', s.nearHigh, `vs ${s.nearLow} within 2% of low`, s.nearHigh >= s.nearLow ? 'up' : 'down')}
      ${card('RSI ≥ 70 / ≤ 30', `<span class="down">${s.overbought}</span> / <span class="up">${s.oversold}</span>`, 'overbought / oversold')}
    </div>
    ${tech}
    <div class="ins-sec"><h3>Today's % change: how many stocks in each bucket</h3>${bars({ labels, series: [{ name: 'stocks', values: counts, color: () => 'var(--accent)' }], w: 1100, h: 200 })}</div>
    <div class="ins-sec"><h3>50/200-day crosses in the last 5 sessions</h3><p>Golden: ${crosses(s.golden, 'golden')}</p><p>Death: ${crosses(s.death, 'death')}</p></div>`;
  body.querySelectorAll('[data-u]').forEach(b => b.addEventListener('click', () => { universe = b.dataset.u; redraw(); }));
}

registerTab('breadth', 'Breadth', render, { pollMs: 15000, title: 'Advance/decline, % above 50/200-day averages, 52-week highs/lows' });
