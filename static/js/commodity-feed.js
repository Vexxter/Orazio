// Source switch for commodities: Binance perpetual (real-time, the default) or Yahoo's CME futures (~10 min late).
import { loadCandles, pollQuote } from './data.js';
import { isCommodity, normalizeFeed } from './feed-policy.js';
import { $, state } from './state.js';

const STORE_KEY = 'orazio.commodityFeed';
const seg = $('feed-seg');

try { state.commodityFeed = normalizeFeed(localStorage.getItem(STORE_KEY)); } catch (e) { /* storage blocked: the default stands */ }

export function updateFeedToggle() {
  seg.hidden = !isCommodity(state.currentSymbol, state.CONFIG.commodities);
  seg.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.feed === state.commodityFeed)));
}

seg.addEventListener('click', (e) => {
  const btn = e.target.closest('button[data-feed]');
  if (!btn || btn.dataset.feed === state.commodityFeed) return;
  state.commodityFeed = btn.dataset.feed;
  try { localStorage.setItem(STORE_KEY, state.commodityFeed); } catch (err) { /* a convenience only */ }
  state.lastPolledPrice = null;
  updateFeedToggle();
  loadCandles();
  pollQuote();            // the quote stream reopens by itself (live-quote.js watches the feed)
});
