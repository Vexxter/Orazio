// Alert rules on daily bars — pure, unit-tested in Node (tests/frontend/alert-rules.test.mjs). The same function
// decides a live alert (today's bar carries the live price) and its backtest (every past day it would have fired).
import { rsi, sma } from './indicators.js';

export const RULES = {
  above: { label: 'Price crosses above', unit: '' },
  below: { label: 'Price crosses below', unit: '' },
  chgUp: { label: 'Day change ≥ +X%', unit: '%' },
  chgDown: { label: 'Day change ≤ −X%', unit: '%' },
  rsiAbove: { label: 'RSI(14) crosses above', unit: '' },
  rsiBelow: { label: 'RSI(14) crosses below', unit: '' },
  smaAbove: { label: 'Close crosses above SMA(X)', unit: 'd' },
  smaBelow: { label: 'Close crosses below SMA(X)', unit: 'd' },
};

// Per bar: the value the rule compares, or null before it exists.
function values(bars, rule) {
  const x = rule.value;
  if (rule.type === 'chgUp' || rule.type === 'chgDown') return bars.map((b, i) => (i ? (b.close / bars[i - 1].close - 1) * 100 : null));
  if (rule.type.startsWith('rsi')) {
    const r = rsi(bars, 14), off = bars.length - r.length;
    return bars.map((_, i) => (i >= off ? r[i - off].value : null));
  }
  if (rule.type.startsWith('sma')) {
    const s = sma(bars, Math.max(2, Math.round(x))), off = bars.length - s.length;
    return bars.map((b, i) => (i >= off ? b.close - s[i - off].value : null));   // > 0 = above the average
  }
  return bars.map(b => b.close);
}

// Indices of the bars on which the rule fires. Crossing rules fire on the first bar past the line (they need
// the bar before to be on the other side); change rules fire on every qualifying day.
export function fires(bars, rule) {
  const v = values(bars, rule);
  const level = rule.type.startsWith('sma') ? 0 : rule.value;
  const out = [];
  for (let i = 1; i < bars.length; i++) {
    if (v[i] === null) continue;
    let hit;
    if (rule.type === 'chgUp') hit = v[i] >= rule.value;
    else if (rule.type === 'chgDown') hit = v[i] <= -Math.abs(rule.value);
    else {
      if (v[i - 1] === null) continue;
      const up = rule.type.endsWith('bove');
      hit = up ? v[i - 1] <= level && v[i] > level : v[i - 1] >= level && v[i] < level;
    }
    if (hit) out.push(i);
  }
  return out;
}

// Daily bars with today's bar replaced (or appended) by the live price, so the last index is "now".
export function withLive(bars, price, nowSec) {
  if (!bars.length || !Number.isFinite(price)) return bars;
  const day = (t) => Math.floor((t + 19800) / 86400);
  const last = bars.at(-1);
  if (day(last.time) === day(nowSec)) return [...bars.slice(0, -1), { ...last, close: price, high: Math.max(last.high, price), low: Math.min(last.low, price) }];
  return [...bars, { time: nowSec, open: price, high: price, low: price, close: price }];
}

export function describe(rule) {
  const label = RULES[rule.type].label;
  return `${rule.symbol} · ${label.includes('X') ? label.replace('X', rule.value) : `${label} ${rule.value}`}`;
}
