// Which price source a commodity chart/quote should ask for. Pure, so it is unit-tested.
//   spot    — live spot (oil, gas, copper: Dukascopy; gold and silver: Swissquote); the default.
//   futures — real-time futures: Hyperliquid's oracle for oil, gas and copper, Binance for gold and silver.
// (A stored "binance" — the old name of futures — maps to futures; "yahoo", the removed CME option, to spot.)
export const FEEDS = ['spot', 'futures'];
const ALIASES = { binance: 'futures' };

export function normalizeFeed(value) {
  const v = ALIASES[value] || value;
  return FEEDS.includes(v) ? v : 'spot';
}

export function isCommodity(symbol, commodities) {
  return !!symbol && commodities.includes(String(symbol).toUpperCase());
}

// The source this symbol is actually served from: spot falls back to Binance where there is no spot feed.
export function effectiveFeed({ symbol, feed, spotCommodities = [] }) {
  const f = normalizeFeed(feed);
  return f === 'spot' && !isCommodity(symbol, spotCommodities) ? 'futures' : f;
}

// The query-string piece to append to /api/candles, /api/quote and /api/stream/quote. Spot is the server's
// default, so only the other choices are sent, and only for commodities.
export function feedQuery({ symbol, commodities, feed }) {
  const f = normalizeFeed(feed);
  return isCommodity(symbol, commodities) && f !== 'spot' ? `&feed=${f}` : '';
}
