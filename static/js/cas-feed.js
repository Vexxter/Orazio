// Call auction: live feed window (stock-by-stock, with per-symbol order books).
// NSE keeps serving the last window's snapshot after pre-open closes, so every view
// states whether it is live or a snapshot and when it was stamped.
import { fmtCountdown } from './cas-panel.js';
import { $, esc } from './state.js';

const feedModal = $('feed-modal');
let feedRows = [], feedKey = 'FO', feedFilter = '', feedLadderFor = null;
let feedSort = { key: 'pChange', dir: -1 };
let feedLadderHtml = '';  // survives the 3s table re-render so the book doesn't flicker
let feedPoll = null, feedTrigger = null;

// Pre-open and the closing auction are different NSE feeds with different fields.
const PRE_COLS = [
  { key: 'symbol', label: 'Symbol', align: 'left' },
  { key: 'iep', label: 'IEP', dp: 2 },
  { key: 'pChange', label: 'Chg %', dp: 2, signed: true },
  { key: 'finalQuantity', label: 'Qty' },
  { key: 'buyQty', label: 'Buy' },
  { key: 'sellQty', label: 'Sell' },
  { key: 'atoBuy', label: 'ATO B' },
  { key: 'atoSell', label: 'ATO S' },
];
const CAS_COLS = [
  { key: 'symbol', label: 'Symbol', align: 'left' },
  { key: 'refPrice', label: 'Ref price', dp: 2 },
  { key: 'iep', label: 'IEP', dp: 2 },
  { key: 'pChange', label: 'Chg %', dp: 2, signed: true },
  { key: 'imbalanceEP', label: 'Imbalance @EP', plus: true },
  { key: 'imbalanceMO', label: 'Imbalance MO', plus: true },
  { key: 'buyQty', label: 'Total buy' },
  { key: 'sellQty', label: 'Total sell' },
  { key: 'lowerBand', label: 'Low band', dp: 2 },
  { key: 'upperBand', label: 'High band', dp: 2 },
];
let FEED_COLS = PRE_COLS;
const nfmt = new Intl.NumberFormat('en-IN');
const fcell = (v, c) => v === null || v === undefined ? '–'
  : c.dp !== undefined ? (c.signed && v >= 0 ? '+' : '') + Number(v).toFixed(c.dp)
  : c.plus ? (v > 0 ? '+' : '') + nfmt.format(v)
  : nfmt.format(v);

function openCasFeed() {
  feedTrigger = document.activeElement;
  feedModal.classList.add('open');
  $('feed-close').focus();
  loadCasFeed();
  clearInterval(feedPoll);
  feedPoll = setInterval(loadCasFeed, 3000);
}
function closeCasFeed() {
  feedModal.classList.remove('open');
  clearInterval(feedPoll);
  feedPoll = null;
  feedTrigger?.focus();
}

async function loadCasFeed() {
  let d;
  try {
    const res = await fetch(`/api/cas/feed?key=${feedKey}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    d = await res.json();
  } catch (e) {
    $('feed-body').innerHTML = '<div class="empty-note">Auction feed unreachable — retrying.</div>';
    return;
  }
  if (!d.available) {
    $('feed-body').innerHTML = `<div class="empty-note">${esc(d.reason || 'Feed unavailable')}</div>`;
    return;
  }
  feedRows = d.rows;
  const isCas = d.source === 'cas';
  FEED_COLS = isCas ? CAS_COLS : PRE_COLS;
  $('feed-title').textContent = isCas ? 'Closing Auction (CAS) · live feed' : 'Pre-open Auction · feed';
  // The F&O/All universe switch only applies to the pre-open feed; CAS is the F&O names.
  $('feed-universe').hidden = isCas;

  const pill = $('feed-pill');
  pill.dataset.live = String(!!d.live);
  if (d.live) {
    const left = d.secondsRemaining === null || d.secondsRemaining === undefined ? 'running' : `${fmtCountdown(d.secondsRemaining)} left`;
    pill.textContent = `Live · ${left}`;
    pill.title = d.stage || (isCas ? 'Closing auction is running' : 'Pre-open auction is running');
  } else {
    pill.textContent = `Snapshot · ${d.asOf || ''}`;
    pill.title = 'No auction is running; NSE is still serving the last window\'s snapshot';
  }

  const strip = $('feed-strip');
  if (isCas) {
    const t = d.totals || {};
    strip.innerHTML =
      (d.stage ? `<span class="feed-stage">${esc(d.stage)}</span>` : '') +
      `<span>${d.eligible ?? '–'} eligible F&amp;O stocks</span>` +
      `<span>Indicative qty ${t.indicativeQuantity ? nfmt.format(t.indicativeQuantity) : '–'}</span>` +
      `<span title="Positive = more buy interest than sell at the indicative price">Imbalance: <span class="up">+ buy surplus</span> / <span class="down">− sell surplus</span></span>` +
      `<span class="feed-strip-val">${d.statusMsg ? esc(d.statusMsg) : (d.status ? esc(d.status) : '')}</span>`;
  } else {
    const b = d.breadth || {};
    strip.innerHTML =
      `<span class="up">${b.advances ?? '–'} advancing</span>` +
      `<span class="down">${b.declines ?? '–'} declining</span>` +
      `<span>${b.unchanged ?? '–'} unchanged</span>` +
      `<span class="feed-strip-val">Traded ₹${b.tradedValue ? nfmt.format(Math.round(b.tradedValue / 1e7)) + ' Cr' : '–'}</span>`;
  }

  if (!d.rows.length && d.note) { $('feed-body').innerHTML = `<div class="empty-note">${esc(d.note)}</div>`; return; }
  renderFeedTable();
  // If a ladder is open, keep it in step with the table.
  if (feedLadderFor) loadLadder(feedLadderFor, true);
}

function renderFeedTable() {
  const q = feedFilter.trim().toUpperCase();
  const rows = feedRows
    .filter(r => !q || r.symbol.includes(q))
    .sort((a, b) => {
      const x = a[feedSort.key], y = b[feedSort.key];
      if (x === null || x === undefined) return 1;
      if (y === null || y === undefined) return -1;
      return (typeof x === 'string' ? x.localeCompare(y) : x - y) * feedSort.dir;
    });

  if (!rows.length) { $('feed-body').innerHTML = '<div class="empty-note">No symbols match that filter.</div>'; return; }

  const head = FEED_COLS.map(c =>
    `<th class="${c.align === 'left' ? 'l' : ''}" data-sort="${c.key}" aria-sort="${feedSort.key === c.key ? (feedSort.dir === 1 ? 'ascending' : 'descending') : 'none'}">${c.label}${feedSort.key === c.key ? (feedSort.dir === 1 ? ' ▲' : ' ▼') : ''}</th>`
  ).join('');

  const body = rows.map(r => {
    const cls = r.pChange === null || r.pChange === undefined ? '' : r.pChange >= 0 ? 'up' : 'down';
    const cells = FEED_COLS.map(c => {
      if (c.key === 'symbol') return `<td class="l"><strong>${esc(r.symbol)}</strong></td>`;
      // imbalance: positive = buy surplus (green), negative = sell surplus (red)
      const tone = c.plus ? (r[c.key] > 0 ? 'up' : r[c.key] < 0 ? 'down' : '') : (c.key === 'pChange' ? cls : '');
      return `<td class="${tone}">${fcell(r[c.key], c)}</td>`;
    }).join('');
    const ladder = feedLadderFor === r.symbol
      ? `<tr class="ladder-row"><td colspan="${FEED_COLS.length}"><div id="ladder-box">${feedLadderHtml || 'Loading order book…'}</div></td></tr>` : '';
    return `<tr class="feed-row${feedLadderFor === r.symbol ? ' open' : ''}" data-symbol="${esc(r.symbol)}">${cells}</tr>${ladder}`;
  }).join('');

  $('feed-body').innerHTML = `<table class="opt-table feed-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

async function loadLadder(symbol, silent) {
  feedLadderFor = symbol;
  if (!silent) renderFeedTable();
  let d;
  try {
    const res = await fetch(`/api/cas/feed?symbol=${encodeURIComponent(symbol)}`);
    d = await res.json();
  } catch (e) { d = null; }
  const box = $('ladder-box');
  if (!box) return;
  if (!d || !d.available || !d.ladder.length) { feedLadderHtml = '<em>No order book for this symbol.</em>'; box.innerHTML = feedLadderHtml; return; }
  const maxQty = Math.max(...d.ladder.map(r => Math.max(r.buyQty || 0, r.sellQty || 0)), 1);
  feedLadderHtml = `<div class="ladder">${d.ladder.map(r => `
    <div class="rung${r.isIep ? ' iep' : ''}">
      <span class="rq buy"><i style="width:${r.buyQty ? Math.max(2, Math.round(r.buyQty / maxQty * 100)) : 0}%"></i><b>${r.buyQty ? nfmt.format(r.buyQty) : ''}</b></span>
      <span class="rp num">${Number(r.price).toFixed(2)}${r.isIep ? ' ◂ IEP' : ''}${r.flag ? ` <small class="rflag" title="NSE flag, shown as published">${esc(r.flag)}</small>` : ''}</span>
      <span class="rq sell"><i style="width:${r.sellQty ? Math.max(2, Math.round(r.sellQty / maxQty * 100)) : 0}%"></i><b>${r.sellQty ? nfmt.format(r.sellQty) : ''}</b></span>
    </div>`).join('')}</div>
    <div class="ladder-foot">${d.source === 'cas' ? `Indicative ${d.iep ?? '–'}` : `ATO buy ${nfmt.format(d.atoBuy || 0)} · ATO sell ${nfmt.format(d.atoSell || 0)}`} · updated ${esc(d.updated || '')}</div>`;
  box.innerHTML = feedLadderHtml;
}

$('cas-open').addEventListener('click', openCasFeed);
$('feed-close').addEventListener('click', closeCasFeed);
feedModal.addEventListener('mousedown', (e) => { if (e.target === feedModal) closeCasFeed(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && feedModal.classList.contains('open')) closeCasFeed(); });
$('feed-filter').addEventListener('input', (e) => { feedFilter = e.target.value; renderFeedTable(); });
$('feed-universe').addEventListener('click', (e) => {
  const btn = e.target.closest('button[data-key]');
  if (!btn) return;
  feedKey = btn.dataset.key;
  document.querySelectorAll('#feed-universe button').forEach(b => b.setAttribute('aria-pressed', String(b === btn)));
  loadCasFeed();
});
$('feed-body').addEventListener('click', (e) => {
  const th = e.target.closest('th[data-sort]');
  if (th) {
    const key = th.dataset.sort;
    feedSort = { key, dir: feedSort.key === key ? -feedSort.dir : (key === 'symbol' ? 1 : -1) };
    renderFeedTable();
    return;
  }
  const row = e.target.closest('.feed-row');
  if (row) {
    const sym = row.dataset.symbol;
    if (feedLadderFor === sym) { feedLadderFor = null; feedLadderHtml = ''; renderFeedTable(); }
    else { feedLadderHtml = ''; loadLadder(sym); }
  }
});
