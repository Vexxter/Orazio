// Which price source a commodity request should ask for: Spot (default) or Futures.
import test from 'node:test';
import assert from 'node:assert/strict';
import { effectiveFeed, feedQuery, isCommodity, normalizeFeed } from '../../static/js/feed-policy.js';

const commodities = ['GOLD', 'GC=F', 'CRUDE', 'CL=F', 'NATGAS', 'NG=F'];
const spotCommodities = ['GOLD', 'GC=F', 'CRUDE', 'CL=F'];

test('spot is the default and is not sent (the server defaults to it)', () => {
  assert.equal(feedQuery({ symbol: 'GOLD', commodities, feed: 'spot' }), '');
  assert.equal(feedQuery({ symbol: 'GOLD', commodities, feed: undefined }), '');
});

test('futures are requested explicitly, for aliases and raw tickers alike', () => {
  assert.equal(feedQuery({ symbol: 'GOLD', commodities, feed: 'futures' }), '&feed=futures');
  assert.equal(feedQuery({ symbol: 'cl=f', commodities, feed: 'futures' }), '&feed=futures');
  assert.equal(feedQuery({ symbol: 'GOLD', commodities, feed: 'binance' }), '&feed=futures');   // old stored name
});

test('the choice never leaks onto other symbols', () => {
  assert.equal(feedQuery({ symbol: 'NIFTY', commodities, feed: 'futures' }), '');
  assert.equal(feedQuery({ symbol: '', commodities, feed: 'futures' }), '');
});

test('a stored value from the removed CME option, or junk, falls back to spot', () => {
  assert.equal(normalizeFeed('yahoo'), 'spot');
  assert.equal(normalizeFeed('nonsense'), 'spot');
  assert.equal(normalizeFeed(null), 'spot');
  assert.equal(feedQuery({ symbol: 'GOLD', commodities, feed: 'yahoo' }), '');
});

test('spot falls back to futures where there is no spot feed (gas, copper)', () => {
  assert.equal(effectiveFeed({ symbol: 'CRUDE', feed: 'spot', spotCommodities }), 'spot');
  assert.equal(effectiveFeed({ symbol: 'NATGAS', feed: 'spot', spotCommodities }), 'futures');
  assert.equal(effectiveFeed({ symbol: 'CRUDE', feed: 'futures', spotCommodities }), 'futures');
});

test('isCommodity is case-insensitive and safe on empty input', () => {
  assert.equal(isCommodity('gold', commodities), true);
  assert.equal(isCommodity(undefined, commodities), false);
});
