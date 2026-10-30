// Insights › Flows: FII/DII cash-market net buying (₹ Cr) and who holds what in index derivatives
// (participant-wise OI, contracts). Data: /api/flows (orazio/flows.py).
import { esc } from './format.js';
import { registerTab } from './insights.js';
import { bars, legend, lines } from './minichart.js';

const PARTY_COLOR = { FII: 'var(--accent)', DII: 'var(--warn)', Pro: 'var(--reb)', Client: 'var(--up)' };
const nf = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 });
const cr = (v) => (v === null || v === undefined ? '–' : `${v >= 0 ? '+' : '−'}₹${nf.format(Math.abs(v))} Cr`);
const short = (iso) => iso.slice(5).split('-').reverse().join('/');   // 2026-10-29 -> 29/10
const delta = (a, b) => (a === undefined || b === undefined ? '' : `<span class="${a - b >= 0 ? 'up' : 'down'}">${a - b >= 0 ? '+' : '−'}${nf.format(Math.abs(a - b))}</span>`);

function card(k, v, s, cls = '') {
  return `<div class="ins-card"><div class="k">${esc(k)}</div><div class="v ${cls}">${v}</div><div class="s">${s}</div></div>`;
}

async function render(body, ctx) {
  const res = await fetch('/api/flows');
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const { cash, oi } = await res.json();
  if (ctx.stale()) return;
  const last = cash.at(-1), lo = oi.at(-1), po = oi.at(-2);
  ctx.pill(lo ? `OI as of ${lo.date}` : 'No data', !!lo);

  const cards = [
    last ? card(`FII cash · ${last.date}`, cr(last.fii?.net), `buy ${nf.format(last.fii?.buy ?? 0)} · sell ${nf.format(last.fii?.sell ?? 0)}`, last.fii?.net >= 0 ? 'up' : 'down') : '',
    last ? card(`DII cash · ${last.date}`, cr(last.dii?.net), `buy ${nf.format(last.dii?.buy ?? 0)} · sell ${nf.format(last.dii?.sell ?? 0)}`, last.dii?.net >= 0 ? 'up' : 'down') : '',
    lo ? card('FII index futures long %', `${lo.FII.futIdxLongPct ?? '–'}%`, po ? `prev ${po.FII.futIdxLongPct}%` : '', lo.FII.futIdxLongPct >= 50 ? 'up' : 'down') : '',
    lo ? card('FII net index futures', nf.format(lo.FII.futIdxNet), po ? `Δ ${delta(lo.FII.futIdxNet, po.FII.futIdxNet)} contracts` : '', lo.FII.futIdxNet >= 0 ? 'up' : 'down') : '',
    lo ? card('Client net index puts', nf.format(lo.Client.putIdxNet), po ? `Δ ${delta(lo.Client.putIdxNet, po.Client.putIdxNet)}` : '', lo.Client.putIdxNet >= 0 ? 'up' : 'down') : '',
  ].join('');

  const cashSeries = [
    { name: 'FII net', values: cash.map(r => r.fii?.net ?? null), color: () => 'var(--accent)' },
    { name: 'DII net', values: cash.map(r => r.dii?.net ?? null), color: () => 'var(--warn)' },
  ];
  const cashChart = cash.length
    ? `${legend(cashSeries)}${bars({ labels: cash.map(r => short(r.date)), series: cashSeries, w: 1100, h: 200 })}${cash.length < 5 ? '<p class="ins-note">NSE publishes only the latest day; history builds up here from the first day this app ran.</p>' : ''}`
    : '<div class="empty-note">NSE hasn\'t published FII/DII figures yet (around 6 pm IST).</div>';

  const labels = oi.map(r => short(r.date));
  const partySeries = (key) => ['FII', 'DII', 'Pro', 'Client'].map(p => ({ name: p, values: oi.map(r => r[p][key]), color: PARTY_COLOR[p] }));
  const table = lo ? `<table class="opt-table"><thead><tr><th>Party</th><th title="Index futures, long − short contracts">Net idx fut</th><th>Δ day</th><th title="Share of index-futures position that is long">Long %</th><th>Net idx calls</th><th>Net idx puts</th><th>Net stock fut</th></tr></thead><tbody>${
    ['FII', 'DII', 'Pro', 'Client'].map(p => { const r = lo[p]; return `<tr><td>${p}</td><td class="${r.futIdxNet >= 0 ? 'up' : 'down'}">${nf.format(r.futIdxNet)}</td><td>${po ? delta(r.futIdxNet, po[p].futIdxNet) : '–'}</td><td>${r.futIdxLongPct ?? '–'}</td><td>${nf.format(r.callIdxNet)}</td><td>${nf.format(r.putIdxNet)}</td><td>${nf.format(r.futStkNet)}</td></tr>`; }).join('')
  }</tbody></table>` : '';

  body.innerHTML = `<div class="ins-cards">${cards}</div>
    <div class="ins-sec"><h3>Cash market net (₹ Cr) — FII vs DII</h3>${cashChart}</div>
    ${oi.length ? `<div class="ins-grid2">
      <div class="ins-sec"><h3>Net index futures by participant (contracts)</h3>${legend(partySeries('futIdxNet'))}${lines({ labels, series: partySeries('futIdxNet'), withZero: true })}</div>
      <div class="ins-sec"><h3>Index futures long % (FII)</h3>${lines({ labels, series: [{ name: 'FII long %', values: oi.map(r => r.FII.futIdxLongPct), color: 'var(--accent)' }] })}</div>
      <div class="ins-sec"><h3>Net index puts (long − short)</h3>${legend(partySeries('putIdxNet'))}${lines({ labels, series: partySeries('putIdxNet'), withZero: true })}</div>
      <div class="ins-sec"><h3>Net index calls (long − short)</h3>${legend(partySeries('callIdxNet'))}${lines({ labels, series: partySeries('callIdxNet'), withZero: true })}</div>
    </div>
    <div class="ins-sec"><h3>Participant-wise OI · ${esc(lo.date)}</h3>${table}<p class="ins-note">Source: NSE fao_participant_oi archive.</p></div>` : '<div class="empty-note">Participant OI unavailable right now.</div>'}`;
}

registerTab('flows', 'Flows', render, { title: 'FII/DII cash flows and participant-wise derivatives OI' });
