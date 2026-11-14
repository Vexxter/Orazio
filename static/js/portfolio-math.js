// Portfolio analytics, pure — unit-tested in Node (tests/frontend/portfolio-math.test.mjs). insights-portfolio.js owns the tab.
// CSV import reads the holdings exports brokers offer: header names vary, so columns are matched by what they mean.

const NAMES = {
  symbol: ['symbol', 'instrument', 'tradingsymbol', 'trading symbol', 'stock', 'stock name', 'scrip', 'scrip name', 'ticker', 'company', 'security'],
  qty: ['qty', 'qty.', 'quantity', 'quantity available', 'shares', 'units', 'net qty', 'holding qty'],
  avg: ['avg', 'avg.', 'avg cost', 'avg. cost', 'average cost', 'average price', 'avg price', 'buy price', 'buy avg', 'purchase price', 'cost price'],
};

function splitLine(line) {
  const out = [];
  let cur = '', quoted = false;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (quoted) {
      if (c === '"' && line[i + 1] === '"') { cur += '"'; i++; } else if (c === '"') quoted = false; else cur += c;
    } else if (c === '"') quoted = true;
    else if (c === ',') { out.push(cur); cur = ''; } else cur += c;
  }
  out.push(cur);
  return out.map(s => s.trim());
}

const num = (s) => { const v = Number(String(s ?? '').replace(/[₹,\s]/g, '')); return Number.isFinite(v) ? v : null; };

// -> { holdings: [{ symbol, qty, avg }], errors: [text] }. A row that can't be read is reported, never guessed at.
export function parseHoldings(text) {
  const lines = String(text || '').replace(/^﻿/, '').split(/\r?\n/).filter(l => l.trim());
  // Some exports open with title rows: the header is the first line naming a symbol and a quantity column.
  const find = (cells, key) => cells.findIndex(c => NAMES[key].includes(c.toLowerCase().replace(/\s+/g, ' ')));
  const at = lines.findIndex(l => { const c = splitLine(l); return find(c, 'symbol') >= 0 && find(c, 'qty') >= 0; });
  if (at < 0) return { holdings: [], errors: ['No header row found. It needs a symbol column and a quantity column.'] };
  const head = splitLine(lines[at]);
  const col = { symbol: find(head, 'symbol'), qty: find(head, 'qty'), avg: find(head, 'avg') };
  const holdings = [], errors = [];
  lines.slice(at + 1).forEach((l, i) => {
    const c = splitLine(l);
    const symbol = (c[col.symbol] || '').toUpperCase();
    if (!symbol || /^(TOTAL|GRAND TOTAL)/.test(symbol)) return;
    const qty = num(c[col.qty]);
    const avg = col.avg >= 0 ? num(c[col.avg]) : null;
    if (qty === null || qty === 0) { errors.push(`Row ${at + i + 2} (${symbol}): no quantity`); return; }
    holdings.push({ symbol, qty, avg });
  });
  return { holdings, errors };
}

// A broker's bare ticker -> the chart symbol. Anything already qualified passes through.
export const chartSymbol = (s) => (/[.^=]/.test(s) || s.includes('-') ? s : `${s}.NS`);

// Daily returns on the dates both series have. Bars are matched by IST date.
const dayOf = (t) => Math.floor((t + 19800) / 86400);
export function dailyReturns(bars) {
  const out = new Map();
  for (let i = 1; i < bars.length; i++) if (bars[i - 1].close) out.set(dayOf(bars[i].time), bars[i].close / bars[i - 1].close - 1);
  return out;
}

const mean = (a) => a.reduce((s, x) => s + x, 0) / a.length;

export function beta(ret, benchmark) {
  const pairs = [...ret].filter(([d]) => benchmark.has(d)).map(([d, r]) => [r, benchmark.get(d)]);
  if (pairs.length < 20) return null;
  const mr = mean(pairs.map(p => p[0])), mb = mean(pairs.map(p => p[1]));
  const cov = mean(pairs.map(([r, b]) => (r - mr) * (b - mb)));
  const vb = mean(pairs.map(([, b]) => (b - mb) ** 2));
  return vb ? cov / vb : null;
}

// Today's weights held fixed over history: this asks how the current book would have behaved, not what the account did.
export function portfolioReturns(series) {
  const days = new Map();
  for (const { weight, returns } of series) {
    for (const [d, r] of returns) {
      const e = days.get(d) || { sum: 0, w: 0 };
      e.sum += weight * r;
      e.w += weight;
      days.set(d, e);
    }
  }
  const total = series.reduce((s, x) => s + x.weight, 0);
  // Only days with at least 90% of the book priced, rescaled to the part that was, so a recent listing doesn't drag early days to zero.
  return new Map([...days].filter(([, e]) => total && e.w / total >= 0.9).sort((a, b) => a[0] - b[0]).map(([d, e]) => [d, e.sum / e.w]));
}

export function riskStats(returns) {
  const r = [...returns.values()];
  if (r.length < 20) return null;
  const m = mean(r);
  const vol = Math.sqrt(r.reduce((s, x) => s + (x - m) ** 2, 0) / (r.length - 1)) * Math.sqrt(252) * 100;
  let eq = 1, peak = 1, dd = 0;
  for (const x of r) { eq *= 1 + x; peak = Math.max(peak, eq); dd = Math.min(dd, eq / peak - 1); }
  const sorted = [...r].sort((a, b) => a - b);
  return { days: r.length, volPct: vol, maxDrawdownPct: dd * 100, totalPct: (eq - 1) * 100, var95Pct: sorted[Math.floor(r.length * 0.05)] * 100 };
}

export function holdingRows(holdings, quotes) {
  const rows = holdings.map(h => {
    const q = quotes.get(h.symbol);
    const price = q?.price ?? null;
    const value = price === null ? null : price * h.qty;
    const cost = h.avg === null ? null : h.avg * h.qty;
    return { ...h, price, value, cost, pnl: value === null || cost === null ? null : value - cost, dayPnl: q && value !== null ? value - value / (1 + q.changePercent / 100) : null };
  });
  const total = rows.reduce((s, r) => s + Math.abs(r.value ?? 0), 0);
  return rows.map(r => ({ ...r, weight: r.value === null || !total ? null : Math.abs(r.value) / total * 100 }));
}

// Herfindahl-based effective number of positions: 10 equal stocks score 10; one dominant stock scores near 1.
export const effectivePositions = (weightsPct) => {
  const s = weightsPct.filter(w => w > 0).reduce((a, w) => a + (w / 100) ** 2, 0);
  return s ? 1 / s : null;
};

// ---------- risk: position sizing and Monte Carlo ----------

// R-based sizing: risk `riskPct` of `capital` between entry and stop, in whole lots. Short when the stop is above entry.
// -> { side, qty, lots, riskPerUnit, risk, value, pctOfCapital, targets: [{ r, price }] } or { error }.
export function positionSize({ capital, riskPct, entry, stop, lot = 1 }) {
  if (!(capital > 0)) return { error: 'Capital must be above zero' };
  if (!(riskPct > 0 && riskPct <= 100)) return { error: 'Risk must be between 0 and 100%' };
  if (!(entry > 0) || !(stop > 0)) return { error: 'Enter an entry and a stop price' };
  if (entry === stop) return { error: 'The stop must differ from the entry' };
  const unitLot = lot >= 1 ? Math.floor(lot) : 1;
  const side = stop < entry ? 'long' : 'short';
  const riskPerUnit = Math.abs(entry - stop);
  const lots = Math.floor(capital * riskPct / 100 / riskPerUnit / unitLot);
  const qty = lots * unitLot;
  const dir = side === 'long' ? 1 : -1;
  return {
    side, qty, lots, riskPerUnit, risk: qty * riskPerUnit, value: qty * entry, pctOfCapital: qty * entry / capital * 100,
    targets: [1, 2, 3].map(r => ({ r, price: entry + dir * r * riskPerUnit })),
  };
}

// Small seeded PRNG (mulberry32) so a Monte Carlo run is repeatable and testable.
export function rng(seed = 1) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const pctile = (sorted, p) => sorted[Math.min(sorted.length - 1, Math.max(0, Math.floor(p * sorted.length)))];

// Bootstrap: resample past daily returns with replacement into `paths` futures of `days` days. Keeps fat tails,
// loses autocorrelation and volatility clustering (ponytail: a block bootstrap fixes that if it ever matters).
// -> { p5, p50, p95 } total return %, { ddMedian, dd95 } max drawdown % (dd95 = 1-in-20 worst), lossProb %.
export function monteCarlo(returns, { days = 252, paths = 2000, seed = 1 } = {}) {
  const r = [...returns].filter(Number.isFinite);
  if (r.length < 20) return null;
  const rand = rng(seed);
  const finals = [], dds = [];
  for (let p = 0; p < paths; p++) {
    let eq = 1, peak = 1, dd = 0;
    for (let d = 0; d < days; d++) {
      eq *= 1 + r[Math.floor(rand() * r.length)];
      if (eq > peak) peak = eq; else dd = Math.min(dd, eq / peak - 1);
    }
    finals.push((eq - 1) * 100);
    dds.push(dd * 100);
  }
  finals.sort((a, b) => a - b);
  dds.sort((a, b) => a - b);
  return { p5: pctile(finals, 0.05), p50: pctile(finals, 0.5), p95: pctile(finals, 0.95), ddMedian: pctile(dds, 0.5), dd95: pctile(dds, 0.05),
           lossProb: finals.filter(x => x < 0).length / paths * 100, days, paths };
}
