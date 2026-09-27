// Options-chain modal.
import { $, displayName, esc, state } from './state.js';

const optionsModal = $('options-modal');
let optionsTrigger = null;

function closeOptions() {
  optionsModal.classList.remove('open');
  optionsTrigger?.focus();
}
$('options-btn').addEventListener('click', () => { optionsTrigger = $('options-btn'); openOptions(); });
$('options-close').addEventListener('click', closeOptions);
optionsModal.addEventListener('mousedown', (e) => { if (e.target === optionsModal) closeOptions(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && optionsModal.classList.contains('open')) closeOptions(); });
$('expiry-select').addEventListener('change', (e) => openOptions(e.target.value));

async function openOptions(expiry) {
  optionsModal.classList.add('open');
  const body = $('options-body');
  const sym = state.resolvedSymbol || state.currentSymbol;
  $('options-title').textContent = `Options · ${displayName(sym)}`;
  if (!expiry) $('options-close').focus();
  body.innerHTML = '<div class="empty-note">Loading option chain…</div>';
  let data;
  try {
    const url = `/api/options?symbol=${encodeURIComponent(sym)}` + (expiry ? `&expiry=${encodeURIComponent(expiry)}` : '');
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    data = await res.json();
  } catch (e) {
    $('expiry-select').hidden = true;
    body.innerHTML = '<div class="empty-note">Couldn\'t load the option chain. Try again in a moment.</div>';
    return;
  }
  if (!data.available) {
    $('expiry-select').hidden = true;
    body.innerHTML = `<div class="empty-note"><strong>Options aren't available for ${esc(sym)}.</strong><br>${esc(data.reason || 'The data provider has no option chain for this symbol.')}</div>`;
    return;
  }
  const expirySelect = $('expiry-select');
  expirySelect.innerHTML = data.expiries.map(e => `<option value="${esc(e)}" ${e === data.expiry ? 'selected' : ''}>${esc(e)}</option>`).join('');
  expirySelect.hidden = false;

  const nf = new Intl.NumberFormat('en-US');
  const fmt = (v, dp) => v === null || v === undefined ? '–' : (dp === undefined ? nf.format(v) : v.toFixed(dp));
  const atm = state.lastPolledPrice && data.calls.length
    ? data.calls.reduce((best, r) => Math.abs(r.strike - state.lastPolledPrice) < Math.abs(best - state.lastPolledPrice) ? r.strike : best, data.calls[0].strike)
    : null;
  const table = (label, rows) => `<div><h3>${label}</h3><table class="opt-table"><thead><tr>
      <th>Strike</th><th>Last</th><th>Bid</th><th>Ask</th><th>Vol</th><th>OI</th></tr></thead><tbody>${
    rows.map(r => `<tr class="${r.strike === atm ? 'atm' : ''}"><td>${fmt(r.strike, 2)}</td><td>${fmt(r.lastPrice, 2)}</td><td>${fmt(r.bid, 2)}</td><td>${fmt(r.ask, 2)}</td><td>${fmt(r.volume)}</td><td>${fmt(r.openInterest)}</td></tr>`).join('')
  }</tbody></table></div>`;
  body.innerHTML = `<div class="opt-grid">${table('Calls', data.calls)}${table('Puts', data.puts)}</div>`;
}
