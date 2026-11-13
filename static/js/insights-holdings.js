// Insights › Holdings: a stock's promoter, public and employee-trust share by quarter, from NSE's shareholding filings.
// Follows the chart unless you type another symbol. Pledges sit in XBRL filings, so they aren't shown here.
import { esc } from './format.js';
import { redraw, registerTab } from './insights.js';
import { state } from './state.js';

let chosen = null;
const pct = (v) => (v === null || v === undefined ? '–' : `${v.toFixed(2)}%`);

async function render(body, ctx) {
  const symbol = (chosen || state.currentSymbol).toUpperCase();
  const isStock = !/^[\^]/.test(symbol) && (symbol.endsWith('.NS') || chosen);
  const d = isStock ? await fetch(`/api/shareholding?symbol=${encodeURIComponent(symbol)}`).then(r => r.json()) : { available: false, rows: [] };
  if (ctx.stale()) return;
  ctx.pill(d.asOf ? `Latest quarter ${d.asOf}` : '', !!d.asOf);
  const rows = [...d.rows].reverse();
  const first = d.rows[0], last = d.rows.at(-1);
  const drift = first && last && first !== last && first.promoter !== null && last.promoter !== null ? last.promoter - first.promoter : null;
  const note = !isStock ? 'Holdings are for NSE stocks. Chart one, or type a symbol above.' : `No shareholding filings found for ${symbol}.`;
  body.innerHTML = `<div class="ins-bar"><label>Symbol <input class="ins-input" id="hold-sym" value="${esc(chosen || (isStock ? symbol : ''))}" placeholder="RELIANCE" style="width:140px"></label></div>
    ${rows.length ? `<div class="ins-cards"><div class="ins-card"><div class="k">Promoter</div><div class="v">${pct(last.promoter)}</div><div class="s ${(last.promoterChange ?? 0) >= 0 ? 'up' : 'down'}">${last.promoterChange === undefined ? '' : `${last.promoterChange >= 0 ? '+' : ''}${last.promoterChange.toFixed(2)} pts on the quarter`}</div></div>
      <div class="ins-card"><div class="k">Public</div><div class="v">${pct(last.public)}</div></div>
      ${drift === null ? '' : `<div class="ins-card"><div class="k">Promoter since ${esc(first.period)}</div><div class="v ${drift >= 0 ? 'up' : 'down'}">${drift >= 0 ? '+' : ''}${drift.toFixed(2)} pts</div></div>`}</div>
      <table class="opt-table"><thead><tr><th>Quarter</th><th>Promoter</th><th>Change</th><th>Public</th><th>Employee trusts</th><th>Filed</th></tr></thead><tbody>${rows.map(r => `<tr><td>${esc(r.period)}</td><td>${pct(r.promoter)}</td><td class="${(r.promoterChange ?? 0) > 0 ? 'up' : (r.promoterChange ?? 0) < 0 ? 'down' : ''}">${r.promoterChange === undefined ? '–' : `${r.promoterChange >= 0 ? '+' : ''}${r.promoterChange.toFixed(2)}`}</td><td>${pct(r.public)}</td><td>${pct(r.employeeTrusts)}</td><td>${esc(r.filed || '–')}</td></tr>`).join('')}</tbody></table>` : `<div class="empty-note">${esc(note)}</div>`}`;
  body.querySelector('#hold-sym').addEventListener('change', (e) => { chosen = e.target.value.trim() || null; redraw(); });
}

registerTab('holdings', 'Holdings', render, { title: 'Shareholding trend from NSE filings', reset: () => { chosen = null; } });
