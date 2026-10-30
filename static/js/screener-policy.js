// The screener's filtering and sorting as pure functions, unit-tested in Node
// (tests/frontend/screener-policy.test.mjs). screener.js owns the panel.
//
// filters: { key: { min?, max? } } for numeric columns (both ends inclusive; a row with no value for
// a filtered column is left out), or { key: 'value' } for an exact match (the 50/200 cross).

export const COLUMNS = [
  { key: 'symbol', label: 'Symbol' },
  { key: 'ltp', label: 'LTP', num: true },
  { key: 'pChange', label: 'Chg %', num: true, pct: true },
  { key: 'rsi', label: 'RSI', num: true },
  { key: 'vsSma200', label: 'vs 200D', num: true, pct: true, title: '% above (+) or below (−) the 200-day SMA' },
  { key: 'vsSma50', label: 'vs 50D', num: true, pct: true, title: '% above (+) or below (−) the 50-day SMA' },
  { key: 'fromHigh', label: '52W H', num: true, pct: true, title: '% below the 52-week high' },
  { key: 'fromLow', label: '52W L', num: true, pct: true, title: '% above the 52-week low' },
  { key: 'valueCr', label: 'Value ₹Cr', num: true },
  { key: 'volume', label: 'Volume', num: true },
  { key: 'ch30', label: '30D %', num: true, pct: true },
  { key: 'ch365', label: '1Y %', num: true, pct: true },
];

export const PRESETS = {
  all: { label: 'All stocks · most traded', filters: {}, sort: { key: 'valueCr', dir: -1 } },
  nearHigh: { label: 'Near 52W high (≤ 2%)', filters: { fromHigh: { min: -2 } }, sort: { key: 'fromHigh', dir: -1 } },
  nearLow: { label: 'Near 52W low (≤ 2%)', filters: { fromLow: { max: 2 } }, sort: { key: 'fromLow', dir: 1 } },
  gainers: { label: 'Top gainers', filters: { pChange: { min: 0 } }, sort: { key: 'pChange', dir: -1 } },
  losers: { label: 'Top losers', filters: { pChange: { max: 0 } }, sort: { key: 'pChange', dir: 1 } },
  oversold: { label: 'RSI < 30 (oversold)', filters: { rsi: { max: 30 } }, sort: { key: 'rsi', dir: 1 } },
  overbought: { label: 'RSI > 70 (overbought)', filters: { rsi: { min: 70 } }, sort: { key: 'rsi', dir: -1 } },
  above200: { label: 'Above 200-day SMA', filters: { vsSma200: { min: 0 } }, sort: { key: 'vsSma200', dir: -1 } },
  golden: { label: 'Golden cross (50/200, last 5 days)', filters: { cross: 'golden' }, sort: { key: 'valueCr', dir: -1 } },
  death: { label: 'Death cross (50/200, last 5 days)', filters: { cross: 'death' }, sort: { key: 'valueCr', dir: -1 } },
};

const isNum = (v) => typeof v === 'number' && Number.isFinite(v);

export function passes(row, filters) {
  for (const [key, cond] of Object.entries(filters || {})) {
    const v = row[key];
    if (typeof cond === 'string') { if (v !== cond) return false; continue; }
    const hasMin = isNum(cond?.min), hasMax = isNum(cond?.max);
    if (!hasMin && !hasMax) continue;
    if (!isNum(v)) return false;
    if (hasMin && v < cond.min) return false;
    if (hasMax && v > cond.max) return false;
  }
  return true;
}

export const applyFilters = (rows, filters) => rows.filter(r => passes(r, filters));

// Sort by one column; rows with no value always go last, whichever way it is sorted.
export function sortRows(rows, { key, dir }) {
  return [...rows].sort((a, b) => {
    const x = a[key], y = b[key];
    const xn = x === null || x === undefined, yn = y === null || y === undefined;
    if (xn || yn) return xn === yn ? 0 : xn ? 1 : -1;
    return (typeof x === 'string' ? x.localeCompare(y) : x - y) * dir;
  });
}

// How many filter conditions are actually set (for the "Filters (n)" badge).
export const activeFilterCount = (filters) => Object.values(filters || {})
  .filter(c => typeof c === 'string' || isNum(c?.min) || isNum(c?.max)).length;
