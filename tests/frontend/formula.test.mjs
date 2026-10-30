// Compare-chart formula series: parsing (hyphenated tickers vs a spaced minus) and bar combining.
import test from 'node:test';
import assert from 'node:assert/strict';
import { combineBars, formulaText, parseFormula } from '../../static/js/formula.js';

test('parseFormula reads the four operators and keeps hyphenated tickers whole', () => {
  assert.deepEqual(parseFormula('nifty/banknifty'), { a: 'NIFTY', op: '/', b: 'BANKNIFTY' });
  assert.deepEqual(parseFormula('IN10Y-IN - US10Y'), { a: 'IN10Y-IN', op: '-', b: 'US10Y' });
  assert.deepEqual(parseFormula('GOLD * INR=X'), { a: 'GOLD', op: '*', b: 'INR=X' });
  assert.equal(parseFormula('BTC-USD'), null);          // a plain ticker, not a formula
  assert.equal(parseFormula('RELIANCE.NS'), null);
  assert.equal(formulaText(parseFormula('a+b')), 'A + B');
});

test('combineBars matches on time, or on IST day for daily bars', () => {
  const a = [{ time: 100, open: 10, high: 0, low: 0, close: 12 }, { time: 200, open: 12, high: 0, low: 0, close: 9 }];
  const b = [{ time: 200, open: 4, high: 0, low: 0, close: 3 }];
  assert.deepEqual(combineBars(a, b, '/'), [{ time: 200, open: 3, high: 3, low: 3, close: 3, volume: 0 }]);
  const nseDay = 1_700_000_000 - (1_700_000_000 % 86400) + 13500;     // 09:15 IST
  const usDay = nseDay + 34200;                                       // same IST date, later
  const out = combineBars([{ time: nseDay, open: 5, high: 0, low: 0, close: 6 }], [{ time: usDay, open: 1, high: 0, low: 0, close: 2 }], '-', true);
  assert.deepEqual(out.map(x => [x.open, x.close, x.high, x.low]), [[4, 4, 4, 4]]);
});
