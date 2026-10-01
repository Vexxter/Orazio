// Opens the live quote stream (server-sent events) for the symbol on the chart and paints each pushed
// quote the moment it arrives, instead of waiting for the next 2-second poll. Reconnection is the
// browser's own (EventSource retries by itself); polling in main.js covers any gap — see stream-policy.js.
import { applyQuote, currentFeedQuery } from './data.js';
import { state } from './state.js';
import { isStreamHealthy } from './stream-policy.js';

let source = null;
let openFor = null;
let lastEventAt = null;

// The stream is per symbol AND per feed: switching a commodity between Binance and Yahoo reopens it.
const streamKey = () => state.currentSymbol + currentFeedQuery();

function close() {
  source?.close();
  source = null;
  lastEventAt = null;
}

function open(symbol) {
  close();
  openFor = streamKey();
  if (typeof EventSource === 'undefined') return;     // very old browser: polling carries on alone
  const es = new EventSource(`/api/stream/quote?symbol=${encodeURIComponent(symbol)}${currentFeedQuery(symbol)}`);
  es.addEventListener('quote', (e) => {
    lastEventAt = Date.now();
    if (symbol === state.currentSymbol) applyQuote(JSON.parse(e.data));   // ignore a late event for a symbol we've left
  });
  es.addEventListener('ping', () => { lastEventAt = Date.now(); });
  source = es;
}

export function streamHealthy() {
  return isStreamHealthy({ lastEventAt, now: Date.now() });
}

// Follow the chart: reopen the stream whenever the symbol changes.
setInterval(() => { if (streamKey() !== openFor) open(state.currentSymbol); }, 250);
