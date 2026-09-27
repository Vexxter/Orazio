// Left-rail Call Auction Session summary panel: countdown + per-index open/close numbers.
import { $, esc } from './state.js';

let casPhase = null, casSeconds = null, casPollAt = 0, casStatus = '', casStage = '';

export function fmtCountdown(sec) {
  if (sec === null || sec === undefined) return '';
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), r = sec % 60;
  if (h) return `${h}h ${m}m`;
  if (m) return `${m}m ${String(r).padStart(2, '0')}s`;
  return `${r}s`;
}

export const CAS_PHASE_NAME = { 'pre-open': 'Pre-open', 'closing-auction': 'Closing auction', 'post-market': 'Post-market', 'post-close': 'Post-close', 'auction': 'Auction' };

function renderCasPhase() {
  const el = $('cas-phase');
  const live = casPhase in CAS_PHASE_NAME;
  el.dataset.live = String(live);
  // NSE's own wording, so a session our clock windows don't know about is still named right.
  el.title = [casStage, casStatus].filter(Boolean).join(' · ');
  if (live) {
    const name = CAS_PHASE_NAME[casPhase];
    el.textContent = casSeconds === null || casSeconds === undefined
      ? `${name} · running` : `${name} · ${fmtCountdown(casSeconds)} left`;
  } else if (casSeconds !== null && casSeconds !== undefined) {
    const next = CAS_PHASE_NAME[(casPhase || '').split(':')[1]] || 'Pre-open';
    el.textContent = `${next} in ${fmtCountdown(casSeconds)}`;
  } else {
    el.textContent = 'Next session';
  }
}

export async function loadCas() {
  let d;
  try {
    const res = await fetch('/api/cas');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    d = await res.json();
  } catch (e) {
    $('cas-note').textContent = "Auction feed unreachable — retrying.";
    return;
  }
  casPhase = d.phase;
  casSeconds = d.secondsRemaining;
  casStatus = d.nseStatus || '';
  casStage = d.stage || '';
  $('cas-stage').textContent = casStage;
  $('cas-stage').hidden = !casStage;
  casPollAt = Date.now();
  renderCasPhase();

  // Which number matters depends on the phase.
  const mode = (d.phase === 'closing-auction' || d.phase === 'post-market' || d.phase === 'post-close') ? 'close' : 'open';
  const available = d.indices.filter(r => r.available);
  const missing = d.indices.filter(r => !r.available);

  $('cas-rows').innerHTML = available.map(r => {
    const value = mode === 'close' ? (r.indicativeClose ?? r.last) : (r.open ?? r.last);
    const pct = mode === 'close' ? r.indicativeClosePct : r.openChangePct;
    const isAuction = mode === 'close' ? r.indicativeClose !== null : r.open !== null;
    const cls = pct === null || pct === undefined ? '' : pct >= 0 ? 'up' : 'down';
    const tag = mode === 'close' ? (r.indicativeClose !== null ? 'ICL' : 'LTP') : (r.open !== null ? 'Open' : 'LTP');
    return `<div class="cas-row${isAuction ? '' : ' muted'}">
      <span class="cas-sym">${esc(r.alias)}</span>
      <span class="cas-tag" title="${mode === 'close' ? 'Indicative close' : 'Auction-discovered open'}">${tag}</span>
      <span class="cas-val num">${value === null || value === undefined ? '–' : Number(value).toFixed(2)}</span>
      <span class="cas-chg num ${cls}">${pct === null || pct === undefined ? '' : (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%'}</span>
    </div>`;
  }).join('');

  const b = d.breadth;
  const breadthEl = $('cas-breadth');
  breadthEl.hidden = !b;
  if (b) {
    breadthEl.innerHTML = `<span class="up">${b.advances ?? '–'} ▲</span><span class="down">${b.declines ?? '–'} ▼</span><span>${b.unchanged ?? '–'} –</span>`;
    breadthEl.title = `F&O universe at ${b.asOf || 'pre-open'}`;
  }

  $('cas-note').textContent = missing.length
    ? `No public auction feed: ${missing.map(r => r.alias).join(', ')}`
    : '';
}

// Tick the countdown locally; re-poll fast inside a window, slowly outside one.
setInterval(() => {
  if (casSeconds !== null && casSeconds !== undefined) {
    const elapsed = Math.floor((Date.now() - casPollAt) / 1000);
    const left = casSeconds - elapsed;
    if (left >= 0) { const keep = casSeconds; casSeconds = left; renderCasPhase(); casSeconds = keep; }
  }
}, 1000);
setInterval(() => {
  const live = casPhase === 'pre-open' || casPhase === 'post-close';
  if (live || Date.now() - casPollAt > 60000) loadCas();
}, 5000);

$('cas-toggle').addEventListener('click', () => {
  const open = $('cas-toggle').getAttribute('aria-expanded') === 'true';
  $('cas-toggle').setAttribute('aria-expanded', String(!open));
  $('cas').classList.toggle('collapsed', open);
  try { localStorage.setItem('orazio.cas.collapsed', String(open)); } catch (e) { /* private mode */ }
});

try {
  if (localStorage.getItem('orazio.cas.collapsed') === 'true') {
    $('cas').classList.add('collapsed');
    $('cas-toggle').setAttribute('aria-expanded', 'false');
  }
} catch (e) { /* private mode */ }
