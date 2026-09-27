import { $, clockFmt, dateTimeFmt, state, timeFmt } from './state.js';

export function toast(message, kind = 'info') {
  const el = document.createElement('div');
  el.className = `toast ${kind}`;
  el.textContent = message;
  $('toasts').appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

export function setLoading(on) { $('chart-wrap').classList.toggle('is-loading', on); }

export function showChartState(title, text) {
  $('chart-state-title').textContent = title;
  $('chart-state-text').textContent = text;
  $('chart-state').classList.add('show');
}
export function hideChartState() { $('chart-state').classList.remove('show'); }

export function setConn(connState, text, title = '') {
  const el = $('conn');
  el.dataset.state = connState;
  el.textContent = text || (connState === 'ok' ? 'Live' : connState === 'err' ? 'Reconnecting…' : 'Connecting…');
  el.title = title;
}

// Be honest about how old the data is: some feeds are delayed by their provider (SENSEX on
// Yahoo ~15 min, CME futures ~10 min) and that must read as "delayed", not as a broken app.
const SOURCE_LABEL = { yahoo: 'Yahoo Finance', bse: 'BSE India', nse: 'NSE India', yfinance: 'Yahoo Finance (fallback)' };
export function showFreshness(q) {
  const age = q.delaySec;
  const via = SOURCE_LABEL[q.source] || q.source;
  if (age === null || age === undefined) { setConn('ok', 'Live', `Source: ${via}`); return; }
  // 150s, not 90: BSE stamps SENSEX to the minute and publishes once a minute, so a
  // perfectly healthy feed still reads up to ~2 min old and must not say "Delayed".
  if (age <= 150) { setConn('ok', `Live · ${age}s`, `Source: ${via} · last tick ${age}s ago`); return; }
  if (age <= 1800) { setConn('err', `Delayed ${Math.round(age / 60)}m`, `${via} publishes this feed ~${Math.round(age / 60)} minutes late — the delay is at the source`); return; }
  setConn('idle', `Closed · ${timeFmt.format(new Date(q.marketTime * 1000))}`, `Market is closed. Last tick at ${dateTimeFmt.format(new Date(q.marketTime * 1000))} IST`);
}

export function setIntervalUI(value) {
  state.selectedInterval = value;
  document.querySelectorAll('#interval-seg button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.interval === value)));
}
export function setRangeUI(value) {
  document.querySelectorAll('#range-bar button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.range === value)));
}

setInterval(() => { $('clock').textContent = clockFmt.format(new Date()) + ' IST'; }, 1000);
$('clock').textContent = clockFmt.format(new Date()) + ' IST';
