import { applyLineAreaColor, areaSeries, barSeries, candleSeries, chart, computeDayBoundaries, fitWithPadding, lineSeries, renderIndicators, syncStyleData, updateLegend, updateWatermark, volumeSeries } from './chart.js';
import { $, COLORS, INTERVAL_LABEL, INTERVAL_SECONDS, displayName, state, unsuppressSoon } from './state.js';
import { hideChartState, setConn, setIntervalUI, setLoading, setRangeUI, showChartState, showFreshness, toast } from './ui.js';
import { updateFuturesToggle } from './futures.js';

// ---------- data loading ----------
// Aborting a superseded request (not just discarding its late response) matters
// because the Flask dev server serializes requests and the browser caps concurrent
// connections per host — a queue of stale requests can otherwise delay the one
// response you actually want by many seconds.

export async function loadCandles(opts = {}) {
  state.suppressRangeEvents = true;
  const myGeneration = ++state.loadGeneration;
  state.candlesAbortController?.abort();
  state.candlesAbortController = new AbortController();
  const requestedInterval = opts.interval || state.selectedInterval;
  const requestedRange = opts.range || state.currentRange;
  const preserve = opts.preserveView ? chart.timeScale().getVisibleRange() : null;

  // A yfinance round-trip takes a second or two — a progress bar keeps an impatient
  // click from reading as "unresponsive".
  setLoading(true);
  $('note').textContent = '';

  let payload;
  try {
    const res = await fetch(`/api/candles?symbol=${encodeURIComponent(state.currentSymbol)}&interval=${requestedInterval}&range=${requestedRange}`, { signal: state.candlesAbortController.signal });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    payload = await res.json();
  } catch (e) {
    if (e.name === 'AbortError') return; // superseded — a newer loadCandles() is handling things
    if (myGeneration === state.loadGeneration) {
      setLoading(false);
      unsuppressSoon();
      // Keep whatever is already on screen; only take over the chart if there is nothing.
      if (!state.latestCandles.length) showChartState(`Couldn't load ${state.currentSymbol}`, 'The data source didn\'t respond. Check your connection and try again.');
      else toast(`Couldn't refresh ${state.currentSymbol} — showing the last data`, 'error');
    }
    return;
  }
  if (myGeneration !== state.loadGeneration) return; // belt-and-suspenders vs. the abort above

  // Keep locally-built live bars that are newer than anything Yahoo has published yet
  // (same symbol + interval only); Yahoo's bars replace everything up to its last one.
  const prevCandles = state.latestCandles;
  const sameSeries = state.resolvedSymbol === payload.symbol && state.currentInterval === payload.interval;
  state.latestCandles = payload.candles;
  if (sameSeries && prevCandles.length && state.latestCandles.length) {
    const serverLast = state.latestCandles[state.latestCandles.length - 1].time;
    const liveTail = prevCandles.filter(c => c.time > serverLast);
    if (liveTail.length) state.latestCandles = [...state.latestCandles, ...liveTail];
    // A periodic refresh of the SAME range must not discard older days the user has
    // already scrolled back into (that made the chart flicker/re-fetch every minute).
    if (requestedRange === state.currentRange) {
      const serverFirst = state.latestCandles[0].time;
      const olderHistory = prevCandles.filter(c => c.time < serverFirst);
      if (olderHistory.length) state.latestCandles = [...olderHistory, ...state.latestCandles];
    }
  }
  state.currentInterval = payload.interval;
  state.currentRange = requestedRange;
  state.resolvedSymbol = payload.symbol;
  state.historyOldestTime = state.latestCandles.length ? state.latestCandles[0].time : null;
  state.historyExhausted = false;

  setRangeUI(state.currentRange);
  setIntervalUI(payload.interval);
  $('note').textContent = payload.interval !== requestedInterval
    ? `${INTERVAL_LABEL[requestedInterval] || requestedInterval} bars aren't available for ${requestedRange} — showing ${INTERVAL_LABEL[payload.interval] || payload.interval}`
    : '';

  syncStyleData();
  renderIndicators();
  computeDayBoundaries();
  updateFuturesToggle();
  updateWatermark();
  updateLegend(null);
  if (state.latestCandles.length) {
    hideChartState();
    if (preserve) chart.timeScale().setVisibleRange(preserve);
    else fitWithPadding();
  } else {
    showChartState(`No data for ${state.currentSymbol}`, 'This symbol returned no bars for the selected range. Try a different range or symbol.');
  }
  setLoading(false);
  unsuppressSoon();
}

export async function loadMoreHistory() {
  if (state.loadingHistory || state.historyExhausted || state.currentInterval === '1d' || !state.resolvedSymbol || state.historyOldestTime == null) return;
  state.loadingHistory = true;
  state.suppressRangeEvents = true;
  const myGeneration = state.loadGeneration;
  try {
    const res = await fetch(`/api/candles/history?symbol=${encodeURIComponent(state.resolvedSymbol)}&interval=${state.currentInterval}&before=${state.historyOldestTime}`);
    if (!res.ok) return;
    const payload = await res.json();
    if (myGeneration !== state.loadGeneration) return; // a fresh loadCandles() superseded this — discard
    // Defensive dedupe: only ever accept rows strictly older than what we already have,
    // even though the backend already filters on `before` — never hand the chart
    // overlapping/duplicate timestamps (Lightweight-Charts rejects non-monotonic data).
    const newRows = payload.candles.filter(c => c.time < state.historyOldestTime);
    if (!newRows.length) { state.historyExhausted = true; return; }

    const prevRange = chart.timeScale().getVisibleLogicalRange();
    const addedCount = newRows.length;
    state.latestCandles = [...newRows, ...state.latestCandles];
    state.historyOldestTime = state.latestCandles[0].time;

    syncStyleData();
    renderIndicators();
    computeDayBoundaries();
    if (prevRange) {
      chart.timeScale().setVisibleLogicalRange({ from: prevRange.from + addedCount, to: prevRange.to + addedCount });
    }
  } catch (e) { /* older history is a nicety — failing quietly is fine */ }
  finally {
    state.loadingHistory = false;
    unsuppressSoon();
  }
}

chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
  if (state.suppressRangeEvents || !range) return;
  if (range.from < 10) loadMoreHistory();
});

// ---------- live quotes ----------
export async function pollQuote() {
  state.quotesInFlight++;
  // A quote fetch for the PRE-switch symbol can resolve after the user has already
  // switched; without this guard it would overwrite the price display with the wrong
  // symbol's number and fold a wrong-symbol price into the current chart's last candle.
  const symbolAtRequest = state.currentSymbol;
  try {
    const res = await fetch(`/api/quote?symbol=${encodeURIComponent(symbolAtRequest)}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const q = await res.json();
    if (symbolAtRequest !== state.currentSymbol) return;
    const priceEl = $('price');
    const changeEl = $('change');
    const up = q.change >= 0;
    priceEl.textContent = q.price.toFixed(2);
    changeEl.textContent = `${up ? '▲' : '▼'} ${up ? '+' : ''}${q.change.toFixed(2)} (${q.changePercent.toFixed(2)}%)`;
    changeEl.className = `chip ${up ? 'up' : 'down'}`;
    document.title = `${q.price.toFixed(2)} ${displayName(state.currentSymbol)} — Orazio`;
    applyLineAreaColor(up);

    if (state.lastPolledPrice !== null && q.price !== state.lastPolledPrice) {
      const dir = q.price > state.lastPolledPrice ? 'flash-up' : 'flash-down';
      priceEl.classList.remove('flash-up', 'flash-down');
      priceEl.classList.add(dir);
      clearTimeout(state.priceFlashTimer);
      state.priceFlashTimer = setTimeout(() => priceEl.classList.remove(dir), 500);
      state.tickChangedAt = q.time;
    }
    state.lastPolledPrice = q.price;
    showFreshness(q);
    foldTickIntoChart(q.price, q.time, q);
  } catch (e) { setConn('err'); }
  finally { state.quotesInFlight--; }
}

// Yahoo publishes each 1m bar ~1 minute after it opens, so a chart built only from
// /api/candles can never show the current minute. Build it from live ticks instead:
// patch the newest bar, and open a NEW bar locally when the clock crosses a bar
// boundary. The periodic refetch replaces these with Yahoo's authoritative bars.
function pushLiveBar(bar, isNew) {
  if (state.currentStyle === 'candle') candleSeries.update(bar);
  else if (state.currentStyle === 'bar') barSeries.update(bar);
  else if (state.currentStyle === 'line') lineSeries.update({ time: bar.time, value: bar.close });
  else areaSeries.update({ time: bar.time, value: bar.close });
  if (isNew && $('vol').checked) {
    volumeSeries.update({ time: bar.time, value: 0, color: COLORS.volUp });
  }
  updateLegend(null);
}

function foldTickIntoChart(price, nowSec, q = {}) {
  if (!state.latestCandles.length) return;
  const last = state.latestCandles[state.latestCandles.length - 1];
  const step = INTERVAL_SECONDS[state.currentInterval];
  // A quote is "fresh" when the exchange tick itself is recent. That — not the age of
  // Yahoo's newest BAR — decides whether to open live candles: SENSEX bars from Yahoo are
  // ~15 min old, but BSE's quote is current, so the live bar must still be allowed.
  const fresh = q.delaySec !== null && q.delaySec !== undefined && q.delaySec < 180;
  const recentBar = step ? (nowSec - last.time < 2 * step + 240)
                         : (state.currentInterval === '1d' && nowSec - last.time < 86400);
  if (!fresh && !recentBar) return; // market closed / stale everywhere: never paint onto old bars

  // Bucket by the tick's own time when we have it, anchored to the last bar's grid
  // (Yahoo's 1h bars start at :15, not :00) so bars stay aligned even across a data gap.
  const tickSec = fresh && q.marketTime ? q.marketTime : nowSec;
  const bucket = step ? last.time + Math.floor((tickSec - last.time) / step) * step : last.time;
  // Only open a new bar while the feed is actually moving, so a frozen post-close
  // quote can't spawn phantom flat candles.
  if (step && bucket > last.time && (fresh || nowSec - state.tickChangedAt < 90)) {
    const bar = { time: bucket, open: price, high: price, low: price, close: price, volume: 0 };
    state.latestCandles.push(bar);
    pushLiveBar(bar, true);
    return;
  }
  const updated = { ...last, close: price, high: Math.max(last.high, price), low: Math.min(last.low, price) };
  state.latestCandles[state.latestCandles.length - 1] = updated;
  pushLiveBar(updated, false);
}
