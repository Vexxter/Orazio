// Symbol search box + the central switchSymbol() used by search, the rail, and the futures toggle.
import { loadCandles, pollQuote } from './data.js';
import { savePrefs } from './prefs.js';
import { highlightRail } from './rail.js';
import { $, esc, state } from './state.js';

const symbolInput = $('symbol-input');
const resultsBox = $('symbol-results');
let searchDebounce = null;
let searchActive = -1;

function closeResults() {
  resultsBox.classList.remove('open');
  symbolInput.setAttribute('aria-expanded', 'false');
  symbolInput.removeAttribute('aria-activedescendant');
  searchActive = -1;
}
function setActiveResult(i) {
  const rows = resultsBox.querySelectorAll('.result');
  if (!rows.length) return;
  searchActive = (i + rows.length) % rows.length;
  rows.forEach((r, idx) => r.classList.toggle('active', idx === searchActive));
  symbolInput.setAttribute('aria-activedescendant', rows[searchActive].id);
  rows[searchActive].scrollIntoView({ block: 'nearest' });
}
function chooseSymbol(symbol) {
  clearTimeout(searchDebounce);
  closeResults();
  symbolInput.value = symbol;
  symbolInput.blur();
  switchSymbol(symbol);
}

symbolInput.addEventListener('input', () => {
  clearTimeout(searchDebounce);
  const q = symbolInput.value.trim();
  if (q.length < 1) { closeResults(); return; }
  searchDebounce = setTimeout(async () => {
    try {
      const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
      if (!res.ok) throw new Error();
      const items = await res.json();
      if (!items.length) { closeResults(); return; }
      resultsBox.innerHTML = items.map((it, i) =>
        `<div class="result" role="option" id="sr-${i}" data-symbol="${esc(it.symbol)}"><span class="sym">${esc(it.symbol)}</span><span class="nm">${esc(it.name || '')}</span><span class="ex">${esc(it.exchange || '')}</span></div>`
      ).join('');
      resultsBox.classList.add('open');
      symbolInput.setAttribute('aria-expanded', 'true');
      searchActive = -1;
    } catch (e) { closeResults(); }
  }, 300);
});

resultsBox.addEventListener('mousedown', (e) => {
  const row = e.target.closest('.result');
  if (!row) return;
  e.preventDefault();
  chooseSymbol(row.dataset.symbol);
});

symbolInput.addEventListener('keydown', (e) => {
  if (e.key === 'ArrowDown') { e.preventDefault(); setActiveResult(searchActive + 1); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); setActiveResult(searchActive - 1); }
  else if (e.key === 'Escape') { closeResults(); symbolInput.blur(); }
  else if (e.key === 'Enter') {
    // Cancel any pending debounced search fetch — otherwise it can resolve after
    // Enter closes the dropdown and reopen it with stale results.
    clearTimeout(searchDebounce);
    const active = resultsBox.querySelector('.result.active');
    chooseSymbol(active ? active.dataset.symbol : symbolInput.value.trim());
  }
});
symbolInput.addEventListener('focus', () => symbolInput.select());
document.addEventListener('click', (e) => { if (!e.target.closest('.search')) closeResults(); });

// "/" jumps to search from anywhere (unless you're already typing in a field).
document.addEventListener('keydown', (e) => {
  if (e.key === '/' && !e.target.closest('input, select, textarea')) { e.preventDefault(); symbolInput.focus(); }
});

export function switchSymbol(symbol) {
  if (!symbol || symbol.toUpperCase() === state.currentSymbol) return;
  state.currentSymbol = symbol.toUpperCase();
  state.lastPolledPrice = null;
  state.tickChangedAt = 0;
  state.lineAreaUp = null;
  savePrefs();
  loadCandles();
  pollQuote();
  highlightRail();
}
