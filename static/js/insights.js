// Insights hub: one modal, one tab per research view (flows, options analytics, breadth, ...). Each tab
// lives in its own insights-*.js module and registers itself here with registerTab(); this file only
// owns the modal, the tab strip, polling and the "as of" pill. The last tab used is remembered.
import { switchSymbol } from './symbol.js';
import { $, esc, visible } from './state.js';

const KEY = 'orazio.insights.v1';
const modal = $('insights-modal');
const tabsEl = $('insights-tabs');
const body = $('insights-body');
const tabs = new Map();   // id -> { label, render(body, ctx), pollMs }
let current = null;
let poll = null, trigger = null, generation = 0;

try { current = localStorage.getItem(KEY); } catch (e) { /* first tab */ }

// render(body, ctx) draws the tab into `body`; ctx.pill(text, live) sets the header pill and ctx.stale()
// is true once the user has moved on (another tab, or closed), so a slow fetch doesn't paint over them.
// reset() (optional) drops the tab's own symbol choice so it follows the chart again (the command line uses it).
export function registerTab(id, label, render, { pollMs = 0, title = '', reset = null } = {}) {
  tabs.set(id, { label, render, pollMs, title, reset });
  tabsEl.innerHTML = [...tabs].map(([k, t]) => `<button type="button" role="tab" data-tab="${esc(k)}" aria-selected="false"${t.title ? ` title="${esc(t.title)}"` : ''}>${esc(t.label)}</button>`).join('');
}

function pill(textContent, live = true) {
  const el = $('insights-pill');
  el.textContent = textContent || '';
  el.dataset.live = String(!!live);
  el.hidden = !textContent;
}

async function draw(keepScroll = false) {
  const tab = tabs.get(current);
  if (!tab) return;
  const my = generation;
  const ctx = { pill, stale: () => my !== generation || !modal.classList.contains('open') };
  const top = body.scrollTop;
  try {
    await tab.render(body, ctx);
  } catch (e) {
    if (!ctx.stale()) body.innerHTML = `<div class="empty-note">Couldn't load ${esc(tab.label)}: ${esc(e.message)}</div>`;
  }
  if (keepScroll && !ctx.stale()) body.scrollTop = top;
}

export function showTab(id) {
  if (!tabs.has(id)) id = tabs.keys().next().value;
  current = id;
  generation++;
  try { localStorage.setItem(KEY, id); } catch (e) { /* not persisted */ }
  tabsEl.querySelectorAll('[data-tab]').forEach(b => b.setAttribute('aria-selected', String(b.dataset.tab === id)));
  body.innerHTML = '<div class="empty-note">Loading…</div>';
  pill('');
  clearInterval(poll);
  poll = null;
  const { pollMs } = tabs.get(id);
  if (pollMs) poll = setInterval(visible(() => draw(true)), pollMs);
  draw();
}

export function openInsights(id = current, { reset = false } = {}) {
  if (reset) tabs.get(id)?.reset?.();
  if (!modal.classList.contains('open')) {
    trigger = document.activeElement;
    modal.classList.add('open');
  }
  showTab(id);
  tabsEl.querySelector('[aria-selected="true"]')?.focus();
}

function close() {
  modal.classList.remove('open');
  generation++;
  clearInterval(poll);
  poll = null;
  trigger?.focus();
}

// Daily (or weekly) bars for research tabs, cached for 10 minutes so switching tabs doesn't refetch.
const barCache = new Map();
export async function historyBars(symbol, range = '5Y', interval = '1d') {
  const key = `${symbol}|${range}|${interval}`;
  const hit = barCache.get(key);
  if (hit && Date.now() - hit.at < 600000) return hit.bars;
  const res = await fetch(`/api/candles?symbol=${encodeURIComponent(symbol)}&interval=${interval}&range=${range}`);
  if (!res.ok) throw new Error(`${symbol}: HTTP ${res.status}`);
  const bars = (await res.json()).candles || [];
  barCache.set(key, { at: Date.now(), bars });
  return bars;
}

// Tabs re-render themselves on their own controls; this re-draws the current tab on demand.
export const redraw = () => draw(true);

// Any row or tile carrying data-symbol charts that symbol (and closes the hub so the chart is visible).
function chartRow(e) {
  const tr = e.target.closest('[data-symbol]');
  if (!tr || (e.type === 'keydown' && e.key !== 'Enter')) return;
  close();
  $('symbol-input').value = tr.dataset.symbol;
  switchSymbol(tr.dataset.symbol);
}
body.addEventListener('click', chartRow);
// A tab asked Compare to show a pair (correlation cell): get out of the way.
document.addEventListener('compare:pair', () => { if (modal.classList.contains('open')) close(); });
body.addEventListener('keydown', chartRow);

tabsEl.addEventListener('click', (e) => { const b = e.target.closest('[data-tab]'); if (b) showTab(b.dataset.tab); });
$('insights-btn').addEventListener('click', () => openInsights());
$('insights-close').addEventListener('click', close);
modal.addEventListener('click', (e) => { if (e.target === modal) close(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && modal.classList.contains('open')) close(); });
