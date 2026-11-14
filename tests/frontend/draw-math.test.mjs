// Drawing-tool geometry: fib levels, the channel's offset line, and moving/editing drawings without
// breaking the formats older versions saved.
import test from 'node:test';
import assert from 'node:assert/strict';
import { FIB_LEVELS, TOOL_CLICKS, anchorsOf, channelOffset, fibPrices, moveDrawing, setAnchor, withAnchors } from '../../static/js/draw-math.js';

const close = (a, b) => assert.ok(Math.abs(a - b) < 1e-9, `${a} != ${b}`);

test('fib: level 1 is the start of the move, 0 the end, 0.5 the midpoint', () => {
  const lv = fibPrices({ t: 0, price: 100 }, { t: 60, price: 200 });
  assert.equal(lv.length, FIB_LEVELS.length);
  close(lv.find(l => l.level === 1).price, 100);
  close(lv.find(l => l.level === 0).price, 200);
  close(lv.find(l => l.level === 0.5).price, 150);
  close(lv.find(l => l.level === 0.618).price, 200 - 100 * 0.618);
});

test('fib works for a down move too', () => {
  const lv = fibPrices({ t: 0, price: 200 }, { t: 60, price: 100 });
  close(lv.find(l => l.level === 0.382).price, 100 + 100 * 0.382);
});

test('channel offset is measured from the A–B line at C\'s time', () => {
  const a = { t: 0, price: 100 }, b = { t: 100, price: 200 };
  close(channelOffset(a, b, { t: 50, price: 140 }, 60), -10);   // line is at 150 there
  close(channelOffset(a, b, { t: 200, price: 310 }, 60), 10);   // extrapolated: line at 300
  close(channelOffset(a, { t: 0, price: 120 }, { t: 0, price: 90 }, 60), -10);   // vertical A–B: offset from A
});

test('old trend and hline shapes round-trip through anchorsOf/withAnchors unchanged', () => {
  const trend = { type: 'trend', a: { t: 1, price: 10 }, b: { t: 2, price: 20 } };
  const hline = { type: 'hline', price: 55 };
  assert.deepEqual(withAnchors(trend, anchorsOf(trend)), trend);
  assert.deepEqual(withAnchors(hline, anchorsOf(hline)), hline);
  const rect = { type: 'rect', pts: [{ t: 1, price: 1 }, { t: 2, price: 2 }] };
  assert.deepEqual(withAnchors(rect, anchorsOf(rect)), rect);
});

test('moving a drawing shifts every anchor by the same time and price', () => {
  const ch = { type: 'channel', pts: [{ t: 0, price: 1 }, { t: 60, price: 2 }, { t: 30, price: 0 }] };
  assert.deepEqual(moveDrawing(ch, 120, 5, 60).pts, [{ t: 120, price: 6 }, { t: 180, price: 7 }, { t: 150, price: 5 }]);
});

test('a horizontal line moves in price only', () => {
  assert.deepEqual(moveDrawing({ type: 'hline', price: 100 }, 999, -3, 60), { type: 'hline', price: 97 });
});

test('anchors in the legacy { time, off } form come out as { t, price } when moved', () => {
  const trend = { type: 'trend', a: { time: 600, off: 0.5, price: 10 }, b: { t: 900, price: 12 } };
  const moved = moveDrawing(trend, 60, 1, 60);
  assert.deepEqual(moved.a, { t: 690, price: 11 });
  assert.deepEqual(moved.b, { t: 960, price: 13 });
});

test('setAnchor replaces one point and keeps text and type', () => {
  const note = { type: 'text', pts: [{ t: 0, price: 1 }], text: 'hi' };
  assert.deepEqual(setAnchor(note, 0, { t: 5, price: 9 }), { type: 'text', pts: [{ t: 5, price: 9 }], text: 'hi' });
  assert.deepEqual(setAnchor({ type: 'hline', price: 1 }, 0, { t: 5, price: 9 }), { type: 'hline', price: 9 });
});

test('every tool declares how many clicks places it', () => {
  for (const tool of ['trend', 'hline', 'fib', 'rect', 'ray', 'channel', 'text']) assert.ok(TOOL_CLICKS[tool] >= 1, tool);
});
