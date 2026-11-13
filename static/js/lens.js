// Stock Lens: a card at the top of the right-hand column that answers, for whatever is charted, the questions an analyst
// asks first: results coming and is the options market pricing more than usual, are insiders buying, cheap or dear
// against peers, options cheap or dear, trend. One line each, a verdict, and a click through to the evidence.
// Facts arrive in parallel and the card redraws as each lands, so the slowest feed never holds up the rest.
// Wording and ordering: lens-math.js (unit-tested).
import { esc } from './format.js';
import { historyBars } from './insights.js';
import { resultsReactions } from './insights-math.js';
import { lensLines, trendFacts } from './lens-math.js';
import { rankOf } from './options-math.js';
import { fnoStocks, impliedMove } from './results-edge.js';
import { $, displayName, state } from './state.js';

const SHOW = 6;
const INDEX = { NIFTY: 'NIFTY', '^NSEI': 'NIFTY', BANKNIFTY: 'BANKNIFTY', '^NSEBANK': 'BANKNIFTY', FINNIFTY: 'FINNIFTY' };
const listEl = $('lens-list');
let generation = 0, shown = null;
const json = (url) => fetch(url).then(r => (r.ok ? r.json() : null)).catch(() => null);
const daysTo = (iso) => Math.round((Date.parse(`${iso}T00:00:00Z`) - Date.UTC(new Date().getUTCFullYear(), new Date().getUTCMonth(), new Date().getUTCDate())) / 86400000);

function paint(lines, loading) {
  if (!lines.length) {
    listEl.innerHTML = loading ? '<div class="lens-skel"></div><div class="lens-skel"></div><div class="lens-skel"></div>' : '<div class="lens-empty">Nothing stands out yet.</div>';
    return;
  }
  listEl.innerHTML = lines.slice(0, SHOW).map(l => `<button type="button" class="lens-line tone-${l.tone}" data-cmd="${esc(l.cmd)}" title="Open the evidence: ${esc(l.cmd)}">
      <span class="lens-k">${esc(l.title)}</span><span class="lens-t">${esc(l.text)}</span><kbd>:${esc(l.cmd.split(' ').pop().replace(/^:/, ''))}</kbd></button>`).join('')
    + (loading ? '<div class="lens-skel"></div>' : '');
}

async function results(t, sym, facts, done) {
  const cal = await json(`/api/earnings/calendar?symbols=${encodeURIComponent(t)}`);
  const next = cal?.rows?.[0];
  if (!next) return;
  facts.nextResults = { date: next.date, days: daysTo(next.date) };
  done();
  const [events, bars, edge] = await Promise.all([json(`/api/chart-events?symbol=${encodeURIComponent(sym)}`), historyBars(sym, '5Y').catch(() => []), impliedMove(t, next.date)]);
  const r = resultsReactions(bars, (events || []).filter(e => e.kind === 'results').map(e => e.date));
  if (r.avgAbsMove) facts.typicalMove = r.avgAbsMove;
  if (edge) facts.impliedMove = edge.move;
  done();
}

async function gather(sym, done) {
  const facts = { symbol: sym };
  const t = sym.endsWith('.NS') ? sym.slice(0, -3) : null;
  const idx = INDEX[sym];
  const jobs = [historyBars(sym, '1Y').then(b => { facts.trend = trendFacts(b); done(facts); }).catch(() => {})];
  const tick = () => done(facts);
  if (t) {
    jobs.push(json(`/api/fundamentals?symbol=${encodeURIComponent(sym)}`).then(f => { if (f?.available) { facts.pe = f.ratios.pe; facts.roe = f.ratios.roe; tick(); } }));
    jobs.push(json(`/api/peers?symbol=${encodeURIComponent(sym)}`).then(p => { if (p?.available) { facts.peerPe = p.median.pe; facts.peerRoe = p.median.roe; tick(); } }));
    jobs.push(json(`/api/insider?symbol=${encodeURIComponent(t)}`).then((d) => {
      const since = new Date(Date.now() - 120 * 86400000).toISOString().slice(0, 10);
      const rows = (d?.rows || []).filter(r => r.senior && r.date >= since);
      if (rows.length) { facts.insiderNetCr = rows.reduce((s, r) => s + (r.side === 'buy' ? r.valueCr : -r.valueCr), 0); facts.insiderTrades = rows.length; tick(); }
    }));
    jobs.push(results(t, sym, facts, tick));
    jobs.push(fnoStocks().then(s => (s.has(t) ? json(`/api/options/analytics?symbol=${encodeURIComponent(sym)}`) : null)).then((a) => {
      if (a?.available) { facts.ivRank = a.ivHistory?.rank ?? null; facts.ivDays = a.ivHistory?.days; facts.pcr = a.pcr; tick(); }
    }));
  } else if (idx) {
    jobs.push(json(`/api/options/analytics?symbol=${idx}`).then((a) => {
      if (a?.available) { facts.gex = { netCr: a.netGexCr, flip: a.flip, spot: a.spot }; facts.pcr = a.pcr; facts.ivRank = a.ivHistory?.rank ?? null; facts.ivDays = a.ivHistory?.days; tick(); }
    }));
    if (idx === 'NIFTY') {
      jobs.push(historyBars('^INDIAVIX', '1Y').then((b) => { const c = b.map(x => x.close); const r = rankOf(c, c.at(-1)); if (r) { facts.vixRank = r.rank; tick(); } }).catch(() => {}));
      jobs.push(json('/api/flows').then((d) => { const last = (d?.cash || []).at(-1); if (last?.fii?.net !== undefined) { facts.fiiNetCr = last.fii.net; tick(); } }));
    }
  }
  await Promise.allSettled(jobs);
  return facts;
}

export async function renderLens() {
  const sym = state.currentSymbol;
  if (!sym || sym === shown) return;
  shown = sym;
  const my = ++generation;
  $('lens-sym').textContent = displayName(sym);
  paint([], true);
  const draw = (facts, loading = true) => { if (my === generation) paint(lensLines(facts), loading); };
  const facts = await gather(sym, (f) => draw(f));
  draw(facts, false);
}

listEl.addEventListener('click', (e) => {
  const b = e.target.closest('[data-cmd]');
  if (b) document.dispatchEvent(new CustomEvent('intent:run', { detail: b.dataset.cmd }));
});
document.addEventListener('candles:loaded', renderLens);
