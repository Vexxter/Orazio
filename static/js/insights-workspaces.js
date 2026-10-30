// Insights › Workspaces: save the current layout under a name, switch between saved ones, or start from a
// preset (Expiry day, Bond desk, Pre-open). Switching writes the layout settings and reloads the page, so every
// panel boots in its saved state. Store: workspace-store.js.
import { esc } from './format.js';
import { openInsights, redraw, registerTab } from './insights.js';
import { PRESETS, apply, list, remove, saveAs } from './workspace-store.js';
import { toast } from './ui.js';

const OPEN_TAB = 'orazio.ws.openTab';   // sessionStorage: which Insights tab to show after the reload

function load(snap, tab = null) {
  apply(localStorage, snap);
  try { if (tab) sessionStorage.setItem(OPEN_TAB, tab); } catch (e) { /* the tab just won't auto-open */ }
  location.reload();
}

async function render(body, ctx) {
  const saved = list(localStorage);
  ctx.pill(`${Object.keys(saved).length} saved`);
  body.innerHTML = `<div class="ins-bar"><input class="ins-input" id="ws-name" placeholder="Name this layout" aria-label="Workspace name" style="width:240px">
      <button type="button" class="btn primary" id="ws-save">Save current layout</button></div>
    <div class="ins-grid2">
      <div class="ins-sec"><h3>Saved</h3>${Object.keys(saved).length ? `<table class="opt-table"><tbody>${Object.keys(saved).map(n => `<tr><td style="text-align:left">${esc(n)}</td><td><button type="button" class="btn" data-load="${esc(n)}">Open</button> <button type="button" class="btn" data-del="${esc(n)}" aria-label="Delete ${esc(n)}">✕</button></td></tr>`).join('')}</tbody></table>` : '<div class="ins-note">Nothing saved yet.</div>'}</div>
      <div class="ins-sec"><h3>Presets</h3><table class="opt-table"><tbody>${Object.keys(PRESETS).map(n => `<tr><td style="text-align:left">${esc(n)}</td><td><button type="button" class="btn" data-preset="${esc(n)}">Open</button></td></tr>`).join('')}</tbody></table>
        <p class="ins-note">Expiry day: NIFTY vs BANKNIFTY, 1m/5m grid, options analytics. Bond desk: India 10Y vs US 10Y, rates. Pre-open: GIFT Nifty vs NIFTY, the brief.</p></div>
    </div>
    <p class="ins-note">A workspace holds layout only (symbol, style, studies, compare, grid, panels). Alerts, drawings, the watchlist and the journal are shared by all of them.</p>`;
  body.querySelector('#ws-save').addEventListener('click', () => {
    const name = body.querySelector('#ws-name').value.trim();
    if (!name) { toast('Give the layout a name', 'error'); return; }
    saveAs(localStorage, name);
    toast(`Saved “${name}”`);
    redraw();
  });
  body.querySelectorAll('[data-load]').forEach(b => b.addEventListener('click', () => load(saved[b.dataset.load])));
  body.querySelectorAll('[data-del]').forEach(b => b.addEventListener('click', () => { remove(localStorage, b.dataset.del); redraw(); }));
  body.querySelectorAll('[data-preset]').forEach(b => b.addEventListener('click', () => { const p = PRESETS[b.dataset.preset]; load(p.snap, p.tab); }));
}

registerTab('workspaces', 'Workspaces', render, { title: 'Save and switch layouts' });

// After a workspace switch reloaded the page: open the tab the preset asked for.
try {
  const tab = sessionStorage.getItem(OPEN_TAB);
  if (tab) { sessionStorage.removeItem(OPEN_TAB); setTimeout(() => openInsights(tab), 800); }
} catch (e) { /* no session storage */ }
