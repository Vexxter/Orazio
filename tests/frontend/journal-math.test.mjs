// Trade journal: FIFO matching for longs and shorts, partial closes, and the per-setup stats.
import test from 'node:test';
import assert from 'node:assert/strict';
import { fifo, stats } from '../../static/js/journal-math.js';

const t = (id, date, side, qty, price, setup = 'breakout', symbol = 'NIFTY') => ({ id, date, symbol, side, qty, price, setup });

test('FIFO closes the oldest lot first and leaves the rest open', () => {
  const { closed, open } = fifo([t(1, '2026-01-01', 'buy', 10, 100), t(2, '2026-01-02', 'buy', 10, 110), t(3, '2026-01-03', 'sell', 15, 120)]);
  assert.deepEqual(closed.map(c => [c.qty, c.entry, c.pnl]), [[10, 100, 200], [5, 110, 50]]);
  assert.deepEqual(open, [{ symbol: 'NIFTY', qty: 5, avg: 110 }]);
});

test('selling flat opens a short that a later buy closes', () => {
  const { closed, open } = fifo([t(1, '2026-01-01', 'sell', 5, 100, 'fade'), t(2, '2026-01-02', 'buy', 5, 90)]);
  assert.deepEqual(closed.map(c => [c.side, c.pnl, c.setup]), [['short', 50, 'fade']]);
  assert.deepEqual(open, []);
});

test('stats: win rate, profit factor, setups ranked by P&L, equity curve', () => {
  const { closed } = fifo([
    t(1, '2026-01-01', 'buy', 1, 100, 'a'), t(2, '2026-01-02', 'sell', 1, 130, 'a'),
    t(3, '2026-01-03', 'buy', 1, 100, 'b'), t(4, '2026-01-04', 'sell', 1, 90, 'b'),
  ]);
  const s = stats(closed);
  assert.equal(s.total, 20);
  assert.equal(s.winRate, 50);
  assert.equal(s.profitFactor, 3);
  assert.deepEqual(s.bySetup.map(x => [x.setup, x.pnl]), [['a', 30], ['b', -10]]);
  assert.deepEqual(s.equity.map(e => e.value), [30, 20]);
});
