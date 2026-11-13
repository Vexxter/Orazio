// Insights › Risk: position sizer. Risk a fixed share of capital between entry and stop and get the quantity, rounded
// down to F&O lots when asked, with 1R/2R/3R targets. Entry starts at the chart's last price; capital and risk % are
// remembered in this browser. Maths: positionSize() in portfolio-math.js.
import { esc } from './format.js';
import { registerTab } from './insights.js';
import { positionSize } from './portfolio-math.js';
import { state } from './state.js';

const KEY = 'orazio.risk.v1';
let cfg = { capital: 1000000, riskPct: 1, useLots: false };
try { cfg = { ...cfg, ...JSON.parse(localStorage.getItem(KEY) || '{}') }; } catch (e) { /* defaults */ }
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(cfg)); } catch (e) { /* not persisted */ } };
const nf2 = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 });
const nf = (v) => nf2.format(v);
const nf0 = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 });
const card = (k, v, s = '', cls = '') => `<div class="ins-card"><div class="k">${esc(k)}</div><div class="v ${cls}">${v}</div><div class="s">${s}</div></div>`;
const field = (id, label, value, step = 'any') => `<label>${label} <input class="ins-input num" type="number" id="${id}" value="${value ?? ''}" step="${step}" min="0" style="width:120px"></label>`;

async function lotSize(symbol) {
  try {
    const d = await fetch(`/api/fno?symbol=${encodeURIComponent(symbol)}`).then(r => (r.ok ? r.json() : null));
    return d?.available ? d.lotSize : null;
  } catch (e) { return null; }
}

function result(body, lot) {
  const val = (id) => Number(body.querySelector(`#${id}`).value);
  cfg.capital = val('rk-cap'); cfg.riskPct = val('rk-pct'); cfg.useLots = !!body.querySelector('#rk-lots')?.checked;
  save();
  const r = positionSize({ capital: cfg.capital, riskPct: cfg.riskPct, entry: val('rk-entry'), stop: val('rk-stop'), lot: cfg.useLots && lot ? lot : 1 });
  const out = body.querySelector('#rk-out');
  if (r.error) { out.innerHTML = `<div class="empty-note">${esc(r.error)}</div>`; return; }
  const tooSmall = r.qty === 0 ? `<p class="ins-note down">Risk budget ₹${nf0.format(cfg.capital * cfg.riskPct / 100)} is less than one ${cfg.useLots ? 'lot' : 'share'} at this stop. Widen the risk %, or tighten the stop.</p>` : '';
  out.innerHTML = `<div class="ins-cards">
      ${card(r.side === 'long' ? 'Buy' : 'Sell short', nf0.format(r.qty), cfg.useLots && lot ? `${r.lots} lot${r.lots === 1 ? '' : 's'} of ${lot}` : 'shares', r.side === 'long' ? 'up' : 'down')}
      ${card('Money at risk', `₹${nf0.format(r.risk)}`, `₹${nf(r.riskPerUnit)} per share to the stop`, 'down')}
      ${card('Position value', `₹${nf0.format(r.value)}`, `${r.pctOfCapital.toFixed(1)}% of capital${r.pctOfCapital > 100 ? ': needs leverage' : ''}`)}
      ${r.targets.map(t => card(`${t.r}R target`, nf(t.price), `+₹${nf0.format(r.risk * t.r)}`, 'up')).join('')}</div>${tooSmall}`;
}

async function render(body, ctx) {
  const symbol = state.currentSymbol;
  const last = state.latestCandles.at(-1)?.close;
  const lot = await lotSize(symbol);
  if (ctx.stale()) return;
  ctx.pill(esc(symbol), false);
  body.innerHTML = `<div class="ins-bar">
      ${field('rk-cap', 'Capital ₹', cfg.capital, '10000')}${field('rk-pct', 'Risk %', cfg.riskPct, '0.25')}
      ${field('rk-entry', 'Entry', last ? +last.toFixed(2) : '')}${field('rk-stop', 'Stop', last ? +(last * 0.98).toFixed(2) : '')}
      ${lot ? `<label><input type="checkbox" id="rk-lots"${cfg.useLots ? ' checked' : ''}> F&amp;O lots (${lot})</label>` : ''}</div>
    <div id="rk-out"></div>
    <p class="ins-note">Size so the stop costs a fixed share of capital: a 1% risk survives a long losing streak. A stop below entry is a long, above it a short. Gaps can jump a stop, so the real loss can be larger. Entry starts at ${esc(symbol)}'s last price and the stop 2% under it.</p>`;
  body.querySelector('.ins-bar').addEventListener('input', () => result(body, lot));
  result(body, lot);
}

registerTab('risk', 'Risk', render, { title: 'Position sizer: quantity from capital, risk % and stop' });
