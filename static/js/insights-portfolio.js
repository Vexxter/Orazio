// Insights › Portfolio: import a holdings CSV from your broker and see value, P&L, weights, concentration, beta to
// NIFTY, volatility, drawdown, VaR, and a Monte Carlo of the next year from resampled daily returns. Kept in this browser only; nothing is uploaded. Maths: portfolio-math.js.
import { esc } from './format.js';
import { historyBars, redraw, registerTab } from './insights.js';
import { beta, chartSymbol, dailyReturns, effectivePositions, holdingRows, monteCarlo, parseHoldings, portfolioReturns, riskStats } from './portfolio-math.js';
import { toast } from './ui.js';

const KEY = 'orazio.portfolio.v1';
const BENCH = 'NIFTY';
let holdings = [];
try { holdings = JSON.parse(localStorage.getItem(KEY) || '[]'); } catch (e) { /* none yet */ }
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(holdings)); } catch (e) { toast("Couldn't save the portfolio in this browser", 'error'); } };
const nf = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 });
const nf2 = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 });
const money = (v) => (v === null || v === undefined ? '–' : nf.format(v));
const pct = (v, d = 1) => (v === null || v === undefined ? '–' : `${v.toFixed(d)}%`);
const sign = (v) => (v > 0 ? 'up' : v < 0 ? 'down' : '');
const card = (k, v, s = '', cls = '') => `<div class="ins-card"><div class="k">${esc(k)}</div><div class="v ${cls}">${v}</div><div class="s">${s}</div></div>`;

function importer(body) {
  const load = (text) => {
    const { holdings: rows, errors } = parseHoldings(text);
    if (!rows.length) { toast(errors[0] || 'No holdings found', 'error'); return; }
    holdings = rows;
    save();
    if (errors.length) toast(`Imported ${rows.length}, skipped ${errors.length}: ${errors[0]}`, 'error');
    redraw();
  };
  body.querySelector('#pf-file').addEventListener('change', async (e) => { if (e.target.files[0]) load(await e.target.files[0].text()); });
  body.querySelector('#pf-paste').addEventListener('click', () => load(body.querySelector('#pf-text').value));
}

async function render(body, ctx) {
  const form = `<div class="ins-bar"><label class="btn">Import CSV<input type="file" id="pf-file" accept=".csv,text/csv" hidden></label>
      ${holdings.length ? '<button type="button" class="btn" id="pf-clear">Clear</button>' : ''}<span class="ins-note">Stays in this browser. Works with holdings exports that have symbol, quantity and average price columns.</span></div>
    <details${holdings.length ? '' : ' open'}><summary class="ins-note">Or paste CSV</summary><textarea class="ins-input" id="pf-text" rows="5" style="width:100%" placeholder="Symbol,Qty,Avg price&#10;RELIANCE,10,2400&#10;TCS,5,3500" aria-label="Holdings as CSV"></textarea><button type="button" class="btn" id="pf-paste">Use this</button></details>`;
  if (!holdings.length) {
    ctx.pill('');
    body.innerHTML = `${form}<div class="empty-note">No holdings yet.</div>`;
    importer(body);
    return;
  }
  const syms = holdings.map(h => chartSymbol(h.symbol));
  const quotes = await Promise.all(syms.map(s => fetch(`/api/quote?symbol=${encodeURIComponent(s)}`).then(r => (r.ok ? r.json() : null)).catch(() => null)));
  const [hist, bench] = await Promise.all([
    Promise.all(syms.map(s => historyBars(s, '1Y').catch(() => []))),
    historyBars(BENCH, '1Y').catch(() => []),
  ]);
  if (ctx.stale()) return;
  const quoteMap = new Map(holdings.map((h, i) => [h.symbol, quotes[i]]));
  const rows = holdingRows(holdings, quoteMap);
  const value = rows.reduce((s, r) => s + (r.value ?? 0), 0);
  const cost = rows.reduce((s, r) => s + (r.pnl === null ? 0 : r.cost), 0);
  const pnl = rows.reduce((s, r) => s + (r.pnl ?? 0), 0);
  const day = rows.reduce((s, r) => s + (r.dayPnl ?? 0), 0);
  const series = rows.map((r, i) => ({ weight: r.weight ?? 0, returns: dailyReturns(hist[i]) })).filter(s => s.weight > 0 && s.returns.size);
  const ret = portfolioReturns(series);
  const risk = riskStats(ret);
  const b = beta(ret, dailyReturns(bench));
  const mc = monteCarlo(ret.values());
  const unpriced = rows.filter(r => r.price === null).map(r => r.symbol);
  const top = [...rows].sort((a, x) => (x.weight ?? 0) - (a.weight ?? 0))[0];
  ctx.pill(`${rows.length} holdings · live`);
  body.innerHTML = `${form}
    <div class="ins-cards">${card('Value', `₹${money(value)}`)}
      ${card('Total P&L', `₹${money(pnl)}`, cost ? pct(pnl / cost * 100) : '', sign(pnl))}
      ${card('Today', `₹${money(day)}`, value ? pct(day / (value - day) * 100, 2) : '', sign(day))}
      ${card('Largest', esc(top?.symbol ?? '–'), pct(top?.weight))}
      ${card('Effective positions', nf2.format(effectivePositions(rows.map(r => r.weight ?? 0)) ?? 0), `of ${rows.length}`)}
      ${card(`Beta to ${BENCH}`, b === null ? '–' : b.toFixed(2), '1 year, daily')}
      ${card('Volatility', pct(risk?.volPct), 'annualised')}
      ${card('Worst drawdown', pct(risk?.maxDrawdownPct), '1 year', 'down')}
      ${card('1-day 95% VaR', pct(risk?.var95Pct, 2), 'historical')}</div>
    ${mc ? `<h3 class="ins-note">Next 12 months, ${nf.format(mc.paths)} simulated paths</h3><div class="ins-cards">
      ${card('Likely range', `${pct(mc.p5)} to ${pct(mc.p95)}`, '5th to 95th percentile')}
      ${card('Median outcome', pct(mc.p50), `₹${money(value * mc.p50 / 100)}`, sign(mc.p50))}
      ${card('Typical drawdown', pct(mc.ddMedian), 'median worst dip on the way', 'down')}
      ${card('Bad-year drawdown', pct(mc.dd95), `1 in 20 · ₹${money(value * mc.dd95 / 100)}`, 'down')}
      ${card('Chance of a loss', pct(mc.lossProb, 0), 'over 12 months')}</div>` : ''}
    ${unpriced.length ? `<p class="ins-note down">No price found for ${esc(unpriced.join(', '))}, so they count as zero above. Use the chart symbol in the CSV, like TATAMOTORS.NS.</p>` : ''}
    <table class="opt-table"><thead><tr><th style="text-align:left">Symbol</th><th>Qty</th><th>Avg</th><th>Price</th><th>Value</th><th>Weight</th><th>P&amp;L</th><th>Today</th></tr></thead><tbody>${
      rows.map((r, i) => `<tr data-symbol="${esc(syms[i])}" tabindex="0" role="button"><td style="text-align:left"><strong>${esc(r.symbol)}</strong></td><td>${nf2.format(r.qty)}</td><td>${r.avg === null ? '–' : nf2.format(r.avg)}</td><td>${r.price === null ? '–' : nf2.format(r.price)}</td><td>${money(r.value)}</td><td>${pct(r.weight)}</td><td class="${sign(r.pnl)}">${money(r.pnl)}</td><td class="${sign(r.dayPnl)}">${money(r.dayPnl)}</td></tr>`).join('')
    }</tbody></table>
    <p class="ins-note">The simulation resamples the last year's daily returns at random, so it assumes the next year looks like a shuffled last year: it keeps big days, not streaks. Beta, volatility, drawdown and VaR apply today's weights to the last year of daily returns: how this book would have behaved, not what your account did.</p>`;
  importer(body);
  body.querySelector('#pf-clear')?.addEventListener('click', () => { holdings = []; save(); redraw(); });
}

registerTab('portfolio', 'Portfolio', render, { pollMs: 30000, title: 'Portfolio analytics from a holdings CSV' });
