// Bar replay's rules as pure functions, unit-tested in Node (tests/frontend/replay-policy.test.mjs).
// replay.js owns the chart and the controls.

export const SPEEDS = [1, 3, 10];             // bars per second
export const tickMs = (speed) => 1000 / speed;

// Index of the last bar at or before time t (-1 when t is before the first bar).
export function indexAtTime(bars, t) {
  let lo = 0, hi = bars.length - 1, found = -1;
  while (lo <= hi) {
    const m = (lo + hi) >> 1;
    if (bars[m].time <= t) { found = m; lo = m + 1; } else hi = m - 1;
  }
  return found;
}

// A replay needs a bar to start on and at least one bar after it to reveal.
export const canStartAt = (idx, n) => idx >= 0 && idx < n - 1;

export const atEnd = (idx, n) => idx >= n - 1;
export const nextIndex = (idx, n) => Math.min(idx + 1, n - 1);
