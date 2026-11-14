// Insights hub: one modal, one tab per research view (flows, options analytics, breadth, ...). Each tab
// lives in its own insights-*.js module and registers itself here with registerTab(); this file only
// owns the modal, the tab strip, polling and the "as of" pill. The last tab used is remembered.
// Tabs are grouped by the job an analyst is doing (GROUPS), not by data source: a row of groups, then the
// tabs of the open group, so 30+ views read as seven questions.
import { FUNCTIONS } from './command-parse.js';
import { switchSymbol } from './symbol.js';
import { $, esc, visible } from './state.js';

const KEY = 'orazio.insights.v1';
const modal = $('insights-modal');
const tabsEl = $('insights-tabs');
const body = $('insights-body');
const tabs = new Map();   // id -> { label, render(body, ctx), pollMs }
let current = null;
let poll = null, trigger = null, generation = 0;

// Each tab's feeds, named in a source line under it. Registry: /api/sources (orazio/provenance.py).
const TAB_FEEDS = {
  brief: ['yahoo', 'gift', 'bonds', 'spot', 'flows', 'macro', 'news'], flows: ['flows'], options: ['options'], breadth: ['screener'],
  delivery: ['delivery'], rollover: ['fno-archive'], rotation: ['yahoo'], correlation: ['yahoo', 'bonds', 'spot'], seasonality: ['yahoo'],
  events: ['yahoo'], rates: ['bonds', 'corp-bonds'], macro: ['macro'], alerts: ['yahoo'], watchlist: ['yahoo', 'delivery'],
  filings: ['filings'], holdings: ['shareholding'], optbt: ['option-backtest'], portfolio: ['yahoo'], insider: ['insider'], company: ['fundamentals'], earnings: ['earnings'], calendar: ['ipos'], ratepath: ['rate-path'],
};
let feedInfo = null;
async function sourceLine(id) {
  if (!TAB_FEEDS[id]) return '';
  feedInfo ||= fetch('/api/sources').then(r => r.json()).then(d => new Map(d.feeds.map(f => [f.id, f]))).catch(() => { feedInfo = null; return new Map(); });
  const info = await feedInfo;
  const parts = TAB_FEEDS[id].map(k => info.get(k)).filter(Boolean)
    .map(f => `<a href="${esc(f.url)}" target="_blank" rel="noopener noreferrer">${esc(f.source)}</a> (${esc(f.delay)})`);
  return parts.length ? `<p class="ins-note ins-source">Source: ${parts.join(' · ')}. Type <b>:SRC</b> for feed health.</p>` : '';
}

// [id, label, what the group answers, tab ids in order]. A tab not listed lands in "More".
export const GROUPS = [
  ['today', 'Today', 'What changed and what is coming', ['changes', 'brief', 'earnings', 'calendar', 'flows', 'breadth']],
  ['find', 'Find', 'Ideas: screens, insiders, deals, rotation', ['find', 'insider', 'delivery', 'rotation', 'correlation']],
  ['stock', 'Stock', 'One company, in depth', ['company', 'holdings', 'filings', 'events', 'seasonality']],
  ['deriv', 'Derivatives', 'Positioning, volatility, backtests', ['options', 'optbt', 'rollover']],
  ['rates', 'Rates & macro', 'Curves, policy path, the calendar', ['rates', 'ratepath', 'macro']],
  ['book', 'My book', 'Watchlist, portfolio, risk, alerts', ['watchlist', 'portfolio', 'risk', 'alerts', 'journal', 'workspaces']],
  ['more', 'More', 'Excel, settings, sources, every command', ['excel', 'settings', 'sources', 'commands']],
];
export const groupOf = (id) => (GROUPS.find(g => g[3].includes(id)) || GROUPS.at(-1))[0];
const lastInGroup = {};   // group -> last tab opened there, so a group click returns where you were

try { current = localStorage.getItem(KEY); } catch (e) { /* first tab */ }

// render(body, ctx) draws the tab into `body`; ctx.pill(text, live) sets the header pill and ctx.stale()
// is true once the user has moved on (another tab, or closed), so a slow fetch doesn't paint over them.
// reset() (optional) drops the tab's own symbol choice so it follows the chart again (the command line uses it).
export function registerTab(id, label, render, { pollMs = 0, title = '', reset = null } = {}) {
  tabs.set(id, { label, render, pollMs, title, reset });
  paintTabs();
}

// The command that opens a tab, shown on hover and in hints: the fast path, taught in passing.
export const commandFor = (id) => Object.entries(FUNCTIONS).find(([, [action]]) => action === `tab:${id}`)?.[0] || null;

function paintTabs() {
  const open = groupOf(current && tabs.has(current) ? current : 'changes');
  const groups = GROUPS.filter(([g]) => [...tabs.keys()].some(k => groupOf(k) === g)).map(([g, label, what]) =>
    `<button type="button" class="ins-group" data-group="${g}" aria-pressed="${g === open}" title="${esc(what)}">${esc(label)}</button>`).join('');
  const inGroup = [...tabs.keys()].filter(k => groupOf(k) === open);
  const order = (GROUPS.find(g => g[0] === open) || GROUPS.at(-1))[3];
  inGroup.sort((a, b) => (order.indexOf(a) + 1 || 99) - (order.indexOf(b) + 1 || 99));
  const row = inGroup.map((k) => {
    const t = tabs.get(k), hint = commandFor(k);
    const tip = [t.title, hint && `Command: :${hint}`].filter(Boolean).join(' · ');
    return `<button type="button" role="tab" data-tab="${esc(k)}" aria-selected="${k === current}"${tip ? ` title="${esc(tip)}"` : ''}>${esc(t.label)}${hint ? `<kbd>:${esc(hint)}</kbd>` : ''}</button>`;
  }).join('');
  tabsEl.innerHTML = `<div class="ins-groups" role="group" aria-label="Insight groups">${groups}</div><div class="ins-tabrow" role="tablist">${row}</div>`;
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
    const line = await sourceLine(current);
    if (line && !ctx.stale()) body.insertAdjacentHTML('beforeend', line);
  } catch (e) {
    if (!ctx.stale()) body.innerHTML = `<div class="empty-note">Couldn't load ${esc(tab.label)}: ${esc(e.message)}</div>`;
  }
  if (keepScroll && !ctx.stale()) body.scrollTop = top;
}

export function showTab(id) {
  if (!tabs.has(id)) id = tabs.has('changes') ? 'changes' : tabs.keys().next().value;   // first visit: the inbox
  current = id;
  lastInGroup[groupOf(id)] = id;
  generation++;
  try { localStorage.setItem(KEY, id); } catch (e) { /* not persisted */ }
  paintTabs();
  document.dispatchEvent(new CustomEvent('insights:tab', { detail: { id } }));
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

tabsEl.addEventListener('click', (e) => {
  const g = e.target.closest('[data-group]');
  if (g) {
    const order = (GROUPS.find(x => x[0] === g.dataset.group) || GROUPS.at(-1))[3];
    const first = lastInGroup[g.dataset.group] || order.find(k => tabs.has(k)) || [...tabs.keys()].find(k => groupOf(k) === g.dataset.group);
    if (first) showTab(first);
    return;
  }
  const b = e.target.closest('[data-tab]');
  if (b) { showTab(b.dataset.tab); document.dispatchEvent(new CustomEvent('insights:clicked', { detail: { id: b.dataset.tab } })); }
});
$('insights-btn').addEventListener('click', () => openInsights());
$('insights-close').addEventListener('click', close);
modal.addEventListener('click', (e) => { if (e.target === modal) close(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && modal.classList.contains('open')) close(); });
