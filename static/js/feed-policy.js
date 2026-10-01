// Which price source a commodity chart/quote should ask for. Pure, so it is unit-tested.
export const FEEDS = ['binance', 'yahoo'];

export function normalizeFeed(value) {
  return FEEDS.includes(value) ? value : 'binance';
}

export function isCommodity(symbol, commodities) {
  return !!symbol && commodities.includes(String(symbol).toUpperCase());
}

// The query-string piece to append to /api/candles, /api/quote and /api/stream/quote. Binance is the
// server's default, so only the non-default choice is sent, and only for commodities.
export function feedQuery({ symbol, commodities, feed }) {
  return isCommodity(symbol, commodities) && feed === 'yahoo' ? '&feed=yahoo' : '';
}
