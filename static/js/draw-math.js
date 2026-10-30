// The geometry behind the drawing tools, as pure functions of { t, price } anchors — no chart, no DOM —
// so it is unit-tested in Node (tests/frontend/draw-math.test.mjs). Pixels stay in draw.js.
//
// Storage shapes: trendlines and horizontal lines keep the format older versions saved
// ({ type:'trend', a, b } and { type:'hline', price }), so existing drawings load untouched. Every
// newer tool is { type, pts: [{ t, price }, ...], text? }. anchorsOf/withAnchors hide the difference.
import { anchorSeconds } from './anchor-math.js';

// Clicks it takes to place each tool.
export const TOOL_CLICKS = { trend: 2, hline: 1, fib: 2, rect: 2, ray: 1, channel: 3, text: 1 };

export const FIB_LEVELS = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1];

// Retracement from A (start of the move, level 1) to B (end of the move, level 0).
export function fibPrices(a, b) {
  return FIB_LEVELS.map(level => ({ level, price: b.price - (b.price - a.price) * level }));
}

// How far C sits above (+) or below (-) the line through A and B, measured at C's time: the
// channel's second line is the A–B line shifted by this much.
export function channelOffset(a, b, c, step) {
  const ta = anchorSeconds(a, step), tb = anchorSeconds(b, step), tc = anchorSeconds(c, step);
  const onLine = tb === ta ? a.price : a.price + (b.price - a.price) * (tc - ta) / (tb - ta);
  return c.price - onLine;
}

export function anchorsOf(d) {
  if (d.type === 'trend') return [d.a, d.b];
  if (d.type === 'hline') return [{ price: d.price }];
  return d.pts || [];
}

export function withAnchors(d, anchors) {
  if (d.type === 'trend') return { ...d, a: anchors[0], b: anchors[1] };
  if (d.type === 'hline') return { ...d, price: anchors[0].price };
  return { ...d, pts: anchors };
}

// Shift one anchor by dt seconds and dp price. Anchors saved in the old { time, off } form come out
// as { t, price }; a horizontal line's anchor has no time and only moves in price.
export function moveAnchor(p, dt, dp, step) {
  if (p.t === undefined && p.time === undefined) return { price: p.price + dp };
  return { t: anchorSeconds(p, step) + dt, price: p.price + dp };
}

export function moveDrawing(d, dt, dp, step) {
  return withAnchors(d, anchorsOf(d).map(p => moveAnchor(p, dt, dp, step)));
}

// Replace anchor i (a handle drag) with point p; a horizontal line keeps only the price.
export function setAnchor(d, i, p) {
  const anchors = anchorsOf(d).slice();
  anchors[i] = d.type === 'hline' ? { price: p.price } : p;
  return withAnchors(d, anchors);
}
