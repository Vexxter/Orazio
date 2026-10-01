// The geometry behind the measure and trendline tools: a click must map to the exact time under the
// cursor, survive a change of bar size, and read out the right move.
import test from 'node:test';
import assert from 'node:assert/strict';
import { anchorSeconds, logicalToSeconds, secondsToLogical, trendReadout } from '../../static/js/anchor-math.js';

const MIN = 60;
// Five 1-minute bars: 09:15..09:19
const bars1m = Array.from({ length: 5 }, (_, i) => ({ time: 1000 * MIN + i * MIN }));

test('a logical position exactly on a bar maps to that bar\'s time', () => {
  assert.equal(logicalToSeconds(bars1m, MIN, 0), bars1m[0].time);
  assert.equal(logicalToSeconds(bars1m, MIN, 3), bars1m[3].time);
});

test('a position between two bars interpolates — this is what makes clicks land where you clicked', () => {
  assert.equal(logicalToSeconds(bars1m, MIN, 1.5), bars1m[1].time + 30);
  assert.equal(logicalToSeconds(bars1m, MIN, 3.25), bars1m[3].time + 15);
});

test('logical -> seconds -> logical is lossless inside the data', () => {
  for (const logical of [0, 0.25, 1.5, 2.999, 3.5, 4]) {
    const t = logicalToSeconds(bars1m, MIN, logical);
    assert.ok(Math.abs(secondsToLogical(bars1m, MIN, t) - logical) < 1e-9, `round trip failed at ${logical}`);
  }
});

test('past either end it extrapolates one step per bar (clicking the empty area right of the last candle)', () => {
  assert.equal(logicalToSeconds(bars1m, MIN, 6), bars1m[4].time + 2 * MIN);
  assert.equal(logicalToSeconds(bars1m, MIN, -2), bars1m[0].time - 2 * MIN);
  assert.equal(secondsToLogical(bars1m, MIN, bars1m[4].time + 3 * MIN), 4 + 3);
  assert.equal(secondsToLogical(bars1m, MIN, bars1m[0].time - MIN), -1);
});

test('uneven bar gaps (overnight) still interpolate between the neighbours', () => {
  const bars = [{ time: 0 }, { time: 60 }, { time: 60 + 17 * 3600 }]; // a long gap after the 2nd bar
  assert.equal(logicalToSeconds(bars, MIN, 1.5), 60 + 8.5 * 3600);
  assert.ok(Math.abs(secondsToLogical(bars, MIN, 60 + 8.5 * 3600) - 1.5) < 1e-9);
});

test('a point drawn on 1-minute bars lands correctly when the chart switches to 5-minute bars', () => {
  const t = logicalToSeconds(bars1m, MIN, 2.4);                 // clicked at ~09:17:24 on the 1m chart
  const bars5m = [{ time: bars1m[0].time }, { time: bars1m[0].time + 5 * MIN }];
  const logical = secondsToLogical(bars5m, 5 * MIN, t);
  assert.ok(logical > 0 && logical < 1, 'it must fall between the first two 5m bars, not vanish');
  assert.ok(Math.abs(logical - (t - bars5m[0].time) / (5 * MIN)) < 1e-9);
});

test('anchorSeconds understands both the current {t} and the old {time, off} point formats', () => {
  assert.equal(anchorSeconds({ t: 1234.5, price: 1 }, MIN), 1234.5);
  assert.equal(anchorSeconds({ time: 1000, off: 0.5, price: 1 }, MIN), 1030);
  assert.equal(anchorSeconds({ time: 1000, price: 1 }, MIN), 1000);
});

test('trendReadout: direction, signed change, percent and span', () => {
  const up = trendReadout({ t: 0, price: 22_000 }, { t: 15 * MIN, price: 22_011 }, MIN);
  assert.equal(up.up, true);
  assert.equal(up.text, '▲ +11.00 (+0.05%) · 15m');
  const down = trendReadout({ t: 0, price: 100 }, { t: 2 * 3600 + 5 * MIN, price: 98.5 }, MIN);
  assert.equal(down.up, false);
  assert.equal(down.text, '▼ -1.50 (-1.50%) · 2h 5m');
});

test('trendReadout is order-independent for the span and never divides by a zero price', () => {
  const a = { t: 600, price: 50 }, b = { t: 0, price: 60 };
  assert.match(trendReadout(a, b, MIN).text, /· 10m$/);
  assert.match(trendReadout({ t: 0, price: 0 }, { t: 60, price: 5 }, MIN).text, /\(\+0\.00%\)/);
});
