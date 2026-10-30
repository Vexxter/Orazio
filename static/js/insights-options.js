// Insights › Options: dealer gamma exposure by strike, the zero-gamma flip, call/put walls, the IV smile
// and term structure, and the day's OI build-up by strike. Data: /api/options/analytics
// (orazio/options_analytics.py). Follows the chart's symbol when it has NSE options, else NIFTY.
import { esc } from './format.js';
import { redraw, registerTab } from './insights.js';
import { bars, legend, lines } from './minichart.js';
import { state } from './state.js';

const UNDERLYINGS = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY'];
let symbol = null, expiry = null;
const nf = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 });
const card = (k, v, s = '', cls = '') => `<div class="ins-card"><div class="k">${esc(k)}</div><div class="v ${cls}">${v}</div><div class="s">${s}</div></div>`;

async function fetchFor(sym) {
  const q = new URLSearchParams({ symbol: sym });
  if (expiry) q.set('expiry', expiry);
  const res = await fetch(`/api/options/analytics?${q}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function render(body, ctx) {
  let d = await fetchFor(symbol || state.currentSymbol);
  if (!d.available && !symbol) d = await fetchFor('NIFTY');      // chart symbol has no options: fall back
  if (ctx.stale()) return;
  if (!d.available) { body.innerHTML = `<div class="empty-note">${esc(d.reason)}</div>`; ctx.pill('Unavailable', false); return; }
  ctx.pill(`As of ${d.asOf}`);
  const ks = d.strikes.map(s => String(s.strike));
  const gexSeries = [
    { name: 'Call GEX (₹ Cr / 1%)', values: d.strikes.map(s => s.callGex), color: () => 'var(--up)' },
    { name: 'Put GEX', values: d.strikes.map(s => s.putGex), color: () => 'var(--down)' },
  ];
  const doiSeries = [
    { name: 'Call OI change', values: d.strikes.map(s => s.ceDoi), color: () => 'var(--down)' },
    { name: 'Put OI change', values: d.strikes.map(s => s.peDoi), color: () => 'var(--up)' },
  ];
  const regime = d.flip === null ? '' : d.spot >= d.flip ? 'above flip: dealers dampen moves' : 'below flip: dealers amplify moves';
  const options = [...new Set([d.underlying, ...UNDERLYINGS])].map(u => `<option${u === d.underlying ? ' selected' : ''}>${esc(u)}</option>`).join('');
  body.innerHTML = `<div class="ins-bar">
      <label>Underlying <select class="select" data-k="symbol">${options}</select></label>
      <label>Expiry <select class="select" data-k="expiry">${d.expiries.map(e => `<option${e === d.expiry ? ' selected' : ''}>${esc(e)}</option>`).join('')}</select></label>
      <span class="ins-note">Spot ${nf.format(d.spot)} · lot ${d.lotSize} · ${d.daysToExpiry} days to expiry</span></div>
    <div class="ins-cards">
      ${card('Net GEX (₹ Cr per 1%)', nf.format(d.netGexCr), regime, d.netGexCr >= 0 ? 'up' : 'down')}
      ${card('Zero-gamma flip', d.flip === null ? '–' : nf.format(d.flip), d.flip === null ? 'no flip within ±6%' : `${nf.format(d.spot - d.flip)} pts from spot`)}
      ${card('Call wall', nf.format(d.callWall), 'largest call gamma')}
      ${card('Put wall', nf.format(d.putWall), 'largest put gamma')}
      ${card('Max pain', d.maxPain ? nf.format(d.maxPain) : '–')}
      ${card('PCR (OI)', d.pcr ? d.pcr.toFixed(2) : '–')}
      ${card('ATM IV', d.atmIv ? `${d.atmIv}%` : '–')}
    </div>
    <div class="ins-sec"><h3>Gamma exposure by strike</h3>${legend(gexSeries)}${bars({ labels: ks, series: gexSeries, w: 1100, h: 220 })}</div>
    <div class="ins-sec"><h3>OI change today by strike (contracts)</h3>${legend(doiSeries)}${bars({ labels: ks, series: doiSeries, w: 1100, h: 200 })}</div>
    <div class="ins-grid2">
      <div class="ins-sec"><h3>IV smile · ${esc(d.expiry)} (OTM side)</h3>${lines({ labels: d.smile.map(s => String(s.strike)), series: [{ name: 'IV', values: d.smile.map(s => s.iv), color: 'var(--accent)' }] })}</div>
      <div class="ins-sec"><h3>ATM IV term structure</h3>${lines({ labels: d.term.map(t => t.expiry.slice(0, 6)), series: [{ name: 'ATM IV', values: d.term.map(t => t.atmIv), color: 'var(--warn)' }] })}
        <table class="opt-table"><thead><tr><th>Expiry</th><th>Days</th><th>ATM IV</th></tr></thead><tbody>${d.term.map(t => `<tr><td>${esc(t.expiry)}</td><td>${t.days}</td><td>${t.atmIv ?? '–'}</td></tr>`).join('')}</tbody></table></div>
    </div>
    <p class="ins-note">GEX assumes dealers are long the calls and short the puts the public holds (r = 0, NSE's per-strike IV). It is a positioning estimate, not a measured dealer book.</p>`;
  body.querySelectorAll('select[data-k]').forEach(sel => sel.addEventListener('change', () => {
    if (sel.dataset.k === 'symbol') { symbol = sel.value; expiry = null; } else { symbol = d.underlying; expiry = sel.value; }
    redraw();
  }));
}

registerTab('options', 'Options', render, { pollMs: 30000, title: 'Gamma exposure, IV smile and term structure, OI build-up', reset: () => { symbol = null; expiry = null; } });
