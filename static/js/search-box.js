// A symbol search box with a results dropdown — used by the main toolbar search and the Compare pane.
// Typing a bare NSE ticker and pressing Enter (ADANIENT, RELIANCE) resolves to its Yahoo listing
// (ADANIENT.NS); a bare "ADANIENT" has no data on Yahoo, so it used to load an empty chart.
import { esc } from './format.js';

// Pure (tests/frontend/search-box.test.mjs): what typed text should load, given /api/search results.
// Order: our own aliases and explicit tickers as typed; then the NSE listing (an Indian app first); then an
// exact match elsewhere (AAPL); then the BSE listing; otherwise the text as typed.
export function pickTyped(text, items, aliases = []) {
  const t = text.trim().toUpperCase();
  if (!t || aliases.includes(t) || /[\^.=]/.test(t) || t.endsWith('-FUT')) return t;
  const syms = new Set((items || []).map(it => String(it.symbol || '').toUpperCase()));
  if (syms.has(`${t}.NS`)) return `${t}.NS`;
  if (syms.has(t)) return t;
  if (syms.has(`${t}.BO`)) return `${t}.BO`;
  return t;
}

async function search(q) {
  const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
  if (!res.ok) throw new Error();
  return res.json();
}

// Wires `input` + `box` (an element with class "results") and calls onChoose(symbol).
export function attachSearch({ input, box, idPrefix, onChoose, aliases = () => [] }) {
  let debounce = null;
  let active = -1;
  let lastItems = [];

  const close = () => {
    box.classList.remove('open');
    input.setAttribute('aria-expanded', 'false');
    input.removeAttribute('aria-activedescendant');
    active = -1;
  };
  const setActive = (i) => {
    const rows = box.querySelectorAll('.result');
    if (!rows.length) return;
    active = (i + rows.length) % rows.length;
    rows.forEach((r, idx) => r.classList.toggle('active', idx === active));
    input.setAttribute('aria-activedescendant', rows[active].id);
    rows[active].scrollIntoView({ block: 'nearest' });
  };
  const choose = (symbol) => {
    clearTimeout(debounce);
    close();
    input.value = symbol;
    input.blur();
    onChoose(symbol);
  };
  // Enter without picking a row: resolve the typed text against the search results.
  const chooseTyped = async () => {
    const text = input.value.trim();
    if (!text) return;
    let items = lastItems;
    if (!items.length || !items.some(it => String(it.symbol).toUpperCase().startsWith(text.toUpperCase()))) {
      try { items = await search(text); } catch (e) { items = []; }
    }
    choose(pickTyped(text, items, aliases()));
  };

  input.setAttribute('role', 'combobox');
  input.setAttribute('aria-autocomplete', 'list');
  input.setAttribute('aria-expanded', 'false');
  input.setAttribute('aria-controls', box.id);
  input.addEventListener('input', () => {
    clearTimeout(debounce);
    const q = input.value.trim();
    lastItems = [];
    if (!q) { close(); return; }
    debounce = setTimeout(async () => {
      try {
        const items = await search(q);
        if (input.value.trim() !== q) return;       // the user kept typing: a newer search is coming
        lastItems = items;
        if (!items.length) { close(); return; }
        box.innerHTML = items.map((it, i) =>
          `<div class="result" role="option" id="${idPrefix}-${i}" data-symbol="${esc(it.symbol)}"><span class="sym">${esc(it.symbol)}</span><span class="nm">${esc(it.name || '')}</span><span class="ex">${esc(it.exchange || '')}</span></div>`
        ).join('');
        box.classList.add('open');
        input.setAttribute('aria-expanded', 'true');
        active = -1;
      } catch (e) { close(); }
    }, 300);
  });
  box.addEventListener('mousedown', (e) => {
    const row = e.target.closest('.result');
    if (!row) return;
    e.preventDefault();
    choose(row.dataset.symbol);
  });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive(active + 1); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(active - 1); }
    else if (e.key === 'Escape') { close(); input.blur(); }
    else if (e.key === 'Enter') {
      // Cancel a pending debounced search, or it can resolve after Enter and reopen stale results.
      clearTimeout(debounce);
      const row = box.querySelector('.result.active');
      if (row) choose(row.dataset.symbol); else chooseTyped();
    }
  });
  input.addEventListener('focus', () => input.select());
  document.addEventListener('click', (e) => { if (!box.parentElement.contains(e.target)) close(); });
}
