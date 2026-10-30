// Alert rules: crossings fire once, change rules every qualifying day, live price folds into today.
import test from 'node:test';
import assert from 'node:assert/strict';
import { describe, fires, withLive } from '../../static/js/alert-rules.js';

const D = 86400;
const bars = (closes) => closes.map((c, i) => ({ time: 1_700_000_000 + i * D, open: c, high: c, low: c, close: c }));

test('price crossings fire on the first bar past the level only', () => {
  const b = bars([90, 99, 101, 105, 98, 102]);
  assert.deepEqual(fires(b, { type: 'above', value: 100 }), [2, 5]);
  assert.deepEqual(fires(b, { type: 'below', value: 100 }), [4]);
});

test('day-change rules fire on every qualifying day', () => {
  assert.deepEqual(fires(bars([100, 103, 106.1, 100]), { type: 'chgUp', value: 3 }), [1, 2]);
  assert.deepEqual(fires(bars([100, 103, 106.1, 100]), { type: 'chgDown', value: 3 }), [3]);
});

test('SMA cross compares close with its own average', () => {
  const b = bars([10, 10, 10, 9, 12]);
  assert.deepEqual(fires(b, { type: 'smaAbove', value: 3 }), [4]);
});

test('withLive replaces today or appends a new day', () => {
  const b = bars([100, 101]);
  assert.equal(withLive(b, 105, b[1].time + 3600).length, 2);
  assert.equal(withLive(b, 105, b[1].time + 3600)[1].close, 105);
  assert.equal(withLive(b, 105, b[1].time + D).length, 3);
});

test('describe reads naturally', () => {
  assert.equal(describe({ symbol: 'NIFTY', type: 'above', value: 25000 }), 'NIFTY · Price crosses above 25000');
  assert.equal(describe({ symbol: 'NIFTY', type: 'chgDown', value: 2 }), 'NIFTY · Day change ≤ −2%');
});
