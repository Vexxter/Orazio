// Insights › Rotation: a relative rotation graph of NSE sector indices against NIFTY 50 on weekly closes.
// Right of 100 = beating NIFTY, above 100 = gaining on it; sectors usually rotate clockwise
// (Improving -> Leading -> Weakening -> Lagging). Trails show the last four weeks. Math: insights-math.js rrg().
import { esc } from './format.js';
import { quadrant, rrg } from './insights-math.js';
import { historyBars, registerTab } from './insights.js';
import { scatter } from './minichart.js';

// Yahoo tickers that serve daily history (checked 30 Oct 2026; Media/Healthcare/Oil & Gas don't).
const SECTORS = [
  ['Bank', 'BANKNIFTY'], ['IT', 'NIFTYIT'], ['Auto', '^CNXAUTO'], ['FMCG', '^CNXFMCG'], ['Pharma', '^CNXPHARMA'],
  ['Metal', '^CNXMETAL'], ['Realty', '^CNXREALTY'], ['Energy', '^CNXENERGY'], ['PSU Bank', '^CNXPSUBANK'],
  ['Infra', '^CNXINFRA'], ['Fin Services', 'NIFTY_FIN_SERVICE.NS'], ['PSE', '^CNXPSE'], ['Consumption', '^CNXCONSUM'],
];
const COLOR = { Leading: 'var(--up)', Weakening: 'var(--warn)', Lagging: 'var(--down)', Improving: 'var(--accent)' };

async function render(body, ctx) {
  const [bench, ...all] = await Promise.all([historyBars('NIFTY', '1Y'), ...SECTORS.map(([, s]) => historyBars(s, '1Y').catch(() => []))]);
  if (ctx.stale()) return;
  const points = SECTORS.map(([label, sym], i) => {
    const p = rrg(all[i], bench, 10, 4, 4);
    return p && { label, sym, ...p, q: quadrant(p.x, p.y) };
  }).filter(Boolean);
  ctx.pill(`${points.length} sectors · weekly`);
  const chart = scatter({
    points: points.map(p => ({ ...p, color: COLOR[p.q] })), cx: 100, cy: 100, w: 1100, h: 480,
    quadrants: [['Leading', 1, 1], ['Weakening', 1, 0], ['Lagging', 0, 0], ['Improving', 0, 1]],
  });
  const rows = [...points].sort((a, b) => b.x - a.x).map(p => `<tr data-symbol="${esc(p.sym)}" tabindex="0"><td>${esc(p.label)}</td><td style="color:${COLOR[p.q]}">${p.q}</td><td>${p.x.toFixed(2)}</td><td>${p.y.toFixed(2)}</td></tr>`).join('');
  body.innerHTML = `<div class="ins-sec">${chart}</div>
    <div class="ins-grid2"><div class="ins-sec"><table class="opt-table"><thead><tr><th>Sector</th><th>Quadrant</th><th>RS-Ratio</th><th>RS-Momentum</th></tr></thead><tbody>${rows}</tbody></table></div>
    <p class="ins-note">RS = sector ÷ NIFTY 50 (weekly closes). RS-Ratio = RS against its 10-week mean; RS-Momentum = RS-Ratio against its 4-week mean, both ×100. An open approximation of JdK's RRG, not the licensed formula. Click a sector to chart it.</p></div>`;
}

registerTab('rotation', 'Rotation', render, { title: 'Relative rotation graph of NSE sectors vs NIFTY 50' });
