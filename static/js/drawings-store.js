// Per-symbol persistence for trendlines and horizontal lines. Takes any storage with
// getItem/setItem, so it works with localStorage in the browser and a plain object in Node tests
// (tests/frontend/drawings-store.test.mjs). Storage can be missing or throw (private windows,
// blocked site data) — every path degrades to "no saved drawings" instead of an error.
const KEY = 'orazio.drawings.v1';

export function createDrawingStore(storage, key = KEY) {
  function readAll() {
    try {
      const all = JSON.parse(storage.getItem(key) || '{}');
      return all && typeof all === 'object' && !Array.isArray(all) ? all : {};
    } catch (e) { return {}; }
  }
  return {
    get(symbol) {
      const list = readAll()[symbol];
      return Array.isArray(list) ? list : [];
    },
    set(symbol, drawings) {
      try {
        const all = readAll();
        all[symbol] = drawings;
        storage.setItem(key, JSON.stringify(all));
      } catch (e) { /* storage unavailable: drawings simply won't persist */ }
    },
  };
}

export const browserStorage = {
  getItem(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
  setItem(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* not persisted */ }  },
};
