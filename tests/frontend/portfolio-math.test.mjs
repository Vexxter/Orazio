// Portfolio: broker CSVs, holdings maths, beta and risk against hand-checked numbers.
import test from 'node:test';
import assert from 'node:assert/strict';
import { beta, chartSymbol, dailyReturns, effectivePositions, holdingRows, parseHoldings, portfolioReturns, riskStats } from '../../static/js/portfolio-math.js';

test('reads a Zerodha-style export', () => {
  const { holdings, errors } = parseHoldings('Instrument,Qty.,Avg. cost,LTP\n"RELIANCE",10,"2,400.50",2500\nTCS,5,3500,3600\n');
  assert.deepEqual(holdings, [{ symbol: 'RELIANCE', qty: 10, avg: 2400.5 }, { symbol: 'TCS', qty: 5, avg: 3500 }]);
  assert.deepEqual(errors, []);
});

test('finds the header below title rows, and skips totals', () => {
  const { holdings } = parseHoldings('Holdings as on 2 Nov\n\nStock Name,Quantity,Buy Price\nINFY,3,1500\nTotal,3,\n');
  assert.deepEqual(holdings, [{ symbol: 'INFY', qty: 3, avg: 1500 }]);
});

test('reports a row it cannot read instead of guessing, and a missing header', () => {
  const r = parseHoldings('Symbol,Qty\nA,abc\nB,2\n');
  assert.deepEqual(r.holdings, [{ symbol: 'B', qty: 2, avg: null }]);
  assert.match(r.errors[0], /Row 2 \(A\)/);
  assert.match(parseHoldings('a,b\n1,2').errors[0], /header/);
});

test('bare tickers become NSE symbols; qualified ones pass through', () => {
  assert.equal(chartSymbol('RELIANCE'), 'RELIANCE.NS');
  for (const s of ['AAPL.US', '^NSEI', 'BTC-USD', 'INR=X']) assert.equal(chartSymbol(s), s);
});

test('holding rows: value, P&L, day P&L and weights', () => {
  const rows = holdingRows([{ symbol: 'A', qty: 10, avg: 100 }, { symbol: 'B', qty: 10, avg: null }, { symbol: 'C', qty: 1, avg: 5 }],
    new Map([['A', { price: 110, changePercent: 10 }], ['B', { price: 330, changePercent: 0 }]]));
  assert.equal(rows[0].value, 1100);
  assert.equal(rows[0].pnl, 100);
  assert.ok(Math.abs(rows[0].dayPnl - 100) < 1e-9);
  assert.equal(rows[0].weight, 25);
  assert.equal(rows[1].pnl, null);       // no cost given: no P&L rather than a wrong one
  assert.equal(rows[2].value, null);     // no price: shown as missing
});

const D = 86400;
const bars = (closes) => closes.map((c, i) => ({ time: 1_700_000_000 + i * D, close: c }));

test('a series twice as jumpy as the benchmark has a beta of 2', () => {
  const moves = Array.from({ length: 40 }, (_, i) => (i % 2 ? 0.01 : -0.008));
  const b = new Map(moves.map((m, i) => [i, m]));
  const r = new Map(moves.map((m, i) => [i, 2 * m]));
  assert.ok(Math.abs(beta(r, b) - 2) < 1e-9);
  assert.equal(beta(new Map([[1, 0.1]]), b), null);   // too few shared days: no number at all
});

test('portfolio returns weight the holdings and ignore days most of the book has no price for', () => {
  const a = new Map([[1, 0.1], [2, 0.1]]);
  const c = new Map([[2, 0.3]]);
  const out = portfolioReturns([{ weight: 75, returns: a }, { weight: 25, returns: c }]);
  assert.equal(out.has(1), false);    // only 75% priced
  assert.ok(Math.abs(out.get(2) - 0.15) < 1e-12);
});

test('risk stats: drawdown compounds and short histories give nothing', () => {
  const r = new Map(Array.from({ length: 20 }, (_, i) => [i, i === 5 ? -0.5 : i === 6 ? 0.5 : 0]));
  const s = riskStats(r);
  assert.ok(Math.abs(s.maxDrawdownPct + 50) < 1e-9);
  assert.ok(Math.abs(s.totalPct + 25) < 1e-9);
  assert.equal(riskStats(new Map([[1, 0.1]])), null);
  assert.equal(dailyReturns(bars([100, 110])).size, 1);
});

test('effective positions: equal weights count fully, a dominant one barely', () => {
  assert.ok(Math.abs(effectivePositions([25, 25, 25, 25]) - 4) < 1e-9);
  assert.ok(effectivePositions([97, 1, 1, 1]) < 1.1);
});

test('positionSize risks a fixed share of capital to the stop, in whole lots', async () => {
  const { positionSize } = await import('../../static/js/portfolio-math.js');
  const long = positionSize({ capital: 1_000_000, riskPct: 1, entry: 100, stop: 95 });    // ₹10,000 / ₹5 = 2000
  assert.equal(long.side, 'long');
  assert.equal(long.qty, 2000);
  assert.equal(long.risk, 10000);
  assert.deepEqual(long.targets.map(t => t.price), [105, 110, 115]);
  const lots = positionSize({ capital: 1_000_000, riskPct: 1, entry: 100, stop: 95, lot: 750 });
  assert.deepEqual([lots.lots, lots.qty, lots.risk], [2, 1500, 7500]);                   // rounds down: never over-risk
  const short = positionSize({ capital: 500_000, riskPct: 2, entry: 200, stop: 210 });
  assert.equal(short.side, 'short');
  assert.equal(short.qty, 1000);
  assert.deepEqual(short.targets.map(t => t.price), [190, 180, 170]);
  assert.ok(positionSize({ capital: 1e6, riskPct: 1, entry: 100, stop: 100 }).error);
  assert.ok(positionSize({ capital: 0, riskPct: 1, entry: 100, stop: 90 }).error);
});

test('monteCarlo is repeatable for a seed and brackets a known outcome', async () => {
  const { monteCarlo } = await import('../../static/js/portfolio-math.js');
  const flat = monteCarlo(Array(30).fill(0.001), { days: 100, paths: 50 });
  const sure = (1.001 ** 100 - 1) * 100;                         // every path is the same compounding
  assert.ok(Math.abs(flat.p5 - sure) < 1e-9 && Math.abs(flat.p95 - sure) < 1e-9);
  assert.equal(flat.lossProb, 0);
  assert.equal(flat.dd95, 0);
  const mixed = Array.from({ length: 100 }, (_, i) => (i % 2 ? 0.02 : -0.019));
  const a = monteCarlo(mixed, { seed: 7, paths: 300 }), b = monteCarlo(mixed, { seed: 7, paths: 300 });
  assert.deepEqual(a, b);
  assert.ok(a.p5 < a.p50 && a.p50 < a.p95);
  assert.ok(a.dd95 <= a.ddMedian && a.ddMedian < 0);
  assert.equal(monteCarlo([0.01]), null);
});
