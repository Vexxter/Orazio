// Indicator math — pure, no DOM, no app state — so every formula is unit-tested in Node
// (tests/frontend/indicators.test.mjs). Inputs are the chart's bars ({time, open, high, low, close, volume});
// outputs are Lightweight Charts points ({time, value}).

// EMA over a plain number array: null until `n` values exist, seeded with their simple average.
export function emaValues(values, n) {
  const out = new Array(values.length).fill(null);
  if (n < 1 || values.length < n) return out;
  const a = 2 / (n + 1);
  let e = 0;
  for (let i = 0; i < n; i++) e += values[i];
  e /= n;
  out[n - 1] = e;
  for (let i = n; i < values.length; i++) { e += a * (values[i] - e); out[i] = e; }
  return out;
}

// Rolling sum, so a 200-bar SMA over 5000 bars is 5000 steps, not a million.
export function sma(bars, n) {
  const out = [];
  let sum = 0;
  for (let i = 0; i < bars.length; i++) {
    sum += bars[i].close;
    if (i >= n) sum -= bars[i - n].close;
    if (i >= n - 1) out.push({ time: bars[i].time, value: sum / n });
  }
  return out;
}

export function ema(bars, n) {
  const e = emaValues(bars.map(b => b.close), n);
  return bars.flatMap((b, i) => (e[i] === null ? [] : [{ time: b.time, value: e[i] }]));
}

// Bollinger Bands: SMA ± k population standard deviations.
export function bollinger(bars, n = 20, k = 2) {
  const mid = [], upper = [], lower = [];
  for (let i = n - 1; i < bars.length; i++) {
    let s = 0, s2 = 0;
    for (let j = i - n + 1; j <= i; j++) { s += bars[j].close; s2 += bars[j].close ** 2; }
    const m = s / n;
    const sd = Math.sqrt(Math.max(0, s2 / n - m * m));
    const time = bars[i].time;
    mid.push({ time, value: m });
    upper.push({ time, value: m + k * sd });
    lower.push({ time, value: m - k * sd });
  }
  return { mid, upper, lower };
}

// RSI with Wilder's smoothing (the standard definition: first average is a simple mean of n changes).
export function rsi(bars, n = 14) {
  const out = [];
  if (bars.length <= n) return out;
  let gain = 0, loss = 0;
  for (let i = 1; i <= n; i++) {
    const d = bars[i].close - bars[i - 1].close;
    if (d > 0) gain += d; else loss -= d;
  }
  gain /= n; loss /= n;
  const value = () => (loss === 0 ? (gain === 0 ? 50 : 100) : 100 - 100 / (1 + gain / loss));
  out.push({ time: bars[n].time, value: value() });
  for (let i = n + 1; i < bars.length; i++) {
    const d = bars[i].close - bars[i - 1].close;
    gain = (gain * (n - 1) + Math.max(d, 0)) / n;
    loss = (loss * (n - 1) + Math.max(-d, 0)) / n;
    out.push({ time: bars[i].time, value: value() });
  }
  return out;
}

export function macd(bars, fast = 12, slow = 26, signal = 9) {
  const closes = bars.map(b => b.close);
  const f = emaValues(closes, fast), s = emaValues(closes, slow);
  const idx = [], line = [];
  for (let i = 0; i < bars.length; i++) if (f[i] !== null && s[i] !== null) { idx.push(i); line.push(f[i] - s[i]); }
  const sig = emaValues(line, signal);
  const out = { macd: [], signal: [], hist: [] };
  idx.forEach((bi, j) => {
    const time = bars[bi].time;
    out.macd.push({ time, value: line[j] });
    if (sig[j] !== null) {
      out.signal.push({ time, value: sig[j] });
      out.hist.push({ time, value: line[j] - sig[j] });
    }
  });
  return out;
}

// VWAP anchored to each session (dayOf(time) -> session key). A session with no volume at all (an index
// whose volume isn't published) gets no line rather than a fake one.
export function vwap(bars, dayOf) {
  const out = [];
  let day = null, pv = 0, vol = 0;
  for (const b of bars) {
    const d = dayOf(b.time);
    if (d !== day) { day = d; pv = 0; vol = 0; }
    const v = b.volume || 0;
    pv += ((b.high + b.low + b.close) / 3) * v;
    vol += v;
    if (vol > 0) out.push({ time: b.time, value: pv / vol });
  }
  return out;
}

// ---------- moving averages on another timeframe ----------
// IST weeks starting Monday: epoch day 0 (1 Jan 1970) was a Thursday, hence the +3 days.
export const weekKey = (t) => Math.floor((t + 19800 + 3 * 86400) / (7 * 86400));

export function resampleWeekly(daily) {
  const out = [];
  for (const b of daily) {
    const last = out[out.length - 1];
    if (last && weekKey(last.time) === weekKey(b.time)) {
      last.high = Math.max(last.high, b.high);
      last.low = Math.min(last.low, b.low);
      last.close = b.close;
      last.volume = (last.volume || 0) + (b.volume || 0);
    } else out.push({ ...b });
  }
  return out;
}

// Index of the higher-timeframe bar that chart time `t` falls in; htf.length means "a bar that has
// started but isn't in the data yet" (e.g. today, before Yahoo publishes its daily bar); -1 = before the data.
export function locateBar(htf, t, spanSec, keyFn = null) {
  if (!htf.length) return -1;
  if (keyFn) {
    const k = keyFn(t), lastKey = keyFn(htf[htf.length - 1].time);
    if (k > lastKey) return htf.length;
    let lo = 0, hi = htf.length - 1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1, mk = keyFn(htf[mid].time);
      if (mk === k) return mid;
      if (mk < k) lo = mid + 1; else hi = mid - 1;
    }
    return -1;
  }
  let lo = 0, hi = htf.length - 1, found = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (htf[mid].time <= t) { found = mid; lo = mid + 1; } else hi = mid - 1;
  }
  if (found === htf.length - 1 && t >= htf[found].time + spanSec) return htf.length;
  return found;
}

// An N-period SMA/EMA of a higher timeframe, drawn on the chart's own bars WITHOUT look-ahead: at each
// chart bar the still-forming higher-timeframe bar is closed at that chart bar's price — exactly what the
// average read at that moment. (Using the HTF bar's final close would leak the future into the past.)
export function htfAverage(chartBars, htf, n, type, spanSec, keyFn = null) {
  const closes = htf.map(b => b.close);
  const prefix = [0];
  for (const c of closes) prefix.push(prefix[prefix.length - 1] + c);
  const e = type === 'ema' ? emaValues(closes, n) : null;
  const a = 2 / (n + 1);
  const out = [];
  for (const bar of chartBars) {
    const k = locateBar(htf, bar.time, spanSec, keyFn);
    if (k < 0) continue;
    let value;
    if (type === 'ema') {
      if (k - 1 < n - 1) continue;
      value = e[k - 1] + a * (bar.close - e[k - 1]);
    } else {
      if (k - (n - 1) < 0) continue;
      value = (prefix[k] - prefix[k - (n - 1)] + bar.close) / n;
    }
    out.push({ time: bar.time, value });
  }
  return out;
}

// Which history range to fetch so `n` bars of `interval` exist (sessions of ~375 minutes; a little spare).
const RANGE_DAYS = [['1D', 1], ['1W', 5], ['1M', 21], ['3M', 62], ['6M', 124], ['1Y', 248], ['5Y', 1240]];
export function rangeFor(interval, n) {
  const perDay = { '5m': 75, '15m': 25, '1h': 7, '1d': 1, '1w': 0.2 }[interval] || 1;
  const days = Math.ceil(n / perDay) + 2;
  const hit = RANGE_DAYS.find(([, d]) => d >= days);
  return hit ? hit[0] : 'ALL';
}

export const TF_SECONDS = { '5m': 300, '15m': 900, '1h': 3600, '1d': 86400, '1w': 7 * 86400 };
const TF_ORDER = ['1m', '5m', '15m', '1h', '1d', '1w'];
// A timeframe finer than the chart's bars can't be drawn on them (one chart bar spans several).
export const tfUsable = (tf, chartInterval) => tf === 'chart' || TF_ORDER.indexOf(tf) >= TF_ORDER.indexOf(chartInterval);

// ---------- pane layout ----------
// Lightweight Charts v4 has one pane, so oscillators get their own price scale squeezed into a band at
// the bottom (like volume). Bands stack upward: MACD lowest, RSI above it, volume above both.
export const OSC_BAND = 0.18;
export function bandLayout({ vol, rsi: rsiOn, macd: macdOn }) {
  const bands = [macdOn && 'macd', rsiOn && 'rsi'].filter(Boolean);
  const osc = bands.length * OSC_BAND;
  const out = {
    price: { top: 0.08, bottom: osc + (vol ? 0.1 : 0.05) },
    volume: { top: 1 - osc - 0.06, bottom: osc },
    rsi: null, macd: null,
  };
  bands.forEach((name, i) => { out[name] = { top: 1 - (i + 1) * OSC_BAND + 0.02, bottom: i * OSC_BAND + 0.02 }; });
  return out;
}

// Heikin Ashi bars: close = OHLC average, open = midpoint of the previous HA bar's open/close.
export function heikinAshi(bars) {
  const out = [];
  for (const b of bars) {
    const prev = out[out.length - 1];
    const close = (b.open + b.high + b.low + b.close) / 4;
    const open = prev ? (prev.open + prev.close) / 2 : (b.open + b.close) / 2;
    out.push({ time: b.time, open, high: Math.max(b.high, open, close), low: Math.min(b.low, open, close), close });
  }
  return out;
}
