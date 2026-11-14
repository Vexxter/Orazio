// Formula series for the compare chart: "NIFTY / BANKNIFTY", "IN10Y-IN - US10Y", "GOLD * INR=X". Pure —
// unit-tested in Node (tests/frontend/formula.test.mjs). Minus must have spaces around it, since tickers
// contain hyphens (IN10Y-IN, BTC-USD).

const OPS = { '/': (a, b) => a / b, '*': (a, b) => a * b, '+': (a, b) => a + b, '-': (a, b) => a - b };
const TICKER = '[A-Za-z0-9^.=_&-]+';
const RE = new RegExp(`^\\s*(${TICKER}?)\\s*(?:([/*+])|\\s-\\s)\\s*(${TICKER})\\s*$`);

export function parseFormula(text) {
  const m = RE.exec(text || '');
  if (!m || !m[1] || !m[3]) return null;
  return { a: m[1].toUpperCase(), op: m[2] || '-', b: m[3].toUpperCase() };
}

export const formulaText = (f) => `${f.a} ${f.op} ${f.b}`;

// One bar per time both series have (daily bars from different markets are matched on IST date). Open and close
// combine directly; high/low are only the larger/smaller of those two, since the true intrabar extremes of a
// ratio can't be known from two separate OHLC bars.
export function combineBars(aBars, bBars, op, daily = false) {
  const fn = OPS[op];
  const key = (t) => (daily ? Math.floor((t + 19800) / 86400) : t);
  const bBy = new Map(bBars.map(b => [key(b.time), b]));
  const out = [];
  for (const a of aBars) {
    const b = bBy.get(key(a.time));
    if (!b) continue;
    const open = fn(a.open, b.open), close = fn(a.close, b.close);
    if (!Number.isFinite(open) || !Number.isFinite(close)) continue;
    out.push({ time: a.time, open, high: Math.max(open, close), low: Math.min(open, close), close, volume: 0 });
  }
  return out;
}
