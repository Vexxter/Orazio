// Indicator math: values checked against hand calculations, plus the no-look-ahead rule for
// higher-timeframe averages.
import test from 'node:test';
import assert from 'node:assert/strict';
import { bandLayout, bollinger, ema, htfAverage, locateBar, macd, rangeFor, resampleWeekly, rsi, sma, tfUsable, vwap, weekKey } from '../../static/js/indicators.js';

const bars = (closes, step = 60, t0 = 1_000_000) => closes.map((c, i) => ({ time: t0 + i * step, open: c, high: c, low: c, close: c, volume: 1 }));
const close = (a, b, eps = 1e-9) => assert.ok(Math.abs(a - b) < eps, `${a} != ${b}`);

test('sma averages the last n closes and starts at bar n', () => {
  const out = sma(bars([1, 2, 3, 4, 5]), 3);
  assert.deepEqual(out.map(p => p.value), [2, 3, 4]);
  assert.equal(out[0].time, 1_000_120);
});

test('ema seeds with the simple average, then weights the newest close by 2/(n+1)', () => {
  const out = ema(bars([1, 2, 3, 4]), 3);
  assert.deepEqual(out.map(p => p.value), [2, 3]);           // seed 2, then 2 + 0.5*(4-2) = 3
});

test('bollinger is sma ± k population std-devs', () => {
  const { mid, upper, lower } = bollinger(bars([2, 4, 4, 4, 5, 5, 7, 9]), 8, 2);
  close(mid[0].value, 5);
  close(upper[0].value, 9);                                  // the textbook set has sd = 2
  close(lower[0].value, 1);
});

test('rsi is 100 on a straight rise, 0 on a straight fall, and uses Wilder smoothing', () => {
  assert.equal(rsi(bars([1, 2, 3, 4, 5]), 3).at(-1).value, 100);
  assert.equal(rsi(bars([5, 4, 3, 2, 1]), 3).at(-1).value, 0);
  // gains 1,0 losses 0,1 over n=2 -> avg 0.5/0.5 -> 50; next +2: gain (0.5+2)/2=1.25, loss 0.25 -> 83.33
  const out = rsi(bars([10, 11, 10, 12]), 2);
  close(out[0].value, 50);
  close(out[1].value, 100 - 100 / (1 + 1.25 / 0.25));
});

test('macd line is fast ema minus slow ema; histogram is line minus signal', () => {
  const b = bars(Array.from({ length: 40 }, (_, i) => 100 + Math.sin(i / 3) * 5));
  const m = macd(b, 3, 6, 4);
  assert.equal(m.macd[0].time, b[5].time);                    // slow ema exists from bar 6
  const last = m.hist.at(-1);
  close(last.value, m.macd.at(-1).value - m.signal.at(-1).value);
});

test('vwap resets each session and skips sessions with no volume', () => {
  const b = [
    { time: 1, high: 10, low: 10, close: 10, volume: 1 }, { time: 2, high: 20, low: 20, close: 20, volume: 3 },
    { time: 3, high: 5, low: 5, close: 5, volume: 2 }, { time: 4, high: 7, low: 7, close: 7, volume: 0 },
  ];
  const out = vwap(b, t => (t <= 2 ? 'a' : t === 3 ? 'b' : 'c'));
  assert.deepEqual(out.map(p => p.value), [10, 17.5, 5]);    // session c has no volume: no point
});

test('weekly resample groups Monday..Sunday (IST) into one bar', () => {
  const mon = Date.UTC(2026, 9, 12, 3, 45) / 1000;           // Mon 12 Oct 2026 09:15 IST
  const days = [0, 1, 4, 7].map((d, i) => ({ time: mon + d * 86400, open: i, high: 10 + i, low: i, close: 100 + i, volume: 1 }));
  const w = resampleWeekly(days);
  assert.equal(w.length, 2);
  assert.deepEqual([w[0].open, w[0].high, w[0].low, w[0].close, w[0].volume], [0, 12, 0, 102, 3]);
  assert.equal(weekKey(days[3].time), weekKey(days[0].time) + 1);
});

test('locateBar finds the containing bar, flags a newer-than-data bar, and -1 before the data', () => {
  const h = bars([1, 2, 3], 3600);
  assert.equal(locateBar(h, h[1].time + 100, 3600), 1);
  assert.equal(locateBar(h, h[2].time + 3600, 3600), 3);
  assert.equal(locateBar(h, h[0].time - 1, 3600), -1);
});

test('htfAverage closes the forming HTF bar at the chart bar\'s price (no look-ahead)', () => {
  const htf = bars([10, 20, 30], 3600);                       // hourly closes; the last hour finished at 30
  const chartBar = { time: htf[2].time + 60, close: 26 };    // one minute into that hour, price 26
  const [p] = htfAverage([chartBar], htf, 2, 'sma', 3600);
  close(p.value, (20 + 26) / 2);                              // NOT (20 + 30) / 2
  const [e] = htfAverage([chartBar], htf, 2, 'ema', 3600);
  close(e.value, 15 + (2 / 3) * (26 - 15));                   // ema after 2 bars = 15, then the forming bar
});

test('htfAverage on the same timeframe equals the plain average', () => {
  const b = bars([1, 2, 3, 4, 5], 3600);
  assert.deepEqual(htfAverage(b, b, 3, 'sma', 3600).map(p => p.value), sma(b, 3).map(p => p.value));
  // EMA needs a finished seed bar before it can fold in a forming one, so it starts one bar later
  assert.deepEqual(htfAverage(b, b, 3, 'ema', 3600).map(p => p.value), ema(b, 3).map(p => p.value).slice(1));
});

test('rangeFor fetches enough history; finer-than-chart timeframes are refused', () => {
  assert.equal(rangeFor('1d', 200), '1Y');
  assert.equal(rangeFor('1d', 15), '1M');
  assert.equal(rangeFor('1d', 20), '3M');            // 20 bars + spare is more than a month of sessions
  assert.equal(rangeFor('1w', 200), '5Y');
  assert.equal(rangeFor('5m', 50), '1W');
  assert.ok(tfUsable('1d', '5m'));
  assert.ok(!tfUsable('5m', '1h'));
  assert.ok(tfUsable('chart', '1d'));
});

test('bandLayout stacks MACD below RSI below volume and shrinks the price area', () => {
  const none = bandLayout({ vol: true, rsi: false, macd: false });
  assert.equal(none.rsi, null);
  close(none.price.bottom, 0.1);
  const both = bandLayout({ vol: true, rsi: true, macd: true });
  assert.ok(both.macd.bottom < both.rsi.bottom);
  close(both.volume.bottom, 0.36);
  close(both.price.bottom, 0.46);
});
