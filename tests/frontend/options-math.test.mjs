// Payoff at expiry for option strategies, checked against textbook cases.
import test from 'node:test';
import assert from 'node:assert/strict';
import { breakevens, extremes, legPayoff, netPremium, payoff, payoffCurve } from '../../static/js/options-math.js';

const leg = (side, kind, strike, premium, qty = 1) => ({ side, kind, strike, premium, qty });

test('single legs pay intrinsic value minus premium, sign flipped for sells', () => {
  assert.equal(legPayoff(leg('buy', 'CE', 100, 5), 120), 15);
  assert.equal(legPayoff(leg('buy', 'CE', 100, 5), 90), -5);
  assert.equal(legPayoff(leg('sell', 'PE', 100, 4, 50), 90), -300);   // (10 - 4) * 50, written
  assert.equal(legPayoff(leg('buy', 'FUT', 0, 100, 2), 110), 20);
});

test('long straddle: two breakevens, unlimited upside, loss capped at the premium', () => {
  const legs = [leg('buy', 'CE', 100, 6), leg('buy', 'PE', 100, 4)];
  const curve = payoffCurve(legs, 50, 150);
  assert.deepEqual(breakevens(curve), [90, 110]);
  const e = extremes(legs, curve);
  assert.equal(e.maxProfit, Infinity);
  assert.equal(e.maxLoss, -10);
  assert.equal(netPremium(legs), 10);
});

test('bull call spread: capped both ways', () => {
  const legs = [leg('buy', 'CE', 100, 7), leg('sell', 'CE', 110, 3)];
  const e = extremes(legs, payoffCurve(legs, 80, 130));
  assert.equal(e.maxProfit, 6);
  assert.equal(e.maxLoss, -4);
  assert.deepEqual(breakevens(payoffCurve(legs, 80, 130)), [104]);
});

test('short call is unlimited loss; long put profit is bounded by spot reaching zero', () => {
  assert.equal(extremes([leg('sell', 'CE', 100, 5)], payoffCurve([leg('sell', 'CE', 100, 5)], 80, 120)).maxLoss, -Infinity);
  const put = [leg('buy', 'PE', 100, 5)];
  assert.equal(extremes(put, payoffCurve(put, 80, 120)).maxProfit, 95);
});

test('the curve always includes the strikes, so kinks are exact', () => {
  const xs = payoffCurve([leg('buy', 'CE', 103.3, 1)], 100, 110, 4).map(p => p.x);
  assert.ok(xs.includes(103.3));
  assert.equal(payoff([leg('buy', 'CE', 103.3, 1)], 103.3), -1);
});

test('historicalVol annualises the sample std-dev of daily log returns', async () => {
  const { historicalVol } = await import('../../static/js/options-math.js');
  const up = Math.exp(0.01), dn = Math.exp(-0.01);
  const closes = [100]; for (let i = 0; i < 20; i++) closes.push(closes.at(-1) * (i % 2 ? dn : up));
  const hv = historicalVol(closes.map(close => ({ close })), 20);
  // returns ±1% alternating, mean 0: sample sd = 0.01 * sqrt(20/19)
  assert.ok(Math.abs(hv - 0.01 * Math.sqrt(20 / 19) * Math.sqrt(252) * 100) < 1e-9);
  assert.equal(historicalVol([{ close: 1 }, { close: 2 }], 20), null);
});

test('rankOf matches the backend IV rank / percentile definition', async () => {
  const { rankOf } = await import('../../static/js/options-math.js');
  const vals = Array.from({ length: 21 }, (_, i) => 10 + i);
  const r = rankOf(vals, 15);
  assert.equal(r.rank, 25);
  assert.ok(Math.abs(r.percentile - 5 / 21 * 100) < 1e-9);
  assert.equal(rankOf(vals.slice(0, 19), 15), null);
  assert.equal(rankOf(Array(25).fill(12), 12).rank, 50);
});
