// Shared mutable state, as a single object so every module can read and write it
// without running into ES modules' read-only import bindings (`let` exports can't
// be reassigned by an importer; properties on an exported object can).
export const $ = (id) => document.getElementById(id);

export const IST = 'Asia/Kolkata';
export const timeFmt = new Intl.DateTimeFormat('en-IN', { timeZone: IST, hour: '2-digit', minute: '2-digit', hour12: false });
// Year included everywhere a date is shown — without it, multi-year ranges (5Y/All)
// are ambiguous about which "18 Sep" you're looking at.
export const dateFmt = new Intl.DateTimeFormat('en-IN', { timeZone: IST, day: '2-digit', month: 'short', year: 'numeric' });
export const dateTimeFmt = new Intl.DateTimeFormat('en-IN', { timeZone: IST, day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false });
export const clockFmt = new Intl.DateTimeFormat('en-GB', { timeZone: IST, hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
export const istHms = new Intl.DateTimeFormat('en-GB', { timeZone: IST, hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
export const INTERVAL_LABEL = { '1m': '1m', '5m': '5m', '15m': '15m', '1h': '1h', '1d': '1D' };
export const INTERVAL_SECONDS = { '1m': 60, '5m': 300, '15m': 900, '1h': 3600 };

export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

export function dayKey(t) {
  return new Intl.DateTimeFormat('en-CA', { timeZone: IST, year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(t * 1000));
}

// ---------- design tokens shared with styles.css ----------
// getComputedStyle() returns a LIVE view of the element's style, so token() always
// reflects whichever [data-theme] block is currently active — no re-query needed.
const css = getComputedStyle(document.documentElement);
const token = (n) => css.getPropertyValue(n).trim();
const alpha = (hex, a) => {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${n >> 16}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
};
export { token, alpha };

function computeColors() {
  return {
    bg: token('--bg-1'), grid: token('--line'), border: token('--line-strong'), text: token('--text-dim'),
    accent: token('--accent'), up: token('--up'), down: token('--down'), crosshair: token('--crosshair'),
    volUp: alpha(token('--up'), 0.45), volDown: alpha(token('--down'), 0.45),
  };
}

// A single mutated-in-place object (not reassigned) so every `COLORS.x` read across the
// app — all of them at call time, none destructured into a local at import time — keeps
// working after a theme switch without touching every consumer file.
export const COLORS = computeColors();
export function refreshColors() {
  Object.assign(COLORS, computeColors());
}

// "ES=F" is the CME's S&P 500 futures contract — real, but unreadable. Show its name.
export const displayName = (sym) => (state.CONFIG.futuresMeta && state.CONFIG.futuresMeta[sym] && state.CONFIG.futuresMeta[sym].name) || sym;

export const state = {
  currentStyle: 'candle',
  currentSymbol: 'NIFTY',
  currentInterval: '1m',
  selectedInterval: '1m',
  currentRange: '1D',
  latestCandles: [],
  priceFlashTimer: null,
  resolvedSymbol: null,
  historyOldestTime: null,
  historyExhausted: false,
  loadingHistory: false,
  CONFIG: { quickIndices: [], futuresMap: {}, futuresMeta: {} },
  dayBoundaryTimes: new Set(),
  // Guards the history-prefetch listener against firing on range changes WE caused
  // (setData/fitContent/setVisibleRange), not the user.
  suppressRangeEvents: false,
  // Bumped at the start of every loadCandles() call. A stale response (e.g. a slow request
  // resolving after a newer range/symbol click already started another load) is detected
  // and discarded instead of overwriting fresher chart state.
  loadGeneration: 0,
  candlesAbortController: null,
  lastPolledPrice: null,
  quotesInFlight: 0,
  tickChangedAt: 0,
  // Line/Area series color follows the session's direction (current price vs. previous
  // close), not a fixed accent color. null = not known yet (no quote polled for this symbol).
  lineAreaUp: null,
};

export function unsuppressSoon() {
  setTimeout(() => { state.suppressRangeEvents = false; }, 80);
}
