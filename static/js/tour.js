// Learning by doing. Three pieces, none of them nagging:
//  * The 60-second tour (:TOUR, and the welcome screen): a spotlight walks through the four ideas that make Orazio
//    click — one box for everything, the Lens, Insights grouped by job, commands — doing each thing for real.
//  * The cheat sheet (? anywhere, or :KEYS): one page, built from the live command and group lists so it never drifts.
//  * Quiet hints: the first time a view is opened by mouse, a toast names its command. Once per view, ever.
import { FUNCTIONS } from './command-parse.js';
import { esc } from './format.js';
import { GROUPS, commandFor, openInsights } from './insights.js';
import { switchSymbol } from './symbol.js';
import { $ } from './state.js';
import { toast } from './ui.js';

const HINTS_KEY = 'orazio.hints.v1';
const TOUR_SYMBOL = 'TCS.NS';

// ---------- spotlight ----------
let layer = null;
function spotlight(target, html, actions) {
  layer ||= Object.assign(document.createElement('div'), { id: 'tour-layer', innerHTML: '<div class="tour-hole"></div><div class="tour-card" role="dialog" aria-live="polite"></div>' });
  if (!layer.isConnected) document.body.appendChild(layer);
  const hole = layer.querySelector('.tour-hole'), card = layer.querySelector('.tour-card');
  const el = typeof target === 'string' ? document.querySelector(target) : target;
  const r = el?.getBoundingClientRect() || { left: innerWidth / 2, top: innerHeight / 2, width: 0, height: 0 };
  Object.assign(hole.style, { left: `${r.left - 8}px`, top: `${r.top - 8}px`, width: `${r.width + 16}px`, height: `${r.height + 16}px` });
  card.innerHTML = `${html}<div class="tour-actions">${actions.map(([label, , primary], i) => `<button type="button" class="btn${primary ? ' primary' : ''}" data-i="${i}">${esc(label)}</button>`).join('')}</div>`;
  // Card beside the target: below it if there's room, else above; clamped to the viewport.
  const below = r.top + r.height + 240 < innerHeight;
  const left = Math.min(Math.max(16, r.left), innerWidth - 400);
  Object.assign(card.style, { left: `${left}px`, top: below ? `${r.top + r.height + 18}px` : 'auto', bottom: below ? 'auto' : `${innerHeight - r.top + 18}px` });
  card.querySelectorAll('[data-i]').forEach(b => b.addEventListener('click', () => actions[+b.dataset.i][1]()));
  card.querySelector('.btn.primary')?.focus();
}
const endTour = () => { layer?.remove(); };
const wait = (ms) => new Promise(r => setTimeout(r, ms));

const STEPS = [
  () => spotlight('#symbol-input', `<b>One box for everything.</b><p>Type a ticker, a view on it (<code>tcs peers</code>, <code>nifty gex</code>) or a question (<code>stocks with ROCE above 25</code>). Every suggestion shows its command, so you learn the shortcuts by using it.</p>`,
    [['Show me', async () => { $('symbol-input').value = TOUR_SYMBOL; switchSymbol(TOUR_SYMBOL); await wait(900); next(); }, true], ['Skip tour', endTour]]),
  () => spotlight('#lens', `<b>The Lens reads the stock for you.</b><p>Results coming and whether options price more than the usual move, insider money, valuation against peers, volatility, trend. Click any line for the evidence.</p>`,
    [['Next', next, true], ['Skip tour', endTour]]),
  () => spotlight('#insights-btn', `<b>Insights, grouped by job.</b><p>Today, Find, Stock, Derivatives, Rates &amp; macro, My book. The badge counts today's surprises on your watchlist.</p>`,
    [['Open it', async () => { openInsights('changes'); await wait(500); next(); }, true], ['Skip tour', endTour]]),
  () => spotlight('#insights-tabs', `<b>Every view has a command.</b><p>Hover a tab to see it, then type <code>:</code> and the code from anywhere: <code>:FA</code> fundamentals, <code>:FIND</code> screens, <code>:OPT</code> options. Press <kbd>?</kbd> for the one-page cheat sheet.</p>`,
    [['Finish', () => { endTour(); toast('You’re set. Press ? any time for every command.'); }, true]]),
];
let step = 0;
function next() { step += 1; if (STEPS[step]) STEPS[step](); else endTour(); }
export function startTour() { step = 0; STEPS[0](); }

// ---------- cheat sheet ----------
export function openCheatSheet() {
  if (document.querySelector('#cheat-modal')) return;   // already open (it's built on demand, not in index.html)
  const viewRows = GROUPS.map(([, label, what, ids]) => {
    const rows = ids.map(id => [id, commandFor(id)]).filter(([, c]) => c).map(([, c]) => `<li><kbd>:${esc(c)}</kbd><span>${esc(FUNCTIONS[c][1])}</span></li>`).join('');
    return rows ? `<section><h4>${esc(label)} <span>${esc(what)}</span></h4><ul>${rows}</ul></section>` : '';
  }).join('');
  const panels = ['GP', 'CHAIN', 'SCRN', 'BONDS', 'MOV', 'NEWS', 'GRID', 'CAS', 'TOUR'].filter(k => FUNCTIONS[k]).map(k => `<li><kbd>:${k}</kbd><span>${esc(FUNCTIONS[k][1])}</span></li>`).join('');
  const el = document.createElement('div');
  el.className = 'backdrop open';
  el.id = 'cheat-modal';
  el.innerHTML = `<div class="modal cheat" role="dialog" aria-modal="true" aria-labelledby="cheat-title">
    <div class="modal-head"><h2 id="cheat-title">Orazio on one page</h2><button type="button" class="btn icon" id="cheat-close" aria-label="Close">✕</button></div>
    <div class="modal-body">
      <div class="cheat-top">
        <section><h4>Move</h4><ul><li><kbd>/</kbd><span>Search (or just start typing)</span></li><li><kbd>:</kbd><span>Command line</span></li><li><kbd>?</kbd><span>This page</span></li><li><kbd>Esc</kbd><span>Close anything</span></li></ul></section>
        <section class="ask"><h4>Ask the box</h4><ul><li><code>tcs peers</code><span>a view on a stock</span></li><li><code>nifty gex</code><span>dealer gamma</span></li><li><code>tcs vs infy</code><span>compare</span></li><li><code>stocks with ROCE above 25</code><span>a screen</span></li><li><code>RELIANCE 5M</code><span>a timeframe</span></li></ul></section>
        <section><h4>Chart and panels</h4><ul>${panels}</ul></section>
      </div>
      <div class="cheat-grid">${viewRows}</div>
    </div></div>`;
  document.body.appendChild(el);
  const close = () => el.remove();
  el.querySelector('#cheat-close').addEventListener('click', close);
  el.addEventListener('click', (e) => { if (e.target === el) close(); });
  el.addEventListener('keydown', (e) => { if (e.key === 'Escape' || e.key === '?') { e.stopPropagation(); close(); } });
  el.querySelector('#cheat-close').focus();
}

document.addEventListener('keydown', (e) => {
  if (e.key !== '?' || (e.target instanceof Element && e.target.closest('input, select, textarea, [contenteditable]'))) return;
  e.preventDefault();
  openCheatSheet();
});
document.addEventListener('tour', startTour);
document.addEventListener('cheatsheet', openCheatSheet);

// ---------- quiet hints ----------
let hinted = new Set();
try { hinted = new Set(JSON.parse(localStorage.getItem(HINTS_KEY) || '[]')); } catch (e) { /* none yet */ }
document.addEventListener('insights:clicked', (e) => {
  const id = e.detail.id, c = commandFor(id);
  if (!c || hinted.has(id)) return;
  hinted.add(id);
  try { localStorage.setItem(HINTS_KEY, JSON.stringify([...hinted])); } catch (err) { /* hint again next time */ }
  toast(`Next time: type :${c} from anywhere.`);
});
