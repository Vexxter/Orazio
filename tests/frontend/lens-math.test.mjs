// Stock Lens lines: verdicts from facts, ordered by what matters now, each pointing at its evidence.
import test from 'node:test';
import assert from 'node:assert/strict';
import { lensLines, trendFacts } from '../../static/js/lens-math.js';

test('results soon with options pricing more than the usual move leads, flagged rich', () => {
  const [l] = lensLines({ symbol: 'TCS.NS', nextResults: { date: '2026-11-17', days: 4 }, typicalMove: 3.2, impliedMove: 4.8, pe: 17, peerPe: 26 });
  assert.equal(l.title, 'Results');
  assert.match(l.text, /Results in 4 days · usually moves ±3\.2% · options price ±4\.8% \(rich/);
  assert.equal(l.cmd, 'TCS.NS ERN');
});

test('valuation against peers reads cheap-with-quality as good news', () => {
  const l = lensLines({ symbol: 'X', pe: 17, peerPe: 26.6, roe: 33, peerRoe: 22 }).find(x => x.title === 'Valuation');
  assert.equal(l.text, 'P/E 17x, 36% below peers · higher ROE');
  assert.equal(l.tone, 'up');
});

test('insider selling is a down line; small amounts are ignored', () => {
  assert.equal(lensLines({ insiderNetCr: -12.4, insiderTrades: 3 })[0].text, 'Promoters/directors net sold ₹12 Cr in 3 trades');
  assert.deepEqual(lensLines({ insiderNetCr: 0.2 }), []);
});

test('index facts: dealer gamma regime and VIX', () => {
  const lines = lensLines({ symbol: 'NIFTY', gex: { netCr: 900, flip: 25100, spot: 25300 }, vixRank: 85 });
  assert.equal(lines[0].title, 'Dealer gamma');
  assert.match(lines[0].text, /Above the 25100 flip: dealers dampen moves/);
  assert.match(lines[1].text, /fear is high/);
});

test('missing facts give no line, not a broken one', () => {
  assert.deepEqual(lensLines({}), []);
  assert.deepEqual(lensLines({ nextResults: { date: 'x', days: 90 } }), []);
});

test('trendFacts: 200-day gap, distance from the 52-week high, one-month return', () => {
  const bars = Array.from({ length: 260 }, (_, i) => ({ close: 100 + i }));   // steady rise: last = 359
  const t = trendFacts(bars);
  assert.equal(Math.round(t.fromHigh * 100), 0);
  assert.ok(t.vs200 > 0 && t.ret1m > 0);
  assert.equal(trendFacts(bars.slice(0, 10)), null);
});
