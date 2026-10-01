// The chart legend: per-bar volume lookup and the session-stats string next to Open/High/Low/Close.
import test from 'node:test';
import assert from 'node:assert/strict';
import { statsHtml, volumeAt } from '../../static/js/legend-html.js';

const bars = [{ time: 100, volume: 5 }, { time: 160, volume: 0 }, { time: 220, volume: 9 }, { time: 280, volume: 1 }];

test('volumeAt finds any bar, including the first, last and zero-volume ones', () => {
  assert.equal(volumeAt(bars, 100), 5);
  assert.equal(volumeAt(bars, 160), 0);
  assert.equal(volumeAt(bars, 280), 1);
});

test('volumeAt returns undefined for a time with no bar, and for an empty chart', () => {
  assert.equal(volumeAt(bars, 130), undefined);
  assert.equal(volumeAt(bars, 10_000), undefined);
  assert.equal(volumeAt([], 100), undefined);
});

const stats = { symbol: 'NIFTY', available: true, yearHigh: 26373.2, yearLow: 22182.55, change30d: -5.67, volume: 46_880_000, value: 462_597_606_964.82 };

test('statsHtml shows every field, with the 30-day change coloured by direction', () => {
  const html = statsHtml(stats, 'NIFTY');
  for (const needle of ['52W High', '26373.20', '52W Low', '22182.55', '30D', '-5.67%', 'Day Vol', '4.69 Cr', 'Day Value', '₹46,260 Cr']) {
    assert.ok(html.includes(needle), `missing ${needle} in ${html}`);
  }
  assert.match(html, /class="num down">-5\.67%/);
  assert.match(statsHtml({ ...stats, change30d: 2.1 }, 'NIFTY'), /class="num up">\+2\.10%/);
});

test('statsHtml is empty when stats belong to another symbol (a slow response must not leak across charts)', () => {
  assert.equal(statsHtml(stats, 'RELIANCE.NS'), '');
});

test('statsHtml is empty when there are no stats or the market has none for this symbol', () => {
  assert.equal(statsHtml(null, 'NIFTY'), '');
  assert.equal(statsHtml({ symbol: 'SPX', available: false }, 'SPX'), '');
});

test('statsHtml skips fields that are missing instead of printing "undefined"', () => {
  const html = statsHtml({ symbol: 'X', available: true, yearHigh: 10 }, 'X');
  assert.ok(html.includes('52W High'));
  assert.ok(!html.includes('undefined') && !html.includes('null') && !html.includes('52W Low'));
});
