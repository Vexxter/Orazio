// Options panel. NSE symbols: front/next/far futures (price, basis, OI) and the option chain (OI ladder, PCR,
// max pain, ATM straddle) from orazio/fno.py -> NSE's own feeds. Any other symbol that Yahoo has options for
// (US stocks and ETFs): Yahoo's option chain from /api/options, in the same panel.
import { compactIN } from './format.js';
import { breakevens, extremes, netPremium, payoff, payoffCurve } from './options-math.js';
import { $, displayName, esc, state, visible } from './state.js';

const modal = $('fno-modal');
let tab = 'fut';
let poll = null;
let trigger = null;
let expiry = null;      // chosen option expiry (null = nearest)
let forSymbol = null;   // symbol the current expiry choice belongs to
let inFlight = false;
let again = false;       // a load was asked for (expiry/tab change) while one was in flight: run it after
let usMode = false;     // the symbol has no NSE contracts, so the panel is showing Yahoo's option chain
let legs = [];          // payoff builder: { side, kind, strike, premium, lots }
let legsFor = null;     // "underlying|expiry" the legs were built on
let last = null;        // last NSE panel payload, for the payoff tab's live P&L

const num = (v, d = 2) => (v === null || v === undefined ? '–' : Number(v).toLocaleString('en-IN', { minimumFractionDigits: d, maximumFractionDigits: d }));
const big = (v) => (v === null || v === undefined ? '–' : compactIN(v));
const sgn = (v, d = 2) => (v === null || v === undefined ? '–' : `${v >= 0 ? '+' : ''}${num(v, d)}`);
const cls = (v) => (v === null || v === undefined || v === 0 ? '' : v > 0 ? 'up' : 'down');
const delta = (v) => (v === null || v === undefined ? '–' : (v >= 0 ? '+' : '') + big(v));

function open() {
  trigger = document.activeElement;
  modal.classList.add('open');
  $('fno-close').focus();
  load();
  clearInterval(poll);
  poll = setInterval(visible(() => { if (!usMode) load(); }), 5000);     // Yahoo's chain moves slowly: loaded on open, on expiry change and on symbol change only
}
function close() {
  modal.classList.remove('open');
  clearInterval(poll);
  poll = null;
  trigger?.focus();
}

async function load() {
  if (inFlight) { again = true; return; }
  inFlight = true;
  const symbol = state.currentSymbol;
  if (symbol !== forSymbol) { expiry = null; forSymbol = symbol; usMode = false; }
  try {
    const q = new URLSearchParams({ symbol });
    if (expiry && !usMode) q.set('expiry', expiry);
    const res = await fetch(`/api/fno?${q}`);
    if (!res.ok) throw new Error();
    const d = await res.json();
    if (d.available) { usMode = false; render(d); }
    else await loadYahooChain(d);
  } catch (e) {
    $('fno-body').innerHTML = '<div class="empty-note">Options feed unreachable — retrying.</div>';
  } finally {
    inFlight = false;
    if (again) { again = false; load(); }
  }
}

// Not an NSE F&O symbol: try Yahoo's option chain (US stocks and ETFs) before saying there is nothing.
async function loadYahooChain(nse) {
  const sym = state.resolvedSymbol || state.currentSymbol;
  const q = new URLSearchParams({ symbol: sym });
  if (expiry) q.set('expiry', expiry);
  let d;
  try {
    const res = await fetch(`/api/options?${q}`);
    if (!res.ok) throw new Error();
    d = await res.json();
  } catch (e) {
    usMode = false;
    renderNone(`${nse.reason || 'No NSE contracts for this symbol.'} Yahoo's option chain didn't respond either.`);
    return;
  }
  if (!d.available) { usMode = false; renderNone(d.reason || nse.reason); return; }
  usMode = true;
  renderYahooChain(d, sym);
}

function renderNone(reason) {
  $('fno-title').textContent = 'Options';
  $('fno-tabs').hidden = false;
  $('fno-strip').innerHTML = '';
  $('fno-expiry').hidden = true;
  $('fno-window').hidden = true;
  $('fno-asof').dataset.live = 'false';
  $('fno-asof').textContent = '—';
  $('fno-body').innerHTML = `<div class="empty-note">${esc(reason || 'No options data.')}<br>Options come from NSE (NIFTY, BANKNIFTY, F&amp;O stocks) and from Yahoo (US stocks and ETFs).</div>`;
}

function renderYahooChain(d, sym) {
  $('fno-title').textContent = `Options · ${displayName(sym)}`;
  $('fno-tabs').hidden = true;                      // no futures tab: Yahoo has no futures for these symbols
  $('fno-window').hidden = true;
  const pill = $('fno-asof');
  pill.dataset.live = 'false';
  pill.textContent = 'Yahoo · delayed';
  pill.title = 'Yahoo option chains are delayed about 15 minutes';
  const sel = $('fno-expiry');
  sel.innerHTML = d.expiries.map(e => `<option value="${esc(e)}"${e === d.expiry ? ' selected' : ''}>${esc(e)}</option>`).join('');
  sel.hidden = false;
  $('fno-strip').innerHTML = `<span class="fno-note">Option chain from Yahoo Finance — US stocks and ETFs. Delayed about 15 minutes.</span>`;
  const atm = state.lastPolledPrice && d.calls.length
    ? d.calls.reduce((best, r) => Math.abs(r.strike - state.lastPolledPrice) < Math.abs(best - state.lastPolledPrice) ? r.strike : best, d.calls[0].strike)
    : null;
  const cell = (v, dp) => (v === null || v === undefined ? '–' : dp === undefined ? Number(v).toLocaleString('en-US') : Number(v).toFixed(dp));
  const table = (label, rows) => `<div><h3>${label}</h3><table class="opt-table"><thead><tr>
      <th>Strike</th><th>Last</th><th>Bid</th><th>Ask</th><th>Vol</th><th>OI</th></tr></thead><tbody>${
    rows.map(r => `<tr class="${r.strike === atm ? 'atm' : ''}"><td>${cell(r.strike, 2)}</td><td>${cell(r.lastPrice, 2)}</td><td>${cell(r.bid, 2)}</td><td>${cell(r.ask, 2)}</td><td>${cell(r.volume)}</td><td>${cell(r.openInterest)}</td></tr>`).join('')
  }</tbody></table></div>`;
  $('fno-body').innerHTML = `<div class="opt-grid">${table('Calls', d.calls)}${table('Puts', d.puts)}</div>`;
}

function render(d) {
  const pill = $('fno-asof');
  $('fno-tabs').hidden = false;
  pill.title = '';
  if (!d.available) { renderNone(d.reason); return; }
  last = d;
  $('fno-title').textContent = `Options · ${d.name}`;
  const asOf = (tab !== 'fut' ? d.chain?.asOf : d.asOf) || d.asOf || '';
  pill.dataset.live = 'true';
  pill.textContent = asOf ? `Live · ${asOf.split(' ').pop()}` : 'Live';

  const onFutures = d.futureSymbol === state.currentSymbol;
  const canSwap = !$('futures-toggle').hidden;
  const swap = canSwap
    ? `<button type="button" class="btn fno-swap" id="fno-swap">Chart the ${onFutures ? 'spot' : 'future'} instead</button>` : '';

  const ch = d.chain;
  const sel = $('fno-expiry');
  sel.hidden = tab === 'fut' || !ch || !ch.expiries?.length;
  $('fno-window').hidden = tab !== 'chain' && tab !== 'smile';
  if (!sel.hidden) {
    sel.innerHTML = ch.expiries.map(e => `<option value="${esc(e)}"${e === ch.expiry ? ' selected' : ''}>${esc(e)}</option>`).join('');
  }

  if (tab === 'fut') {
    $('fno-strip').innerHTML = `<span>Spot <b class="num">${num(d.spot)}</b></span><span class="fno-note">Basis = future − spot. Volume is in contracts.</span><span class="feed-strip-val">${swap}</span>`;
    $('fno-body').innerHTML = futuresTable(d);
  } else if (tab === 'payoff' && ch && ch.rows.length) {
    renderPayoff(d, swap);
  } else if (!ch || !ch.rows.length) {
    $('fno-strip').innerHTML = `<span class="feed-strip-val">${swap}</span>`;
    $('fno-body').innerHTML = '<div class="empty-note">No option chain returned for this expiry.</div>';
  } else {
    $('fno-strip').innerHTML =
      `<span>Spot <b class="num">${num(ch.spot)}</b></span>` +
      `<span title="Put OI ÷ Call OI. Above 1 = more puts written than calls">PCR <b class="num ${ch.pcr >= 1 ? 'up' : 'down'}">${num(ch.pcr)}</b></span>` +
      `<span title="Strike where option writers pay out least at expiry">Max pain <b class="num">${num(ch.maxPain, 0)}</b></span>` +
      `<span title="ATM call + put price: the move the market is pricing in">ATM straddle <b class="num">${num(ch.straddle)}</b></span>` +
      `<span>CE OI <b class="num">${big(ch.totalCeOi)}</b></span><span>PE OI <b class="num">${big(ch.totalPeOi)}</b></span>` +
      `<span class="feed-strip-val">${swap}</span>`;
    $('fno-body').innerHTML = tab === 'smile' ? smileChart(ch) : chainTable(ch);
  }
}

function futuresTable(d) {
  if (!d.futures.length) return '<div class="empty-note">No futures returned right now.</div>';
  const rows = d.futures.map((f, i) => `<tr>
    <td class="l"><strong>${esc(f.expiry)}</strong>${i === 0 ? ' <span class="fno-tag">front</span>' : ''}</td>
    <td>${num(f.last)}</td><td class="${cls(f.pChange)}">${sgn(f.pChange)}%</td>
    <td class="${cls(f.basis)}">${sgn(f.basis)}</td><td class="${cls(f.basisPct)}">${sgn(f.basisPct)}%</td>
    <td>${big(f.oi)}</td><td class="${cls(f.dOi)}">${delta(f.dOi)}</td>
    <td>${big(f.volume)}</td><td>${num(f.open)}</td><td>${num(f.high)}</td><td>${num(f.low)}</td></tr>`).join('');
  return `<table class="opt-table feed-table"><thead><tr>
    <th class="l">Expiry</th><th>Last</th><th>Chg %</th><th>Basis</th><th>Basis %</th><th>OI</th><th>Δ OI</th><th>Volume</th><th>Open</th><th>High</th><th>Low</th>
    </tr></thead><tbody>${rows}</tbody></table>`;
}

// The strikes the ±N window selector keeps around ATM.
function windowRows(ch) {
  const win = $('fno-window').value;
  if (win === 'all') return ch.rows;
  const i = ch.rows.findIndex(r => r.strike === ch.atm);
  const n = Number(win);
  return ch.rows.slice(Math.max(0, i - n), i + n + 1);
}

function chainTable(ch) {
  const rows = windowRows(ch);
  const maxOi = Math.max(1, ...rows.map(r => Math.max(r.ce?.oi || 0, r.pe?.oi || 0)));
  // Change-in-OI heatmap: green = positions being built, red = unwound; stronger = bigger vs the window.
  const maxD = Math.max(1, ...rows.map(r => Math.max(Math.abs(r.ce?.dOi || 0), Math.abs(r.pe?.dOi || 0))));
  const heat = (v) => (v ? ` style="background:${v > 0 ? 'rgba(38,166,154,' : 'rgba(239,83,80,'}${(0.08 + 0.42 * Math.abs(v) / maxD).toFixed(2)})"` : '');
  const pick = (kind, r, s) => (s?.ltp != null ? ` class="pick" data-kind="${kind}" data-strike="${r.strike}" data-ltp="${s.ltp}" title="Click: buy · Shift+click: sell — adds a leg to Payoff"` : '');
  const bar = (oi, side) => `style="--w:${Math.round(((oi || 0) / maxOi) * 100)}%" class="oi ${side}"`;
  const at = (s, k, f) => (s ? f(s[k]) : '–');
  const body = rows.map(r => {
    const ce = r.ce, pe = r.pe;
    return `<tr class="${r.strike === ch.atm ? 'atm' : ''}">
      <td ${bar(ce?.oi, 'ce')}>${at(ce, 'oi', big)}</td>
      <td${heat(ce?.dOi)}>${at(ce, 'dOi', delta)}</td>
      <td>${at(ce, 'volume', big)}</td><td>${at(ce, 'iv', (v) => num(v, 1))}</td>
      <td${pick('CE', r, ce)}><strong class="${cls(ce?.change)}">${at(ce, 'ltp', num)}</strong></td>
      <td class="strike"><strong>${num(r.strike, 0)}</strong></td>
      <td${pick('PE', r, pe)}><strong class="${cls(pe?.change)}">${at(pe, 'ltp', num)}</strong></td>
      <td>${at(pe, 'iv', (v) => num(v, 1))}</td><td>${at(pe, 'volume', big)}</td>
      <td${heat(pe?.dOi)}>${at(pe, 'dOi', delta)}</td>
      <td ${bar(pe?.oi, 'pe')}>${at(pe, 'oi', big)}</td></tr>`;
  }).join('');
  return `<table class="opt-table fno-chain"><thead><tr>
    <th colspan="5" class="grp ce">CALLS</th><th class="strike">Strike</th><th colspan="5" class="grp pe">PUTS</th></tr><tr>
    <th>OI</th><th>Δ OI</th><th>Vol</th><th>IV</th><th>LTP</th><th class="strike"></th><th>LTP</th><th>IV</th><th>Vol</th><th>Δ OI</th><th>OI</th>
    </tr></thead><tbody>${body}</tbody></table>`;
}

$('fno-btn').addEventListener('click', open);
$('fno-close').addEventListener('click', close);
modal.addEventListener('mousedown', (e) => { if (e.target === modal) close(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && modal.classList.contains('open')) close(); });
$('fno-tabs').addEventListener('click', (e) => {
  const b = e.target.closest('button[data-tab]');
  if (!b) return;
  tab = b.dataset.tab;
  document.querySelectorAll('#fno-tabs button').forEach(x => x.setAttribute('aria-pressed', String(x === b)));
  $('fno-body').innerHTML = '<div class="empty-note">Loading…</div>';
  load();
});
$('fno-expiry').addEventListener('change', (e) => { expiry = e.target.value; load(); });
$('fno-window').addEventListener('change', load);
// "Chart the future/spot instead" clicks the same Spot | Futures switch the user would.
modal.addEventListener('click', (e) => {
  if (!e.target.closest('#fno-swap')) return;
  $('futures-toggle').querySelector('button[aria-pressed="false"]')?.click();
  close();
});

// ---------- IV smile ----------
// Implied volatility per strike for calls and puts, ATM marked. Plain SVG: the x axis is strike, not time,
// which Lightweight Charts can't do.
const W = 800, H = 280, PAD = { l: 48, r: 16, t: 16, b: 28 };
const scale = (lo, hi, a, b) => (v) => a + ((v - lo) / (hi - lo || 1)) * (b - a);
const ticks = (lo, hi, n = 5) => Array.from({ length: n + 1 }, (_, i) => lo + ((hi - lo) * i) / n);

function axes(xs, ys, fx, fy, fmtX, fmtY) {
  return ticks(ys[0], ys[1], 4).map(v => `<line class="gl" x1="${PAD.l}" x2="${W - PAD.r}" y1="${fy(v)}" y2="${fy(v)}"/><text class="ax" x="${PAD.l - 6}" y="${fy(v) + 4}" text-anchor="end">${fmtY(v)}</text>`).join('') +
    ticks(xs[0], xs[1], 6).map(v => `<text class="ax" x="${fx(v)}" y="${H - 8}" text-anchor="middle">${fmtX(v)}</text>`).join('');
}

function smileChart(ch) {
  const rows = windowRows(ch);
  const pts = (side) => rows.filter(r => r[side]?.iv > 0).map(r => [r.strike, r[side].iv]);
  const ce = pts('ce'), pe = pts('pe');
  const all = [...ce, ...pe];
  if (all.length < 2) return '<div class="empty-note">NSE has published no implied volatility for these strikes yet.</div>';
  const xs = [Math.min(...rows.map(r => r.strike)), Math.max(...rows.map(r => r.strike))];
  const ivs = all.map(p => p[1]);
  const ys = [Math.floor(Math.min(...ivs) - 1), Math.ceil(Math.max(...ivs) + 1)];
  const fx = scale(xs[0], xs[1], PAD.l, W - PAD.r), fy = scale(ys[0], ys[1], H - PAD.b, PAD.t);
  const path = (p) => p.map(([x, y], i) => `${i ? 'L' : 'M'}${fx(x).toFixed(1)},${fy(y).toFixed(1)}`).join('');
  const atm = ch.atm != null ? `<line class="atm-line" x1="${fx(ch.atm)}" x2="${fx(ch.atm)}" y1="${PAD.t}" y2="${H - PAD.b}"/><text class="ax" x="${fx(ch.atm) + 4}" y="${PAD.t + 10}">ATM ${num(ch.atm, 0)}</text>` : '';
  return `<div class="fno-chart-legend"><span class="ce">Calls IV</span><span class="pe">Puts IV</span><span class="fno-note">Implied volatility (%) by strike — a steeper left side means downside protection is priced richer.</span></div>
    <svg class="fno-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Implied volatility by strike">
      ${axes(xs, ys, fx, fy, (v) => num(v, 0), (v) => `${v.toFixed(0)}%`)}${atm}
      <path class="smile ce" d="${path(ce)}"/><path class="smile pe" d="${path(pe)}"/>
      ${ce.map(([x, y]) => `<circle class="dot ce" cx="${fx(x)}" cy="${fy(y)}" r="2.5"><title>${num(x, 0)} CE · IV ${num(y, 1)}%</title></circle>`).join('')}
      ${pe.map(([x, y]) => `<circle class="dot pe" cx="${fx(x)}" cy="${fy(y)}" r="2.5"><title>${num(x, 0)} PE · IV ${num(y, 1)}%</title></circle>`).join('')}
    </svg>`;
}

// ---------- Payoff builder ----------
const lotOf = () => last?.lotSize || 1;
const asLegs = () => legs.map(l => ({ ...l, qty: l.lots * lotOf() }));
const ltpOf = (ch, kind, strike) => {
  if (kind === 'FUT') return last?.futures?.[0]?.last ?? null;
  const r = ch.rows.find(x => x.strike === strike);
  return r?.[kind === 'CE' ? 'ce' : 'pe']?.ltp ?? null;
};
const money = (v) => (Math.abs(v) === Infinity ? 'Unlimited' : `${v >= 0 ? '+' : '−'}₹${compactIN(Math.abs(v))}`);

// Legs belong to one underlying and expiry; switching either starts a fresh strategy.
function resetLegsIfMoved(d) {
  const key = `${d.underlying}|${d.chain?.expiry}`;
  if (legsFor !== key) { legs = []; legsFor = key; }
}

function addLeg(kind, strike, premium, side) {
  if (!last?.chain) return;
  resetLegsIfMoved(last);
  legs.push({ side, kind, strike, premium, lots: 1 });
}

function renderPayoff(d, swap) {
  resetLegsIfMoved(d);
  const ch = d.chain;
  $('fno-strip').innerHTML = `<span>Spot <b class="num">${num(ch.spot)}</b></span><span>Lot size <b class="num">${d.lotSize || '–'}</b></span><span class="fno-note">Profit and loss at expiry. Click any LTP in the Option chain to add it (Shift+click to sell).</span><span class="feed-strip-val">${swap}</span>`;
  // The 5-second poll must not rebuild the form under the user's cursor: refresh only the result then.
  const editing = $('fno-body').contains(document.activeElement) && document.activeElement.matches('input, select');
  if (editing && $('payoff-result')) { renderPayoffResult(ch); return; }
  const strikes = ch.rows.map(r => `<option value="${r.strike}"${r.strike === ch.atm ? ' selected' : ''}>${num(r.strike, 0)}</option>`).join('');
  const legRows = legs.map((l, i) => `<tr data-leg="${i}">
      <td class="l"><span class="leg-side ${l.side}">${l.side === 'buy' ? 'BUY' : 'SELL'}</span> ${l.kind === 'FUT' ? 'Future' : `${num(l.strike, 0)} ${l.kind}`}</td>
      <td><input type="number" class="ind-len" name="lots" min="1" step="1" value="${l.lots}" aria-label="Lots"></td>
      <td><input type="number" class="ind-len" name="premium" min="0" step="0.05" value="${l.premium}" aria-label="Entry price"></td>
      <td>${num(ltpOf(ch, l.kind, l.strike))}</td>
      <td><button type="button" class="btn icon leg-del" aria-label="Remove leg">×</button></td></tr>`).join('');
  $('fno-body').innerHTML = `<div class="payoff">
    <div class="payoff-form">
      <select class="select" id="leg-side" aria-label="Buy or sell"><option value="buy">Buy</option><option value="sell">Sell</option></select>
      <select class="select" id="leg-kind" aria-label="Instrument"><option value="CE">Call (CE)</option><option value="PE">Put (PE)</option><option value="FUT">Future</option></select>
      <select class="select" id="leg-strike" aria-label="Strike">${strikes}</select>
      <button type="button" class="btn" id="leg-add">Add leg</button>
      ${legs.length ? '<button type="button" class="btn" id="leg-clear">Clear</button>' : ''}
    </div>
    ${legs.length ? `<table class="opt-table payoff-legs"><thead><tr><th class="l">Leg</th><th>Lots</th><th>Entry</th><th>LTP</th><th></th></tr></thead><tbody>${legRows}</tbody></table>` : '<div class="empty-note">No legs yet. Add one above, or click an LTP in the Option chain.</div>'}
    <div id="payoff-result"></div></div>`;
  renderPayoffResult(ch);
}

function renderPayoffResult(ch) {
  const box = $('payoff-result');
  if (!box) return;
  if (!legs.length) { box.innerHTML = ''; return; }
  const L = asLegs();
  const spot = ch.spot;
  // Frame the interesting part: wide enough for every strike and breakeven (found on a ±10% pass), with
  // some air either side — a fixed ±8% made a cheap straddle's loss zone a few pixels wide.
  const wide = breakevens(payoffCurve(L, spot * 0.9, spot * 1.1, 400));
  const dist = [...L.filter(l => l.kind !== 'FUT').map(l => Math.abs(l.strike - spot)), ...wide.map(b => Math.abs(b - spot))];
  const span = Math.min(spot * 0.1, Math.max(spot * 0.01, ...dist.map(d => d * 2)));
  const lo = Math.max(0, spot - span), hi = spot + span;
  const curve = payoffCurve(L, lo, hi, 240);
  const ex = extremes(L, curve);
  const be = breakevens(curve);
  const prem = netPremium(L);
  const nowPl = L.reduce((s, l) => { const p = ltpOf(ch, l.kind, l.strike); return p == null ? s : s + (l.side === 'sell' ? -1 : 1) * (p - l.premium) * l.qty; }, 0);
  const ys = curve.map(p => p.y);
  const yLo = Math.min(0, ...ys), yHi = Math.max(0, ...ys);
  const pad = (yHi - yLo) * 0.08 || 1;
  const x0 = PAD.l + 24;
  const fx = scale(lo, hi, x0, W - PAD.r), fy = scale(yLo - pad, yHi + pad, H - PAD.b, PAD.t);
  const line = curve.map((p, i) => `${i ? 'L' : 'M'}${fx(p.x).toFixed(1)},${fy(p.y).toFixed(1)}`).join('');
  const z = fy(0);
  const area = `${line}L${fx(hi)},${z}L${fx(lo)},${z}Z`;
  const fmtY = (v) => `${v < 0 ? '−' : ''}${compactIN(Math.abs(v))}`;
  box.innerHTML = `<div class="payoff-stats">
      <span>Max profit <b class="num up">${money(ex.maxProfit)}</b></span>
      <span>Max loss <b class="num down">${money(ex.maxLoss)}</b></span>
      <span>Breakeven <b class="num">${be.length ? be.map(v => num(v, 0)).join(' / ') : '–'}</b></span>
      <span>${prem >= 0 ? 'Net debit' : 'Net credit'} <b class="num">₹${compactIN(Math.abs(prem))}</b></span>
      <span title="Mark-to-market at current LTPs">P&amp;L now <b class="num ${nowPl >= 0 ? 'up' : 'down'}">${money(nowPl)}</b></span>
    </div>
    <svg class="fno-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Profit and loss at expiry by spot price">
      <defs><clipPath id="pf-up"><rect x="0" y="0" width="${W}" height="${z}"/></clipPath><clipPath id="pf-dn"><rect x="0" y="${z}" width="${W}" height="${H}"/></clipPath></defs>
      ${axes([lo, hi], [yLo - pad, yHi + pad], fx, fy, (v) => num(v, 0), fmtY)}
      <path class="pf-fill up" clip-path="url(#pf-up)" d="${area}"/><path class="pf-fill dn" clip-path="url(#pf-dn)" d="${area}"/>
      <line class="zero" x1="${x0}" x2="${W - PAD.r}" y1="${z}" y2="${z}"/>
      <path class="pf-line" d="${line}"/>
      <line class="atm-line" x1="${fx(spot)}" x2="${fx(spot)}" y1="${PAD.t}" y2="${H - PAD.b}"/><text class="ax" x="${fx(spot) + 4}" y="${PAD.t + 10}">Spot ${num(spot, 0)}</text>
      ${be.map(v => `<circle class="be" cx="${fx(v)}" cy="${z}" r="3.5"><title>Breakeven ${num(v, 2)}</title></circle>`).join('')}
    </svg>
    <p class="fno-note">At expiry, ${L.length} leg${L.length > 1 ? 's' : ''}, lot size ${lotOf()}. Ignores brokerage, taxes and margin.</p>`;
}

$('fno-body').addEventListener('click', (e) => {
  const cell = e.target.closest('td.pick');
  if (cell) {
    addLeg(cell.dataset.kind, Number(cell.dataset.strike), Number(cell.dataset.ltp), e.shiftKey ? 'sell' : 'buy');
    cell.classList.add('picked');
    setTimeout(() => cell.classList.remove('picked'), 400);
    return;
  }
  if (e.target.closest('#leg-add') && last?.chain) {
    const kind = $('leg-kind').value;
    const strike = kind === 'FUT' ? 0 : Number($('leg-strike').value);
    addLeg(kind, strike, ltpOf(last.chain, kind, strike) ?? 0, $('leg-side').value);
    render(last);
  } else if (e.target.closest('#leg-clear')) {
    legs = [];
    render(last);
  } else if (e.target.closest('.leg-del')) {
    legs.splice(Number(e.target.closest('tr').dataset.leg), 1);
    render(last);
  }
});
$('fno-body').addEventListener('change', (e) => {
  const row = e.target.closest('tr[data-leg]');
  if (!row) return;
  const l = legs[Number(row.dataset.leg)];
  const v = Number(e.target.value);
  if (e.target.name === 'lots' && Number.isInteger(v) && v >= 1) l.lots = v;
  if (e.target.name === 'premium' && v >= 0) l.premium = v;
  if (last?.chain) renderPayoffResult(last.chain);
});
