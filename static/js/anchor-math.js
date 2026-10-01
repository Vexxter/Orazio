// The geometry behind measure/trendline points — pure functions of (bars, step), no chart and no
// DOM, so they are unit-tested in Node (tests/frontend/anchor-math.test.mjs).
//
// A point is { t, price }: t is an absolute time in seconds (fractional). Nothing about it depends
// on which bars exist, so it lands correctly on 1m, 5m, 1h or daily bars alike. The chart gives us
// a click as a LOGICAL position (0 = first bar, fractions between bars); these convert between that
// and seconds by interpolating between neighbouring bars' times. Past either end they extrapolate
// using one `step` per bar.
import { formatSpan, signed } from './format.js';

export function logicalToSeconds(bars, step, logical) {
  const n = bars.length;
  const i = Math.floor(logical);
  if (i < 0) return bars[0].time + logical * step;
  if (i >= n - 1) return bars[n - 1].time + (logical - (n - 1)) * step;
  return bars[i].time + (logical - i) * (bars[i + 1].time - bars[i].time);
}

export function secondsToLogical(bars, step, t) {
  const n = bars.length;
  if (t <= bars[0].time) return (t - bars[0].time) / step;
  if (t >= bars[n - 1].time) return n - 1 + (t - bars[n - 1].time) / step;
  let lo = 0, hi = n - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (bars[mid].time <= t) lo = mid; else hi = mid;
  }
  return lo + (t - bars[lo].time) / (bars[hi].time - bars[lo].time);
}

// Points saved by an older format were { time, off } (a bar time plus a fractional bar offset).
export function anchorSeconds(p, step) {
  return p.t !== undefined ? p.t : p.time + (p.off || 0) * step;
}

// "▲ +12.50 (+0.06%) · 15m" — the readout shared by the measure tool and trendlines.
export function trendReadout(a, b, step) {
  const diff = b.price - a.price;
  const pct = a.price ? (diff / a.price) * 100 : 0;
  const up = diff >= 0;
  const span = formatSpan(Math.abs(anchorSeconds(b, step) - anchorSeconds(a, step)));
  return { up, text: `${up ? '▲' : '▼'} ${signed(diff)} (${signed(pct)}%) · ${span}` };
}
