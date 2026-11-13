import { $, state } from './state.js';

const PREFS_KEY = 'orazio.prefs.v1';

export function savePrefs() {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify({
      symbol: state.currentSymbol, style: state.styleBeforeLine || state.currentStyle,   // never a forced line
      studies: state.studies, vol: $('vol').checked,
      theme: document.documentElement.dataset.theme || 'dark',
    }));
  } catch (e) { /* storage unavailable (private mode) — preferences just won't persist */ }
}

export function loadPrefs() {
  try { return JSON.parse(localStorage.getItem(PREFS_KEY) || 'null') || {}; } catch (e) { return {}; }
}
