// When the live quote stream counts as healthy, and when the page falls back to polling.
import test from 'node:test';
import assert from 'node:assert/strict';
import { isStreamHealthy, shouldPoll, MAX_SILENCE_MS } from '../../static/js/stream-policy.js';

test('a stream that has never delivered anything is not healthy yet', () => {
  assert.equal(isStreamHealthy({ lastEventAt: null, now: 1_000_000 }), false);
  assert.equal(isStreamHealthy({ lastEventAt: undefined, now: 1_000_000 }), false);
});

test('recent events (quotes or idle-market pings) keep it healthy', () => {
  assert.equal(isStreamHealthy({ lastEventAt: 1_000_000, now: 1_000_000 + 1000 }), true);
  assert.equal(isStreamHealthy({ lastEventAt: 1_000_000, now: 1_000_000 + MAX_SILENCE_MS }), true);     // right at the limit
});

test('silence longer than the heartbeat interval means the connection is dead, not idle', () => {
  assert.equal(isStreamHealthy({ lastEventAt: 1_000_000, now: 1_000_000 + MAX_SILENCE_MS + 1 }), false);
  assert.ok(MAX_SILENCE_MS > 15000, 'must exceed the server heartbeat (15 s) or an idle market would look dead');
});

test('the page polls only while the stream is down', () => {
  assert.equal(shouldPoll({ streamHealthy: true, quotesInFlight: 0 }), false);
  assert.equal(shouldPoll({ streamHealthy: false, quotesInFlight: 0 }), true);
});

test('and never stacks a second poll on one still in flight', () => {
  assert.equal(shouldPoll({ streamHealthy: false, quotesInFlight: 1 }), false);
});
