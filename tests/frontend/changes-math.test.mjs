// "What changed": price surprises scored against the stock's own volatility; events within a week.
import test from 'node:test';
import assert from 'node:assert/strict';
import { eventSurprises, surprises } from '../../static/js/changes-math.js';

const series = (n, f) => Array.from({ length: n }, (_, i) => ({ close: f(i), high: f(i), low: f(i), volume: 1000 }));

test('a big day for a quiet stock is a high-sigma move; an ordinary day is nothing', () => {
  const quiet = series(80, i => 100 * (1 + (i % 2 ? 0.002 : -0.002)));
  assert.deepEqual(surprises(quiet), []);
  const jump = [...quiet.slice(0, -1), { close: 104, high: 104, low: 100, volume: 1000 }];
  const [m] = surprises(jump);
  assert.equal(m.kind, 'move');
  assert.ok(m.score > 5);
  assert.match(m.text, /^\+4\.\d% today, a \d+\.\dσ move for it$/);
});

test('volume spike and a new 52-week high are flagged', () => {
  const up = series(260, i => 100 + i * 0.1);
  up[up.length - 1] = { ...up.at(-1), volume: 4000 };
  const kinds = surprises(up).map(s => s.kind);
  assert.ok(kinds.includes('volume') && kinds.includes('high'));
});

test('too little history: no claims', () => {
  assert.deepEqual(surprises(series(10, () => 100)), []);
});

test('events: results within a week, insider net money, ex-dates soon; nearer scores higher', () => {
  const ev = eventSurprises({
    results: [{ chartSymbol: 'TCS.NS', date: '2026-11-14' }, { chartSymbol: 'INFY.NS', date: '2026-12-20' }],
    insider: [{ chartSymbol: 'X.NS', side: 'buy', valueCr: 8 }, { chartSymbol: 'X.NS', side: 'sell', valueCr: 2 }, { chartSymbol: 'Y.NS', side: 'buy', valueCr: 0.3 }],
    actions: [{ chartSymbol: 'Z.NS', date: '2026-11-15', subject: 'Dividend Rs 5' }],
  }, '2026-11-13');
  assert.deepEqual(ev.map(e => [e.symbol, e.kind]), [['TCS.NS', 'results'], ['X.NS', 'insider'], ['Z.NS', 'action']]);
  assert.match(ev[0].text, /Results tomorrow/);
  assert.match(ev[1].text, /bought ₹6\.0 Cr/);
});
