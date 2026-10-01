// When the once-a-minute background refresh of the chart may run. Pure, so it is unit-tested in Node
// (tests/frontend/refresh-policy.test.mjs).
//
// loadCandles() aborts whatever load is already in flight. Left unchecked, the timer would cancel a
// load YOU started — a long range such as "All" can take 30+ seconds the first time — and quietly
// reload the previous view instead. So the refresh only runs when nothing else is loading.
export function shouldAutoRefresh({ isLoading, tabHidden = false }) {
  return !isLoading && !tabHidden;
}

// Should a live quote tick be painted onto the newest candle? Not when the candles and the quote
// are different instruments: the server sets liveFold=false for commodity charts that are still
// on Yahoo's CME futures while the live price is Binance's perpetual (they sit apart by 0.5-2%).
export function shouldFoldLiveTick({ liveFold }) {
  return liveFold !== false;
}
