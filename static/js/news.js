// Side panel: headlines for the symbol on the chart, refreshed every minute and on symbol change.
import { ago } from './format.js';
import { $, displayName, esc, state } from './state.js';

const panel = $('news');
const list = $('news-list');
const OPEN_KEY = 'orazio.news.open';
const POLL_MS = 60000;

let open = true;
let shownSymbol = null;
let lastFetch = 0;
let inFlight = false;
let seenUrls = new Set();
let items = [];
let fetchedAt = 0;

try { open = localStorage.getItem(OPEN_KEY) !== '0'; } catch (e) { /* storage unavailable: default open */ }

function render(fresh = new Set()) {
  $('news-title').textContent = `News · ${displayName(state.currentSymbol)}`;
  $('news-updated').textContent = fetchedAt ? `updated ${ago(fetchedAt)}` : '';
  if (!items.length) return;
  list.innerHTML = items.map(it => {
    const safe = /^https?:\/\//i.test(it.url) ? it.url : '#';
    return `<a class="news-item${fresh.has(it.url) ? ' is-new' : ''}" href="${esc(safe)}" target="_blank" rel="noopener noreferrer">
      <div class="news-title">${esc(it.title)}</div>
      <div class="news-meta">${esc(it.publisher || 'News')} · <span data-t="${it.time}">${ago(it.time)}</span></div></a>`;
  }).join('');
}

async function load() {
  if (inFlight || !open) return;
  inFlight = true;
  const symbol = state.currentSymbol;
  try {
    const res = await fetch(`/api/news?symbol=${encodeURIComponent(symbol)}`);
    if (!res.ok) throw new Error();
    const d = await res.json();
    if (symbol !== state.currentSymbol) return; // user moved on while this was loading
    const sameSymbol = shownSymbol === symbol;
    const fresh = sameSymbol ? new Set(d.items.map(i => i.url).filter(u => !seenUrls.has(u))) : new Set();
    seenUrls = new Set(d.items.map(i => i.url));
    shownSymbol = symbol;
    lastFetch = Date.now();
    fetchedAt = d.fetchedAt;
    if (!d.available) {
      items = [];
      list.innerHTML = '<div class="news-empty">News source unreachable — retrying.</div>';
    } else if (!d.items.length) {
      items = [];
      list.innerHTML = `<div class="news-empty">No recent headlines for ${esc(displayName(symbol))}.</div>`;
    } else {
      items = d.items;
      render(fresh);
    }
    $('news-title').textContent = `News · ${displayName(symbol)}`;
    $('news-updated').textContent = `updated ${ago(fetchedAt)}`;
  } catch (e) {
    if (shownSymbol !== symbol) list.innerHTML = '<div class="news-empty">Couldn\'t load news.</div>';
  } finally {
    inFlight = false;
  }
}

function setOpen(next) {
  open = next;
  panel.hidden = !open;
  $('news-btn').setAttribute('aria-pressed', String(open));
  try { localStorage.setItem(OPEN_KEY, open ? '1' : '0'); } catch (e) { /* not persisted */ }
  if (open) load();
}

$('news-btn').addEventListener('click', () => setOpen(!open));

// One light tick: reload on symbol change or every minute.
setInterval(() => {
  if (!open) return;
  if (state.currentSymbol !== shownSymbol) {
    if (!inFlight) { list.innerHTML = '<div class="news-empty">Loading…</div>'; items = []; }
    load();
  } else if (Date.now() - lastFetch >= POLL_MS) load();
}, 1000);

// Keep the "3m ago" labels honest without rebuilding the list (which would drop hover/focus).
setInterval(() => {
  list.querySelectorAll('[data-t]').forEach(el => { el.textContent = ago(+el.dataset.t); });
  if (fetchedAt) $('news-updated').textContent = `updated ${ago(fetchedAt)}`;
}, 20000);

setOpen(open);
