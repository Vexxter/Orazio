// Deep search, in the toolbar beside Spot/Futures: describe stocks in plain English ("IT companies that beat earnings with
// promoter buying") and see, while typing, how Orazio reads it. Enter runs it; each clause becomes a chip showing how many
// stocks survive it, and clicking a chip switches that clause off to loosen the screen. `\` focuses the box from anywhere.
// Data: /api/deep/read (instant, no network) and /api/deep (orazio/deep.py; optional model fallback in deep_llm.py).
import { esc } from './format.js';
import { $ } from './state.js';
import { switchSymbol } from './symbol.js';

const EXAMPLES = ['IT companies that beat earnings with promoter buying', 'debt free midcaps with ROCE 20+ near 52 week high',
  'pharma or chemicals, revenue growth above 15%, not small caps', 'top 10 banks by dividend yield'];
const nf = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 });
const nf0 = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 });
const v = (x, suf = '') => (x === null || x === undefined ? '–' : `${nf.format(x)}${suf}`);
const tone = (x) => (x > 0 ? 'up' : x < 0 ? 'down' : '');

const box = $('deep'), input = $('deep-input'), panel = $('deep-panel');
let ran = null, drop = new Set(), active = -1, readTimer = 0, seq = 0, nollm = false;

function open() { panel.hidden = false; input.setAttribute('aria-expanded', 'true'); }
function close() { panel.hidden = true; input.setAttribute('aria-expanded', 'false'); active = -1; }

// ---------- shared rendering (also used by Insights › Find) ----------
export function readBack(d, { counts = null, toggles = false } = {}) {
  const funnel = new Map((counts || []).map(f => [f.index, f]));
  const chips = (d.clauses || []).map((c, i) => {
    const f = funnel.get(i);
    const n = f ? `<span class="deep-n">${nf0.format(f.before)} → ${nf0.format(f.after)}</span>` : '';
    return toggles
      ? `<button type="button" class="deep-clause" data-i="${i}" aria-pressed="${!c.dropped}" title="${c.dropped ? 'Switched off. Click to apply it again' : 'Click to switch this off'}">${esc(c.label)}${n}</button>`
      : `<span class="deep-clause">${esc(c.label)}</span>`;
  }).join('');
  const fixes = (d.repaired || []).map(r => `<span class="deep-fix">Read “${esc(r.was)}” as “${esc(r.now)}”</span>`).join('');
  const unread = (d.unread || []).length ? `<span class="deep-unread">Not understood: ${esc(d.unread.join(', '))}</span>` : '';
  return chips || fixes || unread ? `<div class="deep-read">${chips}${fixes}${unread}</div>` : '';
}

export function resultTable(d) {
  if (!d.rows?.length) return '';
  const cols = d.columns || [];
  const head = cols.map(c => `<th>${esc(c.label)}</th>`).join('');
  const body = d.rows.map(r => `<tr data-symbol="${esc(r.chartSymbol)}" tabindex="0"><td><strong>${esc(r.symbol)}</strong> <span class="deep-name">${esc(r.name || '')}</span></td>
    <td>${v(r.price)}</td><td class="${tone(r.change)}">${v(r.change, '%')}</td><td>${r.marketCapCr == null ? '–' : nf0.format(r.marketCapCr)}</td>${
    cols.map(c => { const x = c.id === 'insiderNetCr' ? r.insiderNetCr : r.values?.[c.id]; return `<td class="${c.pct ? tone(x) : ''}">${v(x, c.pct ? '%' : '')}</td>`; }).join('')}</tr>`).join('');
  return `<div class="deep-table"><table class="opt-table"><thead><tr><th>Company</th><th>Price</th><th>Day</th><th>Mkt cap ₹ Cr</th>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

// Whether a model took part in this answer: always shown, so a model call is never invisible.
export function modelBadge(m) {
  if (!m) return '';
  if (!m.used) return `<p class="deep-model">Rules only, no model call <span>(${esc(m.why)})</span></p>`;
  if (m.error) return `<p class="deep-model warn">Asked ${esc(m.source)} about “${esc((m.words || []).join(', '))}”, but it failed: ${esc(m.error)}. Rules used instead.</p>`;
  const how = m.cached ? 'answer reused from cache, no new call' : `new call, ${m.seconds} s`;
  const extra = [m.unsupported?.length ? `it couldn't express: ${m.unsupported.join(', ')}` : '', m.rejected ? `${m.rejected} invalid clause(s) thrown away` : '']
    .filter(Boolean).map(esc).join('; ');
  return `<p class="deep-model on">Model used: ${esc(m.source)} read “${esc((m.words || []).join(', '))}” <span>(${how})</span>${extra ? `. ${extra}` : ''}</p>`;
}

export function summary(d) {
  if (!d.available) return `${modelBadge(d.model)}<p class="deep-note">${esc(d.reason || 'No answer.')}</p>`;
  const shown = d.count > d.rows.length ? ` The first ${d.rows.length} shown.` : '';
  return `${modelBadge(d.model)}<p class="deep-note"><b>${nf0.format(d.count)}</b> of ${nf0.format(d.universe)} NSE stocks match.${shown}${(d.notes || []).map(n => ` ${esc(n)}`).join('')}</p>`;
}

// ---------- the toolbar box ----------
function renderTyping(d) {
  const sugg = (d.suggest || []).map((s, i) => `<li role="option" id="deep-opt-${i}" class="deep-opt" data-s="${esc(s)}" aria-selected="${i === active}">${esc(s)}</li>`).join('');
  const willAsk = (d.unread || []).length && d.llm && d.llm !== 'off';
  const plan = willAsk
    ? `<div class="deep-bar"><p class="deep-model on">Enter will ask ${esc(d.llm)} about “${esc(d.unread.join(', '))}”</p><button type="button" class="btn" id="deep-nollm">Run without model</button></div>`
    : `<p class="deep-model">Rules only, no model call${(d.unread || []).length ? ' (model fallback is off)' : ''}</p>`;
  panel.innerHTML = `${readBack(d) || '<p class="deep-note">Keep typing: sectors, ratios, growth, earnings, promoter buying, 52-week highs…</p>'}
    ${sugg ? `<ul class="deep-sugg" role="listbox" aria-label="Completions">${sugg}</ul>` : ''}
    ${input.value.trim() ? plan : ''}<p class="deep-foot">Enter runs it${willAsk ? ' · Alt+Enter runs it on the rules alone' : ''}</p>`;
}

function renderEmpty() {
  panel.innerHTML = `<p class="deep-note">Describe the stocks you want. Orazio shows how it reads each part before it runs.</p>
    <ul class="deep-sugg" role="listbox" aria-label="Examples">${EXAMPLES.map((e, i) => `<li role="option" id="deep-opt-${i}" class="deep-opt" data-s="${esc(e)}" aria-selected="false">${esc(e)}</li>`).join('')}</ul>`;
}

function renderRan(d) {
  panel.innerHTML = `${readBack(d, { counts: d.funnel, toggles: true })}${summary(d)}${resultTable(d)}
    <div class="deep-bar"><button type="button" class="btn" id="deep-full">Open in Find</button><span class="deep-foot">Click a row to chart it · click a chip to switch it off</span></div>`;
}

async function readNow() {
  const q = input.value.trim(), my = ++seq;
  ran = null;
  if (!q) { renderEmpty(); return; }
  const d = await fetch(`/api/deep/read?q=${encodeURIComponent(q)}`).then(r => r.json()).catch(() => null);
  if (d && my === seq) renderTyping(d);
}

async function run(keepDrop = false, rulesOnly = null) {
  const q = input.value.trim();
  if (!q) return;
  if (!keepDrop) drop = new Set();
  if (rulesOnly !== null) nollm = rulesOnly;      // chip toggles rerun the same way the search was first run
  const my = ++seq;
  open();
  panel.setAttribute('aria-busy', 'true');
  const prev = panel.querySelector('.deep-read')?.outerHTML || '';
  panel.innerHTML = `${prev}<p class="deep-note">Screening ~1,100 NSE stocks. Quarterly results take a few seconds the first time.</p>`;
  const d = await fetch(`/api/deep?q=${encodeURIComponent(q)}&drop=${[...drop].join(',')}${nollm ? '&nollm=1' : ''}`).then(r => r.json())
    .catch(() => ({ available: false, reason: 'Orazio’s server didn’t answer.' }));
  if (my !== seq) return;
  panel.removeAttribute('aria-busy');
  ran = d;
  renderRan(d);
}

input.addEventListener('focus', () => { open(); if (!ran) readNow(); });
input.addEventListener('input', () => { clearTimeout(readTimer); active = -1; readTimer = setTimeout(readNow, 120); });
input.addEventListener('keydown', (e) => {
  const opts = [...panel.querySelectorAll('.deep-opt')];
  if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && opts.length) {
    e.preventDefault();
    active = (active + (e.key === 'ArrowDown' ? 1 : -1) + opts.length) % opts.length;
    opts.forEach((o, i) => o.setAttribute('aria-selected', String(i === active)));
    input.setAttribute('aria-activedescendant', opts[active].id);
  } else if ((e.key === 'Tab' && active >= 0 && opts[active]) || (e.key === 'Enter' && active >= 0 && opts[active])) {
    e.preventDefault();
    input.value = opts[active].dataset.s;
    active = -1;
    input.removeAttribute('aria-activedescendant');
    if (e.key === 'Enter') run(false, e.altKey); else readNow();
  } else if (e.key === 'Enter') {
    e.preventDefault();
    run(false, e.altKey);                         // Alt+Enter: the rules alone, never a model call
  } else if (e.key === 'Escape') {
    close();
    input.blur();
  }
});

panel.addEventListener('mousedown', (e) => { if (e.target.closest('.deep-opt')) e.preventDefault(); });   // keep focus in the box
panel.addEventListener('click', (e) => {
  const opt = e.target.closest('.deep-opt');
  if (opt) { input.value = opt.dataset.s; run(false, false); return; }
  if (e.target.closest('#deep-nollm')) { run(false, true); return; }
  const chip = e.target.closest('.deep-clause[data-i]');
  if (chip) {
    const i = Number(chip.dataset.i);
    drop.has(i) ? drop.delete(i) : drop.add(i);
    run(true);
    return;
  }
  if (e.target.closest('#deep-full')) {
    close();
    document.dispatchEvent(new CustomEvent('intent:screen', { detail: input.value.trim() }));
    return;
  }
  const row = e.target.closest('tr[data-symbol]');
  if (row) { close(); $('symbol-input').value = row.dataset.symbol; switchSymbol(row.dataset.symbol); }
});
panel.addEventListener('keydown', (e) => {
  const row = e.target.closest('tr[data-symbol]');
  if (row && e.key === 'Enter') { close(); $('symbol-input').value = row.dataset.symbol; switchSymbol(row.dataset.symbol); }
  if (e.key === 'Escape') { close(); input.focus(); }
});
document.addEventListener('mousedown', (e) => { if (!panel.hidden && !box.contains(e.target)) close(); });
document.addEventListener('keydown', (e) => {
  if (e.key !== '\\' || e.ctrlKey || e.metaKey || e.altKey) return;
  if ((e.target instanceof Element && e.target.closest('input, select, textarea, [contenteditable]')) || document.querySelector('.backdrop.open')) return;
  e.preventDefault();
  e.stopImmediatePropagation();                // symbol.js would otherwise send the keystroke to the ticker box
  input.focus();
}, true);
