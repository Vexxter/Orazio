// Insights › Earnings (:ERN): who reports results in the coming days (your watchlist first, or every NSE company),
// and how the charted stock has moved around its past results. Bloomberg's EE / ERN on public data.
// Data: /api/earnings/calendar (NSE event calendar), /api/chart-events (NSE results meeting history), daily bars.
import { esc } from './format.js';
import { historyBars, redraw, registerTab } from './insights.js';
import { resultsReactions } from './insights-math.js';
import { impliedMove } from './results-edge.js';
import { watchlistSymbols } from './insights-watchlist.js';
import { state } from './state.js';

let scope = 'watchlist';
const nf1 = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 1 });
const pct = (v) => (v === null || v === undefined ? '–' : `${v > 0 ? '+' : ''}${nf1.format(v)}%`);
const sign = (v) => (v > 0 ? 'up' : v < 0 ? 'down' : '');
const card = (k, v, s = '') => `<div class="ins-card"><div class="k">${esc(k)}</div><div class="v">${v}</div><div class="s">${s}</div></div>`;
const isNse = (s) => s.endsWith('.NS');

async function reactions(sym) {
  if (!isNse(sym)) return null;
  const [events, bars] = await Promise.all([
    fetch(`/api/chart-events?symbol=${encodeURIComponent(sym)}`).then(r => (r.ok ? r.json() : [])).catch(() => []),
    historyBars(sym, '5Y').catch(() => []),
  ]);
  return resultsReactions(bars, events.filter(e => e.kind === 'results').map(e => e.date));
}

function calendarTable(rows, mine) {
  if (!rows.length) return `<div class="empty-note">${scope === 'watchlist' ? 'None of your watchlist stocks has a results meeting scheduled. Switch to All NSE.' : 'No results meetings in NSE’s calendar.'}</div>`;
  return `<table class="opt-table"><thead><tr><th>Date</th><th style="text-align:left">Company</th><th style="text-align:left">Agenda</th></tr></thead><tbody>${
    rows.slice(0, 200).map(r => `<tr data-symbol="${esc(r.chartSymbol)}" tabindex="0" role="button"${mine.has(r.chartSymbol) ? ' class="ins-me"' : ''}>
      <td style="white-space:nowrap">${esc(r.date)}</td><td style="text-align:left"><strong>${esc(r.symbol)}</strong> <span class="ins-note">${esc(r.company)}</span></td>
      <td style="text-align:left"><span class="ins-note">${esc(r.purpose.slice(0, 140))}</span></td></tr>`).join('')}</tbody></table>`;
}

function reactionSection(sym, r, next, edge) {
  if (!r) return '';
  if (!r.rows.length) return `<div class="ins-sec"><h3>${esc(sym)} around results</h3><div class="empty-note">No past results dates found for ${esc(sym)}.</div></div>`;
  return `<div class="ins-sec"><h3>${esc(sym)} around results</h3><div class="ins-cards">
      ${card('Next results', next ? esc(next.date) : '–', next ? 'NSE board meeting' : 'none scheduled yet')}
      ${card('Typical move', r.avgAbsMove === null ? '–' : `±${nf1.format(r.avgAbsMove)}%`, `average 2-session move, ${r.rows.length} results`)}
      ${card('Rose after results', r.upShare === null ? '–' : `${nf1.format(r.upShare)}%`, 'of the time')}
      ${edge ? card('Options price', `±${nf1.format(edge.move)}%`, `${esc(edge.expiry)} straddle · ${r.avgAbsMove ? (edge.move / r.avgAbsMove > 1.25 ? 'rich vs history' : edge.move / r.avgAbsMove < 0.8 ? 'cheap vs history' : 'fair vs history') : ''}`) : ''}</div>
    <table class="opt-table"><thead><tr><th>Results date</th><th>2-session move</th><th>Drift to day 5</th></tr></thead><tbody>${
      r.rows.slice(0, 20).map(x => `<tr><td>${esc(x.date)}</td><td class="${sign(x.move)}">${pct(x.move)}</td><td class="${sign(x.drift)}">${pct(x.drift)}</td></tr>`).join('')}</tbody></table>
    <p class="ins-note">Move: last close before the meeting day to the close of the session after it (meetings often end after the close). Compare the typical move with the options straddle (Options tab) to judge whether the market is pricing more or less than usual.</p></div>`;
}

async function render(body, ctx) {
  const sym = state.currentSymbol;
  const mine = new Set(watchlistSymbols());
  const wanted = scope === 'watchlist' ? [...mine].filter(isNse) : [];
  const calendar = (syms) => fetch(`/api/earnings/calendar${syms.length ? `?symbols=${encodeURIComponent(syms.join(','))}` : ''}`).then(x => x.json());
  const [cal, r, own] = await Promise.all([
    scope === 'watchlist' && !wanted.length ? { available: true, rows: [] } : calendar(wanted),
    reactions(sym),
    isNse(sym) ? calendar([sym]).catch(() => ({ rows: [] })) : { rows: [] },   // same cached NSE call server-side
  ]);
  if (ctx.stale()) return;
  ctx.pill(cal.available ? `${cal.rows.length} upcoming` : 'NSE unavailable', cal.available);
  const next = own.rows[0];
  const edge = next ? await impliedMove(sym.replace(/\.NS$/, ''), next.date) : null;
  if (ctx.stale()) return;
  body.innerHTML = `${reactionSection(sym, r, next, edge)}
    <div class="ins-sec"><h3>Results calendar</h3><div class="ins-bar">
      <select class="select" id="ern-scope" aria-label="Which companies"><option value="watchlist"${scope === 'watchlist' ? ' selected' : ''}>My watchlist</option><option value="all"${scope === 'all' ? ' selected' : ''}>All NSE</option></select>
      <span class="ins-note">Board meetings that will consider results, from NSE's event calendar. Click a row to chart it.</span></div>
      ${cal.available ? calendarTable(cal.rows, mine) : '<div class="empty-note">NSE didn’t answer. It will retry.</div>'}</div>`;
  body.querySelector('#ern-scope').addEventListener('change', (e) => { scope = e.target.value; redraw(); });
}

registerTab('earnings', 'Earnings', render, { pollMs: 600000, title: 'Results calendar and past results reactions' });
