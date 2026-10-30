// Insights › Alerts: price, day-change, RSI and moving-average alerts that run in this browser tab (checked every
// 20 s against the live quote) and notify with a toast and a desktop notification. Every rule can be backtested
// first: how often it fired over the symbol's daily history and what the price did 1–20 sessions later.
// Rules: alert-rules.js; backtest stats: insights-math.js eventStudy(). Stored in localStorage.
import { RULES, describe, fires, withLive } from './alert-rules.js';
import { esc } from './format.js';
import { dayKey, eventStudy } from './insights-math.js';
import { historyBars, redraw, registerTab } from './insights.js';
import { state } from './state.js';
import { toast } from './ui.js';

const KEY = 'orazio.alerts.v1';
const CHECK_MS = 20000;
let store = { alerts: [], log: [] };
try { store = { ...store, ...JSON.parse(localStorage.getItem(KEY) || '{}') }; } catch (e) { /* none yet */ }
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(store)); } catch (e) { /* not persisted */ } };
let draft = { type: 'above', value: '' };
let backtest = null;   // { rule, result }
const todayIso = () => new Date(Date.now() + 19800000).toISOString().slice(0, 10);
const f = (v, d = 2) => (v === null || v === undefined ? '–' : v.toFixed(d));
const cls = (v) => (v > 0 ? 'up' : v < 0 ? 'down' : '');

async function quote(symbol) {
  const r = await fetch(`/api/quote?symbol=${encodeURIComponent(symbol)}`);
  return r.ok ? r.json() : null;
}

// ---------- live checking ----------
async function check() {
  const live = store.alerts.filter(a => a.active && a.lastFired !== todayIso());
  for (const a of live) {
    try {
      const [bars, q] = await Promise.all([historyBars(a.symbol, '1Y'), quote(a.symbol)]);
      if (!q || !bars.length) continue;
      // Day change comes from the quote itself (measured against the exchange's official previous close);
      // the other rules need the daily history with today's bar carrying the live price.
      let hit;
      if (a.type === 'chgUp') hit = q.changePercent >= a.value;
      else if (a.type === 'chgDown') hit = q.changePercent <= -Math.abs(a.value);
      else {
        const b = withLive(bars, q.price, q.marketTime || q.time || Date.now() / 1000);
        hit = fires(b, a).includes(b.length - 1);
      }
      if (!hit) continue;
      a.lastFired = todayIso();
      const msg = `${describe(a)} — now ${q.price.toLocaleString('en-IN')}`;
      store.log = [{ at: new Date().toISOString(), msg }, ...store.log].slice(0, 50);
      save();
      toast(`🔔 ${msg}`, 'info');
      if (typeof Notification !== 'undefined' && Notification.permission === 'granted') new Notification('Orazio alert', { body: msg });
    } catch (e) { /* one symbol failing must not stop the rest */ }
  }
}
setInterval(check, CHECK_MS);
setTimeout(check, 3000);

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
  ctx.pill(`${store.alerts.filter(a => a.active).length} active`);
  const perm = typeof Notification === 'undefined' ? 'unsupported' : Notification.permission;
  const rows = store.alerts.map((a, i) => `<tr><td style="text-align:left">${esc(describe(a))}</td><td>${a.lastFired ? esc(a.lastFired) : '–'}</td>
    <td><button type="button" class="btn" data-act="toggle" data-i="${i}">${a.active ? 'Pause' : 'Resume'}</button>
    <button type="button" class="btn" data-act="test" data-i="${i}">Backtest</button>
    <button type="button" class="btn" data-act="del" data-i="${i}" aria-label="Delete alert">✕</button></td></tr>`).join('');
  body.innerHTML = `<div class="ins-bar">
      <label>Symbol <input class="ins-input" id="al-sym" value="${esc(draft.symbol || state.currentSymbol)}" style="width:130px"></label>
      <select class="select" id="al-type" aria-label="Condition">${Object.entries(RULES).map(([k, r]) => `<option value="${k}"${k === draft.type ? ' selected' : ''}>${esc(r.label)}</option>`).join('')}</select>
      <input class="ins-input" id="al-val" type="number" step="any" placeholder="value" value="${esc(draft.value)}" style="width:110px" aria-label="Value">
      <button type="button" class="btn" id="al-test">Backtest</button>
      <button type="button" class="btn primary" id="al-add">Add alert</button>
      ${perm === 'default' ? '<button type="button" class="btn" id="al-perm">Enable desktop notifications</button>' : `<span class="ins-note">Desktop notifications: ${perm}</span>`}
    </div>
    ${backtestHtml()}
    <div class="ins-sec"><h3>Alerts (checked every 20 s while this page is open; each fires at most once a day)</h3>
      ${rows ? `<table class="opt-table"><thead><tr><th style="text-align:left">Rule</th><th>Last fired</th><th></th></tr></thead><tbody>${rows}</tbody></table>` : '<div class="empty-note">No alerts yet.</div>'}</div>
    <div class="ins-sec"><h3>Recently fired</h3>${store.log.length ? store.log.slice(0, 15).map(l => `<div class="ins-note">${esc(l.at.slice(0, 16).replace('T', ' '))} UTC · ${esc(l.msg)}</div>`).join('') : '<div class="ins-note">Nothing yet.</div>'}</div>`;

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
  body.querySelector('#al-add').addEventListener('click', () => {
    const rule = readDraft();
    if (!rule) return;
    store.alerts.push({ ...rule, active: true, lastFired: null });
    save();
    draft = { type: draft.type, value: '' };
    redraw();
  });
  body.querySelector('#al-perm')?.addEventListener('click', () => Notification.requestPermission().then(redraw));
  body.querySelectorAll('[data-act]').forEach(b => b.addEventListener('click', async () => {
    const a = store.alerts[+b.dataset.i];
    if (b.dataset.act === 'toggle') a.active = !a.active;
    else if (b.dataset.act === 'del') store.alerts.splice(+b.dataset.i, 1);
    else backtest = { rule: a, result: await runBacktest(a) };
    save();
    redraw();
  }));
}

registerTab('alerts', 'Alerts', render, { title: 'Price, change, RSI and moving-average alerts, with a backtest' });
