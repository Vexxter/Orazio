// The background chart refresh must never cancel a load the user started (a long range can take 30s+).
import test from 'node:test';
import assert from 'node:assert/strict';
import { shouldAutoRefresh, shouldFoldLiveTick } from '../../static/js/refresh-policy.js';

test('refreshes when the chart is idle and the tab is visible', () => {
  assert.equal(shouldAutoRefresh({ isLoading: false }), true);
  assert.equal(shouldAutoRefresh({ isLoading: false, tabHidden: false }), true);
});

test('never interrupts a load in progress — that load is the one the user asked for', () => {
  assert.equal(shouldAutoRefresh({ isLoading: true }), false);
  assert.equal(shouldAutoRefresh({ isLoading: true, tabHidden: false }), false);
});

test('does not spend requests refreshing a tab nobody is looking at', () => {
  assert.equal(shouldAutoRefresh({ isLoading: false, tabHidden: true }), false);
});

test('live ticks are painted onto the newest candle by default', () => {
  assert.equal(shouldFoldLiveTick({}), true);
  assert.equal(shouldFoldLiveTick({ liveFold: true }), true);
});

test('but not when the server says the candles are a different instrument than the live price', () => {
  // a commodity daily chart is Yahoo's CME future; the live quote is Binance's perpetual, ~0.5-2% away
  assert.equal(shouldFoldLiveTick({ liveFold: false }), false);
});
