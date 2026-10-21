// Screener filters and sorting: presets select exactly the rows their label promises.
import test from 'node:test';
import assert from 'node:assert/strict';
import { PRESETS, activeFilterCount, applyFilters, passes, sortRows } from '../../static/js/screener-policy.js';

const rows = [
  { symbol: 'AAA', pChange: 2.5, fromHigh: -1.5, fromLow: 40, rsi: 72, vsSma200: 12, valueCr: 900, cross: null },
  { symbol: 'BBB', pChange: -3.1, fromHigh: -30, fromLow: 1.2, rsi: 25, vsSma200: -18, valueCr: 300, cross: 'death' },
  { symbol: 'CCC', pChange: 0.4, fromHigh: -2, fromLow: 15, rsi: null, vsSma200: null, valueCr: 1500, cross: 'golden' },
  { symbol: 'DDD', pChange: null, fromHigh: -2.01, fromLow: 9, rsi: 50, vsSma200: 3, valueCr: null, cross: null },
];
const pick = (preset) => sortRows(applyFilters(rows, PRESETS[preset].filters), PRESETS[preset].sort).map(r => r.symbol);

test('near 52W high keeps rows within 2% of the high, inclusive', () => {
  assert.deepEqual(pick('nearHigh'), ['AAA', 'CCC']);
});

test('near 52W low, RSI and SMA presets', () => {
  assert.deepEqual(pick('nearLow'), ['BBB']);
  assert.deepEqual(pick('oversold'), ['BBB']);
  assert.deepEqual(pick('overbought'), ['AAA']);
  assert.deepEqual(pick('above200'), ['AAA', 'DDD']);
});

test('gainers sort high to low, losers low to high', () => {
  assert.deepEqual(pick('gainers'), ['AAA', 'CCC']);
  assert.deepEqual(pick('losers'), ['BBB']);
});

test('cross presets match exactly', () => {
  assert.deepEqual(pick('golden'), ['CCC']);
  assert.deepEqual(pick('death'), ['BBB']);
});

test('a row with no value for a filtered column is left out; unset bounds are ignored', () => {
  assert.ok(!passes(rows[2], { rsi: { min: 0 } }));
  assert.ok(passes(rows[2], { rsi: { min: null, max: undefined } }));
});

test('nulls sort last in both directions', () => {
  assert.deepEqual(sortRows(rows, { key: 'valueCr', dir: -1 }).map(r => r.symbol), ['CCC', 'AAA', 'BBB', 'DDD']);
  assert.deepEqual(sortRows(rows, { key: 'valueCr', dir: 1 }).map(r => r.symbol), ['BBB', 'AAA', 'CCC', 'DDD']);
  assert.deepEqual(sortRows(rows, { key: 'symbol', dir: -1 }).map(r => r.symbol), ['DDD', 'CCC', 'BBB', 'AAA']);
});

test('active filter count ignores empty conditions', () => {
  assert.equal(activeFilterCount({ rsi: { min: 30 }, ltp: {}, cross: 'golden', fromHigh: { min: null } }), 2);
});
