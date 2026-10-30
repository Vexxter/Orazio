// Workspaces: named snapshots of the page's layout settings (chart symbol and style, studies, compare pane, grid,
// open panels, last Insights tab) — never its data (alerts, drawings, watchlist, journal, search history).
// Pure over a Storage-like object, unit-tested in Node (tests/frontend/workspace-store.test.mjs).

export const LAYOUT_KEYS = ['orazio.prefs.v1', 'orazio.compare.v1', 'orazio.grid.v1', 'orazio.insights.v1', 'orazio.screener.v1',
  'orazio.bonds.v2', 'orazio.news.open', 'orazio.cas.collapsed', 'orazio.events.v1', 'orazio.corr.v1'];
export const STORE_KEY = 'orazio.workspaces.v1';

export function snapshot(storage) {
  const out = {};
  for (const k of LAYOUT_KEYS) { const v = storage.getItem(k); if (v !== null) out[k] = v; }
  return out;
}

// Write a snapshot back. Object values are merged into the stored JSON (presets set only what they
// care about); plain strings replace the value.
export function apply(storage, snap) {
  for (const [k, v] of Object.entries(snap)) {
    if (!LAYOUT_KEYS.includes(k)) continue;
    if (typeof v === 'string') { storage.setItem(k, v); continue; }
    let cur = {};
    try { cur = JSON.parse(storage.getItem(k) || '{}') || {}; } catch (e) { cur = {}; }
    storage.setItem(k, JSON.stringify(typeof cur === 'object' && !Array.isArray(cur) ? { ...cur, ...v } : v));
  }
}

export function list(storage) {
  try { return JSON.parse(storage.getItem(STORE_KEY) || '{}') || {}; } catch (e) { return {}; }
}

export function saveAs(storage, name, snap = snapshot(storage)) {
  storage.setItem(STORE_KEY, JSON.stringify({ ...list(storage), [name]: snap }));
}

export function remove(storage, name) {
  const all = list(storage);
  delete all[name];
  storage.setItem(STORE_KEY, JSON.stringify(all));
}

// Built-in starting points. `tab` opens that Insights tab after the reload.
export const PRESETS = {
  'Expiry day': {
    tab: 'options',
    snap: {
      'orazio.prefs.v1': { symbol: 'NIFTY' },
      'orazio.compare.v1': { open: true, symbol: 'BANKNIFTY' },
      'orazio.grid.v1': { n: 4, panes: [{ symbol: 'NIFTY', interval: '1m' }, { symbol: 'NIFTY', interval: '5m' }, { symbol: 'BANKNIFTY', interval: '1m' }, { symbol: 'BANKNIFTY', interval: '5m' }] },
    },
  },
  'Bond desk': {
    tab: 'rates',
    snap: { 'orazio.prefs.v1': { symbol: 'IN10Y-IN' }, 'orazio.compare.v1': { open: true, symbol: 'US10Y' } },
  },
  'Pre-open': {
    tab: 'brief',
    snap: { 'orazio.prefs.v1': { symbol: 'GIFTNIFTY' }, 'orazio.compare.v1': { open: true, symbol: 'NIFTY' } },
  },
};
