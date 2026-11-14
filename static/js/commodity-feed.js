// Source switch for commodities: Spot (the default) or Futures (real-time: Hyperliquid's oracle for oil, gas and
// copper; Binance for gold and silver). A symbol with no spot feed hides "Spot" and uses Futures.
import { loadCandles, pollQuote } from './data.js';
import { effectiveFeed, isCommodity, normalizeFeed } from './feed-policy.js';
import { $, state } from './state.js';

// v2: spot became the default; a "binance" saved under the old key was the old default, not a choice.
const STORE_KEY = 'orazio.commodityFeed.v2';
const seg = $('feed-seg');

try { state.commodityFeed = normalizeFeed(localStorage.getItem(STORE_KEY)); } catch (e) { /* storage blocked: the default stands */ }

export function updateFeedToggle() {
  seg.hidden = !isCommodity(state.currentSymbol, state.CONFIG.commodities);
  const spotList = state.CONFIG.spotCommodities || [];
  const active = effectiveFeed({ symbol: state.currentSymbol, feed: state.commodityFeed, spotCommodities: spotList });
  seg.querySelector('[data-feed="spot"]').hidden = !isCommodity(state.currentSymbol, spotList);
  seg.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.feed === active)));
}

seg.addEventListener('click', (e) => {
  const btn = e.target.closest('button[data-feed]');
  if (!btn || btn.getAttribute('aria-pressed') === 'true') return;
  state.commodityFeed = btn.dataset.feed;
  try { localStorage.setItem(STORE_KEY, state.commodityFeed); } catch (err) { /* a convenience only */ }
  state.lastPolledPrice = null;
  updateFeedToggle();
  loadCandles();
  pollQuote();            // the quote stream reopens by itself (live-quote.js watches the feed)
});
