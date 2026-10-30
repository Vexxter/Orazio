// Bar replay: picking the start bar from a click time, and never stepping past the loaded bars.
import test from 'node:test';
import assert from 'node:assert/strict';
import { SPEEDS, atEnd, canStartAt, indexAtTime, nextIndex, tickMs } from '../../static/js/replay-policy.js';

const bars = [100, 160, 220, 280].map(time => ({ time }));

test('indexAtTime finds the bar a click lands on, or the one before it', () => {
  assert.equal(indexAtTime(bars, 100), 0);
  assert.equal(indexAtTime(bars, 220), 2);
  assert.equal(indexAtTime(bars, 250), 2);
  assert.equal(indexAtTime(bars, 999), 3);
  assert.equal(indexAtTime(bars, 50), -1);
  assert.equal(indexAtTime([], 50), -1);
});

test('a replay can start anywhere except the last bar (nothing left to reveal)', () => {
  assert.ok(canStartAt(0, 4));
  assert.ok(canStartAt(2, 4));
  assert.ok(!canStartAt(3, 4));
  assert.ok(!canStartAt(-1, 4));
});

test('stepping stops at the last loaded bar', () => {
  assert.equal(nextIndex(1, 4), 2);
  assert.equal(nextIndex(3, 4), 3);
  assert.ok(atEnd(3, 4));
  assert.ok(!atEnd(2, 4));
});

test('speeds are bars per second', () => {
  assert.deepEqual(SPEEDS, [1, 3, 10]);
  assert.equal(tickMs(10), 100);
});
