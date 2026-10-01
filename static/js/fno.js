// Options panel. NSE symbols: front/next/far futures (price, basis, OI) and the option chain (OI ladder, PCR,
// max pain, ATM straddle) from orazio/fno.py -> NSE's own feeds. Any other symbol that Yahoo has options for
// (US stocks and ETFs): Yahoo's option chain from /api/options, in the same panel.
import { compactIN } from './format.js';
import { $, displayName, esc, state } from './state.js';

const modal = $('fno-modal');
let tab = 'fut';
let poll = null;
let trigger = null;
let expiry = null;      // chosen option expiry (null = nearest)
let forSymbol = null;   // symbol the current expiry choice belongs to
let inFlight = false;
let usMode = false;     // the symbol has no NSE contracts, so the panel is showing Yahoo's option chain

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
  poll = setInterval(() => { if (!usMode) load(); }, 5000);     // Yahoo's chain moves slowly: loaded on open, on expiry change and on symbol change only
}
function close() {
  modal.classList.remove('open');
  clearInterval(poll);
  poll = null;
  trigger?.focus();
}

async function load() {
  if (inFlight) return;
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
  } finally { inFlight = false; }
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
  $('fno-title').textContent = `Options · ${d.name}`;
  const asOf = (tab === 'chain' ? d.chain?.asOf : d.asOf) || d.asOf || '';
  pill.dataset.live = 'true';
  pill.textContent = asOf ? `Live · ${asOf.split(' ').pop()}` : 'Live';

  const onFutures = d.futureSymbol === state.currentSymbol;
  const canSwap = $('futures-toggle').classList.contains('shown');
  const swap = canSwap
    ? `<button type="button" class="btn fno-swap" id="fno-swap">Chart the ${onFutures ? 'spot' : 'future'} instead</button>` : '';

  const ch = d.chain;
  const sel = $('fno-expiry');
  sel.hidden = tab !== 'chain' || !ch || !ch.expiries?.length;
  $('fno-window').hidden = tab !== 'chain';
  if (!sel.hidden) {
    sel.innerHTML = ch.expiries.map(e => `<option value="${esc(e)}"${e === ch.expiry ? ' selected' : ''}>${esc(e)}</option>`).join('');
  }

  if (tab === 'fut') {
    $('fno-strip').innerHTML = `<span>Spot <b class="num">${num(d.spot)}</b></span><span class="fno-note">Basis = future − spot. Volume is in contracts.</span><span class="feed-strip-val">${swap}</span>`;
    $('fno-body').innerHTML = futuresTable(d);
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
    $('fno-body').innerHTML = chainTable(ch);
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

function chainTable(ch) {
  const win = $('fno-window').value;
  let rows = ch.rows;
  if (win !== 'all') {
    const i = rows.findIndex(r => r.strike === ch.atm);
    const n = Number(win);
    rows = rows.slice(Math.max(0, i - n), i + n + 1);
  }
  const maxOi = Math.max(1, ...rows.map(r => Math.max(r.ce?.oi || 0, r.pe?.oi || 0)));
  const bar = (oi, side) => `style="--w:${Math.round(((oi || 0) / maxOi) * 100)}%" class="oi ${side}"`;
  const at = (s, k, f) => (s ? f(s[k]) : '–');
  const body = rows.map(r => {
    const ce = r.ce, pe = r.pe;
    return `<tr class="${r.strike === ch.atm ? 'atm' : ''}">
      <td ${bar(ce?.oi, 'ce')}>${at(ce, 'oi', big)}</td>
      <td class="${cls(ce?.dOi)}">${at(ce, 'dOi', delta)}</td>
      <td>${at(ce, 'volume', big)}</td><td>${at(ce, 'iv', (v) => num(v, 1))}</td>
      <td class="${cls(ce?.change)}"><strong>${at(ce, 'ltp', num)}</strong></td>
      <td class="strike"><strong>${num(r.strike, 0)}</strong></td>
      <td class="${cls(pe?.change)}"><strong>${at(pe, 'ltp', num)}</strong></td>
      <td>${at(pe, 'iv', (v) => num(v, 1))}</td><td>${at(pe, 'volume', big)}</td>
      <td class="${cls(pe?.dOi)}">${at(pe, 'dOi', delta)}</td>
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
// "Chart the future/spot instead" drives the same toolbar toggle the user would click.
modal.addEventListener('click', (e) => {
  if (!e.target.closest('#fno-swap')) return;
  const toggle = $('futures');
  toggle.checked = !toggle.checked;
  toggle.dispatchEvent(new Event('change'));
  close();
});
