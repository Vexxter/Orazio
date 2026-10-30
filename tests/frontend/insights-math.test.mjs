// Insights research math, checked against hand calculations.
import test from 'node:test';
import assert from 'node:assert/strict';
import { alignByExpiry, breadthSummary, histogram } from '../../static/js/insights-math.js';

test('breadthSummary counts participation', () => {
  const s = breadthSummary([
    { symbol: 'A', pChange: 1, vsSma50: 2, vsSma200: -1, fromHigh: -1, fromLow: 30, rsi: 75, cross: 'golden' },
    { symbol: 'B', pChange: -1, vsSma50: -2, vsSma200: null, fromHigh: -20, fromLow: 1, rsi: 25, cross: null },
  ]);
  assert.equal(s.advances, 1);
  assert.equal(s.above50, 50);
  assert.equal(s.above200, 0);             // B has no 200-day value: not counted in the base
  assert.equal(s.nearHigh, 1);
  assert.equal(s.nearLow, 1);
  assert.deepEqual([s.overbought, s.oversold], [1, 1]);
  assert.deepEqual(s.golden, ['A']);
});

test('histogram buckets by edges, ends open', () => {
  assert.deepEqual(histogram([-10, -1, 0, 0.4, 9, null], [-1, 0, 1]), [1, 1, 2, 1]);
});

test('alignByExpiry lines series up on sessions before expiry', () => {
  const r = alignByExpiry([1, 2, 3, 4], [10, 20], 2);   // prev: T-3..T-0; cur: T-3, T-2 (2 sessions left)
  assert.deepEqual(r.labels, ['T-3', 'T-2', 'T-1', 'T-0']);
  assert.deepEqual(r.prev, [1, 2, 3, 4]);
  assert.deepEqual(r.cur, [10, 20, null, null]);
});

const day = 86400;
const T0 = 1_700_000_000 - (1_700_000_000 % day);   // midnight UTC = 05:30 IST, same IST day
const series = (closes, t0 = T0, step = day) => closes.map((c, i) => ({ time: t0 + i * step, open: c, high: c, low: c, close: c }));

test('pairStats: a series against itself has corr 1, beta 1; against 2x moves beta 0.5', async () => {
  const { dailyReturns, pairStats } = await import('../../static/js/insights-math.js');
  const a = dailyReturns(series([100, 101, 99, 102, 103, 101]));
  assert.ok(Math.abs(pairStats(a, a, 3).corr - 1) < 1e-12);
  const b = new Map([...a].map(([d, r]) => [d, 2 * r]));
  const s = pairStats(a, b, 3);
  assert.ok(Math.abs(s.corr - 1) < 1e-12);
  assert.ok(Math.abs(s.beta - 0.5) < 1e-12);
  assert.equal(pairStats(a, b, 50).corr, null);       // too few shared days
});

test('rrg: steadily outperforming sector sits right of 100', async () => {
  const { rrg, quadrant } = await import('../../static/js/insights-math.js');
  const n = 30;
  const bench = series(Array.from({ length: n }, () => 100), T0, 7 * day);
  const sector = series(Array.from({ length: n }, (_, i) => 100 * 1.01 ** i), T0, 7 * day);
  const p = rrg(sector, bench);
  assert.ok(p.x > 100);
  assert.equal(p.trail.length, 6);
  assert.equal(quadrant(101, 101), 'Leading');
  assert.equal(quadrant(99, 101), 'Improving');
});

test('monthlySeasonality groups month-on-month returns by calendar month', async () => {
  const { monthlySeasonality } = await import('../../static/js/insights-math.js');
  const jan31 = Date.UTC(2024, 0, 31) / 1000, feb29 = Date.UTC(2024, 1, 29) / 1000, mar29 = Date.UTC(2024, 2, 29) / 1000;
  const m = monthlySeasonality([{ time: jan31, close: 100 }, { time: feb29, close: 110 }, { time: mar29, close: 99 }]);
  assert.ok(Math.abs(m[1].avg - 10) < 1e-9);
  assert.ok(Math.abs(m[2].avg + 10) < 1e-9);
  assert.equal(m[0].n, 0);
});

test('eventStudy measures forward moves from the event close; holiday events roll forward', async () => {
  const { dayKey, eventStudy, priceEvents } = await import('../../static/js/insights-math.js');
  const bars = series([100, 98, 99, 100, 102, 104]);
  const ev = priceEvents(bars, 'drop', 1.5);
  assert.deepEqual(ev, [dayKey(bars[1].time)]);
  const r = eventStudy(bars, ev, [1, 3], 2);
  assert.equal(r.events.length, 1);
  assert.ok(Math.abs(r.stats[1].avg - (102 / 98 - 1) * 100) < 1e-9);
  assert.ok(Math.abs(r.path[0]) < 1e-12);
  const gappy = series([100, 101, 102], T0, 2 * day);                  // a session every other day
  const shifted = eventStudy(gappy, [dayKey(gappy[0].time) + 1], [1]);  // event on the missing day in between
  assert.equal(shifted.events[0].index, 1);
});

test('yield symbols use level changes', async () => {
  const { dailyReturns, isYield } = await import('../../static/js/insights-math.js');
  assert.ok(isYield('US10Y') && isYield('IN10Y-IN') && !isYield('NIFTY') && !isYield('INR=X'));
  const [v] = dailyReturns(series([7.0, 7.25]), true).values();
  assert.equal(v, 0.25);
});

test('curveAt takes each tenor\'s last close on or before the day', async () => {
  const { curveAt, dayKey } = await import('../../static/js/insights-math.js');
  const a = series([1, 2, 3]), b = series([10, 20]);
  assert.deepEqual(curveAt([a, b], dayKey(a[2].time)), [3, 20]);
  assert.deepEqual(curveAt([a], dayKey(a[0].time) - 1), [null]);
});

test('ratingSpreads: median spread over the interpolated G-sec, bad prints dropped', async () => {
  const { interp, ratingSpreads } = await import('../../static/js/insights-math.js');
  const g = [{ years: 1, y: 6 }, { years: 5, y: 7 }];
  assert.equal(interp(g, 3), 6.5);
  assert.equal(interp(g, 10), 7);
  const r = ratingSpreads([
    { rating: 'AAA/Stable', ytm: 7.0, years: 3 }, { rating: 'AAA', ytm: 7.2, years: 3 },
    { rating: 'AA/Stable', ytm: 8.5, years: 5 }, { rating: 'AA', ytm: -7, years: 2 }, { rating: null, ytm: 8, years: 2 },
  ], g);
  assert.deepEqual(r.map(x => [x.rating, x.n, Math.round(x.bp)]), [['AAA', 2, 60], ['AA', 1, 150]]);
});

test('placeEvents puts events on the first bar of their IST day and groups them', async () => {
  const { placeEvents } = await import('../../static/js/insights-math.js');
  const day0 = Date.UTC(2026, 9, 26) / 1000 + 13500;                 // Mon 26 Oct 2026, 09:15 IST
  const bars = [0, 1, 2, 3].map(i => ({ time: day0 + i * 86400, close: 1 }));
  const r = placeEvents(bars, [{ date: '2026-10-27', kind: 'a' }, { date: '2026-10-27', kind: 'b' }, { date: '2026-10-01', kind: 'old' }]);
  assert.equal(r.length, 1);
  assert.equal(r[0].time, bars[1].time);
  assert.deepEqual(r[0].events.map(e => e.kind), ['a', 'b']);
  const intraday = [0, 1, 2].map(i => ({ time: day0 + 86400 + i * 300, close: 1 }));   // 27 Oct, 5-min bars
  assert.equal(placeEvents(intraday, [{ date: '2026-10-27', kind: 'x' }])[0].time, intraday[0].time);
});

test('watchStats: 52-week distance, SMA distance and relative volume', async () => {
  const { watchStats } = await import('../../static/js/insights-math.js');
  const b = Array.from({ length: 60 }, (_, i) => ({ time: i * 86400, open: 100, high: 110, low: 90, close: 100, volume: 10 }));
  b[59] = { ...b[59], close: 99, volume: 30 };
  const w = watchStats(b);
  assert.ok(Math.abs(w.fromHigh - (99 / 110 - 1) * 100) < 1e-9);
  assert.ok(Math.abs(w.relVol - 3) < 1e-9);
  assert.ok(w.vsSma50 < 0 && w.vsSma200 === null);
});
