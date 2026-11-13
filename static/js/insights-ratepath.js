// Insights › Rate path (:WIRP): how much the market expects RBI and the Fed to move rates over the next year, read
// from the bill curve against today's overnight rate. Bloomberg's WIRP on public data (bills, not futures/OIS).
// Data: /api/rate-path (orazio/rate_path.py).
import { esc } from './format.js';
import { registerTab } from './insights.js';
import { bars } from './minichart.js';

const nf = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 });
const bp = (v) => `${v > 0 ? '+' : ''}${nf.format(v)} bp`;
const card = (k, v, s = '', cls = '') => `<div class="ins-card"><div class="k">${esc(k)}</div><div class="v ${cls}">${v}</div><div class="s">${s}</div></div>`;

function bank(b) {
  if (!b.available) return `<div class="ins-sec"><h3>${esc(b.bank)}</h3><div class="empty-note">${esc(b.reason || 'Unavailable right now.')}</div></div>`;
  const last = b.windows.at(-1).vsAnchorBp;
  const series = [{ name: 'Priced move (bp)', values: b.windows.map(w => w.vsAnchorBp), color: (v) => (v >= 0 ? 'var(--down)' : 'var(--up)') }];
  return `<div class="ins-sec"><h3>${esc(b.bank)}</h3>
    <div class="ins-cards">${card('Priced over 12 months', bp(last), esc(b.verdict), last > 10 ? 'down' : last < -10 ? 'up' : '')}
      ${card('In 25 bp steps', `${b.steps12m > 0 ? '+' : ''}${nf.format(b.steps12m)}`, last >= 0 ? 'hikes' : 'cuts')}
      ${card('Anchor', `${nf.format(b.anchor)}%`, esc(b.anchorName || ''))}
      ${card('Bill basis taken out', bp(b.basisBp), 'gap between bills and the anchor')}</div>
    ${bars({ labels: b.windows.map(w => w.label), series, w: 700, h: 160 })}
    <table class="opt-table"><thead><tr><th>Window</th><th>Bill yield at end</th><th>Implied rate in window</th><th>vs anchor</th></tr></thead><tbody>${
      b.windows.map(w => `<tr><td>${esc(w.label)}</td><td>${nf.format(w.billYield)}%</td><td>${nf.format(w.forward)}%</td><td>${bp(w.vsAnchorBp)}</td></tr>`).join('')}</tbody></table>
    ${b.olderBills ? `<p class="ins-note">${b.olderBills} bills use their last recorded trade (earlier today or in the past week): Indian bills trade thinly.</p>` : ''}</div>`;
}

async function render(body, ctx) {
  const d = await fetch('/api/rate-path').then(r => r.json());
  if (ctx.stale()) return;
  ctx.pill('Bills live · anchors daily');
  body.innerHTML = `<div class="ins-grid2">${d.banks.map(bank).join('')}</div>
    <p class="ins-note">The forward rate between two bill maturities is what the market expects the short rate to average in that window, plus a small premium. Against the overnight anchor, the gap is the move priced in. Bloomberg reads futures and OIS instead (not free); bills carry supply and tax effects, so treat moves under 10 bp as nothing priced. Horizons, not meeting-by-meeting odds.</p>`;
}

registerTab('ratepath', 'Rate path', render, { pollMs: 60000, title: 'Rate moves priced in for RBI and the Fed' });
