// Top Gainers/Losers modal. Same open/poll/close pattern as cas-feed.js.
import { $, esc } from './state.js';

const moversModal = $('movers-modal');
let moversUniverse = 'allSec';
let moversPoll = null, moversTrigger = null;
const nfmt = new Intl.NumberFormat('en-IN');

function openMovers() {
  moversTrigger = document.activeElement;
  moversModal.classList.add('open');
  $('movers-close').focus();
  loadMovers();
  clearInterval(moversPoll);
  moversPoll = setInterval(loadMovers, 10000);
}
function closeMovers() {
  moversModal.classList.remove('open');
  clearInterval(moversPoll);
  moversPoll = null;
  moversTrigger?.focus();
}

function moversTable(title, rows) {
  if (!rows.length) return `<div><h3>${title}</h3><div class="empty-note">No data.</div></div>`;
  const body = rows.map(r => {
    const cls = r.perChange === null || r.perChange === undefined ? '' : r.perChange >= 0 ? 'up' : 'down';
    return `<tr><td class="l"><strong>${esc(r.symbol)}</strong></td><td>${r.ltp ?? '–'}</td>
      <td class="${cls}">${r.perChange === null || r.perChange === undefined ? '–' : (r.perChange >= 0 ? '+' : '') + r.perChange.toFixed(2) + '%'}</td>
      <td>${r.volume ? nfmt.format(r.volume) : '–'}</td></tr>`;
  }).join('');
  return `<div><h3>${title}</h3><table class="opt-table feed-table"><thead><tr>
    <th class="l">Symbol</th><th>LTP</th><th>Chg %</th><th>Volume</th></tr></thead><tbody>${body}</tbody></table></div>`;
}

async function loadMovers() {
  let d;
  try {
    const res = await fetch(`/api/movers?universe=${moversUniverse}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    d = await res.json();
  } catch (e) {
    $('movers-body').innerHTML = '<div class="empty-note">Movers feed unreachable — retrying.</div>';
    return;
  }
  const pill = $('movers-asof');
  pill.dataset.live = String(d.available);
  pill.textContent = d.available ? 'Live' : 'Unavailable';
  if (!d.available) {
    $('movers-body').innerHTML = '<div class="empty-note">No mover data for this universe right now.</div>';
    return;
  }
  $('movers-body').innerHTML = `<div class="opt-grid">${moversTable('Gainers', d.gainers)}${moversTable('Losers', d.losers)}</div>`;
}

$('movers-btn').addEventListener('click', openMovers);
$('movers-close').addEventListener('click', closeMovers);
moversModal.addEventListener('mousedown', (e) => { if (e.target === moversModal) closeMovers(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && moversModal.classList.contains('open')) closeMovers(); });
$('movers-universe').addEventListener('click', (e) => {
  const btn = e.target.closest('button[data-universe]');
  if (!btn) return;
  moversUniverse = btn.dataset.universe;
  document.querySelectorAll('#movers-universe button').forEach(b => b.setAttribute('aria-pressed', String(b === btn)));
  loadMovers();
});
