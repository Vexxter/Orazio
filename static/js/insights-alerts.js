// Insights › Alerts: price, day-change, RSI and moving-average alerts. The server checks them every 20 s whether or
// not this page is open (orazio/alerts.py) and pushes to the channels in Settings; this tab manages the rules and
// shows a toast for anything that fired while it's open. Every rule can be backtested first: how often it fired over
// the symbol's daily history and what the price did 1–20 sessions later (alert-rules.js, insights-math.js eventStudy()).
import { RULES, describe, fires } from './alert-rules.js';
import { esc } from './format.js';
import { dayKey, eventStudy } from './insights-math.js';
import { historyBars, redraw, registerTab } from './insights.js';
import { state } from './state.js';
import { toast } from './ui.js';

const KEY = 'orazio.alerts.v1';
const CHECK_MS = 20000;
let store = { alerts: [], log: [] };
let lastSeen = null;   // newest log entry already shown
let draft = { type: 'above', value: '' };
let backtest = null;   // { rule, result }
const f = (v, d = 2) => (v === null || v === undefined ? '–' : v.toFixed(d));
const cls = (v) => (v > 0 ? 'up' : v < 0 ? 'down' : '');

const api = async (path, opts) => {
  const r = await fetch(path, opts && { ...opts, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(opts.body ?? {}) });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || `HTTP ${r.status}`);
  return d;
};

// Rules a browser kept before the server took over. They leave localStorage only once the server has them.
async function migrate() {
  let local = null;
  try { local = JSON.parse(localStorage.getItem(KEY) || 'null'); } catch (e) { return; }
  if (!local) return;
  try {
    await api('/api/alerts/import', { method: 'POST', body: { alerts: local.alerts, log: local.log } });
    localStorage.removeItem(KEY);
  } catch (e) { /* kept for the next load */ }
}

// ---------- what fired while this page is open ----------
async function refresh() {
  store = await api('/api/alerts');
  const newest = store.log[0]?.at ?? '';
  if (lastSeen !== null && newest > lastSeen) {
    store.log.filter(l => l.at > lastSeen).reverse().forEach(l => toast(`🔔 ${l.msg}`, 'info'));
  }
  lastSeen = newest;
}
migrate().then(refresh).catch(() => {});
setInterval(() => { refresh().catch(() => {}); }, CHECK_MS);

// ---------- backtest ----------
async function runBacktest(rule) {
  const bars = await historyBars(rule.symbol, 'ALL');
  const hits = fires(bars, rule);
  return { bars: bars.length, from: bars[0] ? new Date(bars[0].time * 1000).getFullYear() : null, ...eventStudy(bars, hits.map(i => dayKey(bars[i].time)), [1, 5, 10, 20]) };
}

function backtestHtml() {
  if (!backtest) return '';
  const { rule, result: r } = backtest;
  if (!r.events.length) return `<div class="ins-sec"><h3>Backtest · ${esc(describe(rule))}</h3><div class="empty-note">Never fired in ${r.bars} daily bars.</div></div>`;
  const perYear = r.events.length / Math.max(1, new Date().getFullYear() - r.from + 1);
  return `<div class="ins-sec"><h3>Backtest · ${esc(describe(rule))} · since ${r.from}</h3>
    <div class="ins-cards"><div class="ins-card"><div class="k">Times it fired</div><div class="v">${r.events.length}</div><div class="s">~${perYear.toFixed(1)} a year</div></div>
    ${r.stats.map(s => `<div class="ins-card"><div class="k">Next ${s.h} session${s.h > 1 ? 's' : ''}</div><div class="v ${cls(s.avg)}">${f(s.avg)}%</div><div class="s">median ${f(s.median)}% · up ${f(s.up, 0)}%</div></div>`).join('')}</div>
    <p class="ins-note">Last fires: ${r.events.slice(-8).reverse().map(e => new Date(e.day * 86400000).toISOString().slice(0, 10)).join(', ')}</p></div>`;
}

// ---------- tab ----------
async function render(body, ctx) {
  await refresh();
  if (ctx.stale()) return;
  ctx.pill(`${store.alerts.filter(a => a.active).length} active`);
  const rows = store.alerts.map((a) => `<tr><td style="text-align:left">${esc(describe(a))}</td><td>${a.lastFired ? esc(a.lastFired) : '–'}</td>
    <td><button type="button" class="btn" data-act="toggle" data-id="${esc(a.id)}">${a.active ? 'Pause' : 'Resume'}</button>
    <button type="button" class="btn" data-act="test" data-id="${esc(a.id)}">Backtest</button>
    <button type="button" class="btn" data-act="del" data-id="${esc(a.id)}" aria-label="Delete alert">✕</button></td></tr>`).join('');
  body.innerHTML = `<div class="ins-bar">
      <label>Symbol <input class="ins-input" id="al-sym" value="${esc(draft.symbol || state.currentSymbol)}" style="width:130px"></label>
      <select class="select" id="al-type" aria-label="Condition">${Object.entries(RULES).map(([k, r]) => `<option value="${k}"${k === draft.type ? ' selected' : ''}>${esc(r.label)}</option>`).join('')}</select>
      <input class="ins-input" id="al-val" type="number" step="any" placeholder="value" value="${esc(draft.value)}" style="width:110px" aria-label="Value">
      <button type="button" class="btn" id="al-test">Backtest</button>
      <button type="button" class="btn primary" id="al-add">Add alert</button>
      <button type="button" class="btn" id="al-settings">Where alerts go…</button>
    </div>
    ${backtestHtml()}
    <div class="ins-sec"><h3>Alerts (checked every 20 s while Orazio is running, even with this page closed; each fires at most once a day)</h3>
      ${rows ? `<table class="opt-table"><thead><tr><th style="text-align:left">Rule</th><th>Last fired</th><th></th></tr></thead><tbody>${rows}</tbody></table>` : '<div class="empty-note">No alerts yet.</div>'}</div>
    <div class="ins-sec"><h3>Recently fired</h3>${store.log.length ? store.log.slice(0, 15).map(l => `<div class="ins-note">${esc(l.at.slice(0, 16).replace('T', ' '))} IST · ${esc(l.msg)}</div>`).join('') : '<div class="ins-note">Nothing yet.</div>'}</div>`;

  const readDraft = () => {
    draft = { symbol: body.querySelector('#al-sym').value.trim().toUpperCase(), type: body.querySelector('#al-type').value, value: body.querySelector('#al-val').value };
    const value = parseFloat(draft.value);
    if (!draft.symbol || !Number.isFinite(value)) { toast('Enter a symbol and a number', 'error'); return null; }
    return { symbol: draft.symbol, type: draft.type, value };
  };
  body.querySelector('#al-test').addEventListener('click', async () => {
    const rule = readDraft();
    if (!rule) return;
    backtest = { rule, result: await runBacktest(rule) };
    redraw();
  });
  body.querySelector('#al-add').addEventListener('click', async () => {
    const rule = readDraft();
    if (!rule) return;
    try {
      await api('/api/alerts', { method: 'POST', body: rule });
      draft = { type: draft.type, value: '' };
      redraw();
    } catch (e) { toast(e.message, 'error'); }
  });
  body.querySelector('#al-settings').addEventListener('click', () => document.querySelector('#insights-tabs [data-tab="settings"]')?.click());
  body.querySelectorAll('[data-act]').forEach(b => b.addEventListener('click', async () => {
    const a = store.alerts.find(x => x.id === b.dataset.id);
    if (!a) return;
    try {
      if (b.dataset.act === 'toggle') await api(`/api/alerts/${encodeURIComponent(a.id)}`, { method: 'PATCH', body: { active: !a.active } });
      else if (b.dataset.act === 'del') await api(`/api/alerts/${encodeURIComponent(a.id)}`, { method: 'DELETE' });
      else backtest = { rule: a, result: await runBacktest(a) };
      redraw();
    } catch (e) { toast(e.message, 'error'); }
  }));
}

registerTab('alerts', 'Alerts', render, { title: 'Price, change, RSI and moving-average alerts, with a backtest' });
