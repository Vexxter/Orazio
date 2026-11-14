// Insights › Option backtest: an option strategy on NSE's end-of-day bhavcopy, entered before each expiry and held to
// it, net of charges. Strikes count from at-the-money. Engine and limits: orazio/option_backtest.py.
import { esc } from './format.js';
import { redraw, registerTab } from './insights.js';
import { state } from './state.js';
import { toast } from './ui.js';

const KEY = 'orazio.optbt.v1';
const PRESETS = { 'Short straddle': 'SELL CE 0, SELL PE 0', 'Short strangle': 'SELL CE 2, SELL PE -2', 'Iron condor': 'SELL CE 2, BUY CE 4, SELL PE -2, BUY PE -4', 'Long straddle': 'BUY CE 0, BUY PE 0', 'Bull call spread': 'BUY CE 0, SELL CE 2' };
let cfg = { underlying: 'NIFTY', legs: PRESETS['Short straddle'], expiry: 'weekly', entry: 1, months: 3, lots: 1, slippagePct: 0.5, brokeragePerOrder: 20 };
try { cfg = { ...cfg, ...JSON.parse(localStorage.getItem(KEY) || '{}') }; } catch (e) { /* defaults */ }
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(cfg)); } catch (e) { /* not persisted */ } };
let result = null, running = false;
const nf = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 });
const money = (v) => (v === null || v === undefined ? '–' : `₹${nf.format(v)}`);
const sign = (v) => (v > 0 ? 'up' : v < 0 ? 'down' : '');
const card = (k, v, s = '', cls = '') => `<div class="ins-card"><div class="k">${esc(k)}</div><div class="v ${cls}">${v}</div><div class="s">${s}</div></div>`;

function resultHtml(r) {
  if (!r) return '<div class="empty-note">Pick a strategy and run it. The first run for an underlying downloads NSE\'s daily files, so it can take a few runs to finish.</div>';
  const s = r.summary;
  const reasons = {};
  r.skipped.forEach(x => { reasons[x.reason] = (reasons[x.reason] || 0) + 1; });
  const skipped = Object.entries(reasons).map(([k, n]) => `${n}: ${k}`).join(' · ');
  return `${r.downloading ? `<p class="ins-note down">${r.downloading} days are still downloading, so this is partial. Run it again in a minute.</p>` : ''}
    ${r.note ? `<div class="empty-note">${esc(r.note)}</div>` : ''}
    ${s.trades ? `<div class="ins-cards">${card('Net P&L', money(s.netPnl), `${s.trades} trades, ${esc(r.from)} to ${esc(r.asOf)}`, sign(s.netPnl))}
      ${card('Costs', money(s.costs), `gross ${money(s.grossPnl)}`)}
      ${card('Win rate', `${s.winRate}%`, `avg win ${money(s.avgWin)} · avg loss ${money(s.avgLoss)}`)}
      ${card('Worst trade', money(s.worstTrade), `best ${money(s.bestTrade)}`, 'down')}
      ${card('Max drawdown', money(s.maxDrawdown), 'on closed trades', 'down')}</div>
    <table class="opt-table"><thead><tr><th>Entered</th><th>Expiry</th><th>Spot</th><th>At expiry</th><th style="text-align:left">Legs: entry → settle</th><th>Gross</th><th>Costs</th><th>Net</th></tr></thead><tbody>${
      [...r.trades].reverse().map(t => `<tr><td>${esc(t.entered)}</td><td>${esc(t.expiry)}</td><td>${nf.format(t.spot)}</td><td>${nf.format(t.finalSpot)}</td><td style="text-align:left">${t.legs.map(l => `${esc(l.side)} ${nf.format(l.strike)} ${esc(l.type)} ×${l.qty}: ${l.entry} → ${l.settle}`).join('<br>')}</td><td class="${sign(t.gross)}">${money(t.gross)}</td><td>${money(t.costs)}</td><td class="${sign(t.net)}">${money(t.net)}</td></tr>`).join('')
    }</tbody></table>` : ''}
    ${skipped ? `<p class="ins-note">Skipped expiries, ${esc(skipped)}.</p>` : ''}
    ${r.limits ? `<p class="ins-note">${esc(r.limits)} Charges are today's rates applied to every date.</p>` : ''}`;
}

async function run(body) {
  body.querySelectorAll('[data-c]').forEach(i => { cfg[i.dataset.c] = i.value.trim(); });
  save();
  running = true;
  redraw();
  try {
    const q = new URLSearchParams(cfg);
    const res = await fetch(`/api/option-backtest?${q}`);
    const d = await res.json();
    if (!res.ok) throw new Error(d.error || `HTTP ${res.status}`);
    result = d;
  } catch (e) { toast(e.message, 'error'); }
  running = false;
  redraw();
}

async function render(body, ctx) {
  ctx.pill(result?.asOf ? `Data to ${result.asOf}` : '', !!result?.asOf);
  const input = (k, label, w = 80) => `<label>${esc(label)} <input class="ins-input" data-c="${k}" value="${esc(cfg[k])}" style="width:${w}px"></label>`;
  body.innerHTML = `<div class="ins-bar">${input('underlying', 'Underlying', 120)}
      <select class="select" id="ob-preset" aria-label="Strategy"><option value="">Strategy…</option>${Object.keys(PRESETS).map(k => `<option>${esc(k)}</option>`).join('')}</select>
      ${input('legs', 'Legs', 300)}
      <label>Expiries <select class="select" data-c="expiry"><option value="weekly"${cfg.expiry === 'weekly' ? ' selected' : ''}>All listed</option><option value="monthly"${cfg.expiry === 'monthly' ? ' selected' : ''}>Monthly</option></select></label>
      ${input('entry', 'Sessions before expiry', 50)}${input('months', 'Months', 50)}${input('lots', 'Lots', 50)}${input('slippagePct', 'Slippage %', 50)}${input('brokeragePerOrder', 'Brokerage ₹', 50)}
      <button type="button" class="btn" id="ob-chart">Use ${esc(state.currentSymbol)}</button>
      <button type="button" class="btn primary" id="ob-run"${running ? ' disabled' : ''}>${running ? 'Running…' : 'Run'}</button></div>
    <p class="ins-note">Legs: BUY or SELL, CE or PE, then strikes from at-the-money (0 = ATM, 2 = two strikes up, −2 = two down).</p>
    ${resultHtml(result)}`;
  body.querySelector('#ob-preset').addEventListener('change', (e) => { if (PRESETS[e.target.value]) body.querySelector('[data-c="legs"]').value = PRESETS[e.target.value]; });
  body.querySelector('#ob-chart').addEventListener('click', () => { body.querySelector('[data-c="underlying"]').value = state.currentSymbol.replace(/\.NS$/, ''); });
  body.querySelector('#ob-run').addEventListener('click', () => run(body));
}

registerTab('optbt', 'Option backtest', render, { title: 'Option strategy backtest, end of day, net of charges' });
