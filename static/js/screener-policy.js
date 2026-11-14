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

// ---------- formula filters: "rsi < 30 and vsSma200 > 0", "valueCr > 100 and (ch30 > 10 or cross = golden)" ----------
// A small parser, never eval: the text comes from the keyboard but is saved and shared, and only named columns,
// numbers and arithmetic can appear. Names match the column keys or labels, in any case.
const FIELD = new Map(COLUMNS.filter(c => c.num).flatMap(c => [[c.key.toLowerCase(), c.key], [c.label.toLowerCase().replace(/[^a-z0-9]/g, ''), c.key]]));
FIELD.set('cross', 'cross');
const WORDS = new Set(['golden', 'death']);
const TOKEN = /\s*(>=|<=|!=|[<>=()+\-*/]|\d+(?:\.\d+)?|[A-Za-z_][A-Za-z0-9_]*)/y;

// -> a predicate (row) => boolean. Throws Error with a readable message. A row missing a named value doesn't match.
export function parseFilter(text) {
  const tokens = [];
  TOKEN.lastIndex = 0;
  const src = String(text ?? '').trimEnd();
  while (TOKEN.lastIndex < src.length) {
    const at = TOKEN.lastIndex, m = TOKEN.exec(src);
    if (!m) throw new Error(`Can't read “${src.slice(at).trim().slice(0, 12)}”`);
    tokens.push(m[1]);
  }
  let i = 0;
  const peek = () => tokens[i]?.toLowerCase();
  const fail = (what) => { throw new Error(`Expected ${what}${tokens[i] ? ` before “${tokens[i]}”` : ' at the end'}`); };

  function atom() {
    const t = tokens[i];
    if (t === undefined) fail('a value');
    if (t === '(') { i++; const v = sum(); if (tokens[i] !== ')') fail('“)”'); i++; return v; }
    if (t === '-') { i++; const v = atom(); return (r) => { const x = v(r); return x === null ? null : -x; }; }
    if (/^\d/.test(t)) { i++; const n = Number(t); return () => n; }
    const low = t.toLowerCase();
    if (WORDS.has(low)) { i++; return () => low; }
    const key = FIELD.get(low);
    if (!key) throw new Error(`Unknown column “${t}”. Try: rsi, pChange, vsSma50, vsSma200, fromHigh, fromLow, valueCr, volume, ch30, ch365, ltp, cross`);
    i++;
    return (r) => r[key] ?? null;
  }
  function binary(next, ops) {
    return () => {
      let left = next();
      while (ops[tokens[i]]) {
        const op = ops[tokens[i++]], l = left, right = next();
        left = (r) => { const a = l(r), b = right(r); if (typeof a !== 'number' || typeof b !== 'number') return null; const v = op(a, b); return Number.isFinite(v) ? v : null; };
      }
      return left;
    };
  }
  const product = binary(atom, { '*': (a, b) => a * b, '/': (a, b) => a / b });
  const sum = binary(product, { '+': (a, b) => a + b, '-': (a, b) => a - b });
  const CMP = { '<': (a, b) => a < b, '<=': (a, b) => a <= b, '>': (a, b) => a > b, '>=': (a, b) => a >= b, '=': (a, b) => a === b, '!=': (a, b) => a !== b };
  function comparison() {
    if (tokens[i] === '(') {
      // A bracket can hold conditions or arithmetic: try conditions, and fall back if it's arithmetic.
      const start = i;
      try {
        i++;
        const v = or();
        if (tokens[i] !== ')') fail('“)”');
        i++;
        if (!CMP[tokens[i]]) return v;
      } catch (e) { /* arithmetic: reparse below */ }
      i = start;
    }
    const left = sum();
    const cmp = CMP[tokens[i]];
    if (!cmp) fail('a comparison like < or >');
    i++;
    const right = sum();
    return (r) => { const a = left(r), b = right(r); return a !== null && b !== null && cmp(a, b); };
  }
  function not() { if (peek() === 'not') { i++; const v = not(); return (r) => !v(r); } return comparison(); }
  function and() { let l = not(); while (peek() === 'and') { i++; const a = l, b = not(); l = (r) => a(r) && b(r); } return l; }
  function or() { let l = and(); while (peek() === 'or') { i++; const a = l, b = and(); l = (r) => a(r) || b(r); } return l; }

  if (!tokens.length) throw new Error('Empty filter');
  const pred = or();
  if (i < tokens.length) throw new Error(`Didn't expect “${tokens[i]}”`);
  return pred;
}
