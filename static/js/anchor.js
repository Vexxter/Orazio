// Chart-anchored points for the measure and drawing tools: the thin, chart-aware layer over the
// pure geometry in anchor-math.js (which is where the maths and its tests live).
import { chart, priceSeriesByStyle } from './chart.js';
import { anchorSeconds as anchorSecondsFor, logicalToSeconds, secondsToLogical, trendReadout as readout } from './anchor-math.js';
import { INTERVAL_SECONDS, state } from './state.js';

const series = () => priceSeriesByStyle[state.currentStyle];
export const stepSec = () => INTERVAL_SECONDS[state.currentInterval] || 86400;

export function anchorSeconds(p) { return anchorSecondsFor(p, stepSec()); }
export function trendReadout(a, b) { return readout(a, b, stepSec()); }

// A pixel position on the plot -> { t, price } (used by clicks and by dragging a drawing).
export function pointFromXY(x, y) {
  if (!state.latestCandles.length) return null;
  const price = series().coordinateToPrice(y);
  const logical = chart.timeScale().coordinateToLogical(x);
  if (price === null || price === undefined || logical === null) return null;
  return { t: logicalToSeconds(state.latestCandles, stepSec(), logical), price };
}

// A click -> { t, price }. Lightweight Charts reports click time snapped to a bar; the exact spot
// comes from the click's logical (fractional bar) position instead.
export function pointFromParam(param) {
  return param.point ? pointFromXY(param.point.x, param.point.y) : null;
}

// { t, price } -> pixel position on the current chart.
export function toXY(p) {
  if (!state.latestCandles.length) return { x: null, y: null };
  const logical = secondsToLogical(state.latestCandles, stepSec(), anchorSeconds(p));
  const x = chart.timeScale().logicalToCoordinate(logical);
  return { x: x === undefined ? null : x, y: series().priceToCoordinate(p.price) };
}
