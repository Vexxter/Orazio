// Which price source a commodity request should ask for.
import test from 'node:test';
import assert from 'node:assert/strict';
import { feedQuery, isCommodity, normalizeFeed } from '../../static/js/feed-policy.js';

const commodities = ['GOLD', 'GC=F', 'CRUDE', 'CL=F'];

test('Binance is the default and is not sent (the server defaults to it)', () => {
  assert.equal(feedQuery({ symbol: 'GOLD', commodities, feed: 'binance' }), '');
});

test('Yahoo is requested explicitly, for aliases and raw tickers alike', () => {
  assert.equal(feedQuery({ symbol: 'GOLD', commodities, feed: 'yahoo' }), '&feed=yahoo');
  assert.equal(feedQuery({ symbol: 'cl=f', commodities, feed: 'yahoo' }), '&feed=yahoo');
});

test('the choice never leaks onto other symbols', () => {
  assert.equal(feedQuery({ symbol: 'NIFTY', commodities, feed: 'yahoo' }), '');
  assert.equal(feedQuery({ symbol: '', commodities, feed: 'yahoo' }), '');
});

test('a corrupted stored value falls back to Binance', () => {
  assert.equal(normalizeFeed('yahoo'), 'yahoo');
  assert.equal(normalizeFeed('nonsense'), 'binance');
  assert.equal(normalizeFeed(null), 'binance');
});

test('isCommodity is case-insensitive and safe on empty input', () => {
  assert.equal(isCommodity('gold', commodities), true);
  assert.equal(isCommodity(undefined, commodities), false);
});
