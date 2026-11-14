// Drawing tools — trendline, horizontal line, horizontal ray, rectangle, Fibonacci retracement,
// parallel channel and text note — built the same way measure.js is: a DOM/SVG overlay positioned via
// logicalToCoordinate/priceToCoordinate (Lightweight Charts v4 has no primitives API of its own).
// They persist per symbol in localStorage, and survive reloads, symbol switches and theme changes.
// The geometry (fib levels, channel offset, moving a drawing) lives in draw-math.js, unit-tested.
//
// Editing: every drawing has a dot on each anchor point (drag it to move that point) and an invisible
// wide stroke along its lines (drag it to move the whole drawing). The overlay sits above the chart's
// canvas, so a drag never reaches the chart and can't pan it. Double-click a text note to edit it.
import { chart, priceSeriesByStyle, syncOverlayInset } from './chart.js';
import { pointFromParam, pointFromXY, stepSec, toXY, trendReadout } from './anchor.js';
import { TOOL_CLICKS, anchorsOf, channelOffset, fibPrices, moveDrawing, setAnchor } from './draw-math.js';
import { $, state, visible } from './state.js';
import { createDrawingStore, browserStorage } from './drawings-store.js';
import { clearMeasure, toggleMeasure } from './measure.js';

const SVG_NS = 'http://www.w3.org/2000/svg';
const store = createDrawingStore(browserStorage);
const overlay = $('draw-overlay');
const clearBtn = $('draw-clear-btn');
const buttons = Object.fromEntries(Object.keys(TOOL_CLICKS).map(t => [t, $(`${t}-btn`)]));

let mode = null;     // a TOOL_CLICKS key, or null
let pending = [];    // points clicked so far for the drawing being placed
let drawings = [];   // see draw-math.js for the shapes
let lastSymbol = null;
let drag = null;     // { i, anchor (index, or null = whole drawing), start, orig, moved }

function persist() { store.set(state.currentSymbol, drawings); }
function loadForCurrentSymbol() { drawings = store.get(state.currentSymbol); }

function removeDrawing(index) {
  drawings.splice(index, 1);
  persist();
  render();
}

const round = (v) => Math.round(v * 2) / 2;
function px(p) {
  const { x, y } = toXY(p);
  return x === null || y === null || x === undefined || y === undefined ? null : { x: round(x), y: round(y) };
}
const priceY = (price) => {
  const y = priceSeriesByStyle[state.currentStyle].priceToCoordinate(price);
  return y === null || y === undefined ? null : round(y);
};

// Pixel layout of one drawing, or null when it is off the chart's coordinate space.
function layout(d, i) {
  const step = stepSec();
  if (d.type === 'hline') {
    const y = priceY(d.price);
    return y === null ? null : { kind: 'hline', i, y };
  }
  const pts = anchorsOf(d).map(px);
  if (pts.some(p => !p)) return null;
  const [A, B] = anchorsOf(d);
  switch (d.type) {
    case 'trend': return { kind: 'trend', i, pts, read: trendReadout(A, B) };
    case 'ray': return { kind: 'ray', i, pts, price: A.price.toFixed(2) };
    case 'rect': return { kind: 'rect', i, pts, read: trendReadout(A, B) };
    case 'text': return { kind: 'text', i, pts, text: d.text || '' };
    case 'fib': {
      const levels = fibPrices(A, B).map(l => ({ level: l.level, price: l.price.toFixed(2), y: priceY(l.price) }));
      return levels.some(l => l.y === null) ? null : { kind: 'fib', i, pts, levels };
    }
    case 'channel': {
      const off = channelOffset(A, B, anchorsOf(d)[2], step);
      const a2 = px({ ...A, price: A.price + off });
      const b2 = px({ ...B, price: B.price + off });
      return a2 && b2 ? { kind: 'channel', i, pts, a2, b2 } : null;
    }
    default: return null;
  }
}

let lastKey = null;

// Rebuilding the overlay DOM replaces every button in it — including the delete × a moment
// before it is clicked. render() runs on every pan, resize and once a second, so it works out
// where everything goes first and only touches the DOM when that actually changed.
function render() {
  syncOverlayInset();
  // A symbol switch doesn't fire any event this module listens to directly — the periodic
  // tick (below) and every render() call both notice it here and pick up that symbol's set.
  if (state.currentSymbol !== lastSymbol) {
    lastSymbol = state.currentSymbol;
    loadForCurrentSymbol();
  }

  const items = drawings.map(layout).filter(Boolean);
  for (const p of pending) {
    const xy = px(p);
    if (xy) items.push({ kind: 'dot', ...xy });
  }
  const width = overlay.clientWidth;
  const key = JSON.stringify([width, mode, items]);
  if (key === lastKey) return;
  lastKey = key;

  overlay.innerHTML = '';
  overlay.classList.toggle('placing', !!mode);
  const svg = el(SVG_NS, 'svg', { class: 'draw-svg' });
  overlay.appendChild(svg);
  for (const it of items) RENDER[it.kind](it, svg, width);
}

// ---------- DOM helpers ----------
function el(ns, tag, attrs = {}) {
  const node = ns ? document.createElementNS(ns, tag) : document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  return node;
}
function at(node, x, y) { node.style.left = `${x}px`; node.style.top = `${y}px`; return node; }

function svgLine(svg, a, b, cls, i) {
  svg.appendChild(el(SVG_NS, 'line', { x1: a.x, y1: a.y, x2: b.x, y2: b.y, class: cls }));
  // A wide invisible twin along the same line: the grab area for moving the whole drawing.
  if (i !== undefined) {
    const hit = el(SVG_NS, 'line', { x1: a.x, y1: a.y, x2: b.x, y2: b.y, class: 'draw-hit' });
    hit.addEventListener('mousedown', (e) => startDrag(e, i, null));
    svg.appendChild(hit);
  }
}

function label(text, x, y, cls = '') {
  const node = at(el(null, 'div', { class: `measure-label draw-label ${cls}` }), x, y);
  node.textContent = text;
  overlay.appendChild(node);
  return node;
}

function delButton(i, x, y, name) {
  const h = at(el(null, 'div', { class: 'draw-handle' }), x, y);
  h.innerHTML = `<button type="button" class="draw-del" aria-label="Delete ${name}" title="Delete">×</button>`;
  h.querySelector('button').addEventListener('click', () => removeDrawing(i));
  overlay.appendChild(h);
}

function anchorDots(it) {
  it.pts.forEach((p, k) => {
    const dot = at(el(null, 'div', { class: 'draw-pt', title: 'Drag to move this point' }), p.x, p.y);
    dot.addEventListener('mousedown', (e) => startDrag(e, it.i, k));
    overlay.appendChild(dot);
  });
}

const mid = (a, b) => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });

// ---------- renderers, one per kind ----------
const RENDER = {
  dot(it) { overlay.appendChild(at(el(null, 'div', { class: 'draw-dot' }), it.x, it.y)); },

  trend(it, svg) {
    const [a, b] = it.pts;
    svgLine(svg, a, b, 'trend-line-el', it.i);
    const m = mid(a, b);
    delButton(it.i, m.x, m.y, 'trendline');
    // The trend readout: how far price moved between the two points, and over how long.
    label(it.read.text, m.x, m.y - 14, `trend-label ${it.read.up ? 'up' : 'down'}`);
    anchorDots(it);
  },

  hline(it) {
    const row = el(null, 'div', { class: 'hline-row' });
    row.style.top = `${it.y}px`;
    row.innerHTML = `<div class="hline-el"></div><div class="hline-hit" title="Drag to move"></div><button type="button" class="draw-del hline-del" aria-label="Delete line" title="Delete">×</button>`;
    row.querySelector('button').addEventListener('click', () => removeDrawing(it.i));
    row.querySelector('.hline-hit').addEventListener('mousedown', (e) => startDrag(e, it.i, null));
    overlay.appendChild(row);
  },

  ray(it, svg, width) {
    const [a] = it.pts;
    svgLine(svg, a, { x: width, y: a.y }, 'trend-line-el', it.i);
    label(it.price, a.x + 6, a.y, 'ray-label');
    delButton(it.i, (a.x + width) / 2, a.y, 'ray');
    anchorDots(it);
  },

  rect(it, svg) {
    const [a, b] = it.pts;
    const x = Math.min(a.x, b.x), y = Math.min(a.y, b.y);
    const box = el(SVG_NS, 'rect', { x, y, width: Math.abs(a.x - b.x), height: Math.abs(a.y - b.y), class: 'draw-rect' });
    box.addEventListener('mousedown', (e) => startDrag(e, it.i, null));
    svg.appendChild(box);
    label(it.read.text, x + Math.abs(a.x - b.x) / 2, y - 12, `trend-label ${it.read.up ? 'up' : 'down'}`);
    delButton(it.i, Math.max(a.x, b.x), y, 'rectangle');
    anchorDots(it);
  },

  fib(it, svg) {
    const [a, b] = it.pts;
    const x1 = Math.min(a.x, b.x), x2 = Math.max(a.x, b.x);
    svgLine(svg, a, b, 'fib-diag', it.i);
    for (const l of it.levels) {
      svgLine(svg, { x: x1, y: l.y }, { x: x2, y: l.y }, `fib-line${l.level === 0.5 || l.level === 0.618 ? ' key' : ''}`, it.i);
      label(`${l.level} (${l.price})`, x1, l.y, 'fib-label');
    }
    const m = mid(a, b);
    delButton(it.i, m.x, m.y, 'Fibonacci retracement');
    anchorDots(it);
  },

  channel(it, svg) {
    const [a, b] = it.pts;
    svg.appendChild(el(SVG_NS, 'polygon', { points: `${a.x},${a.y} ${b.x},${b.y} ${it.b2.x},${it.b2.y} ${it.a2.x},${it.a2.y}`, class: 'channel-fill' }));
    svgLine(svg, a, b, 'trend-line-el', it.i);
    svgLine(svg, it.a2, it.b2, 'trend-line-el', it.i);
    svgLine(svg, mid(a, it.a2), mid(b, it.b2), 'channel-mid');
    const m = mid(a, b);
    delButton(it.i, m.x, m.y, 'channel');
    anchorDots(it);
  },

  text(it) {
    const [a] = it.pts;
    const node = at(el(null, 'div', { class: 'draw-note', title: 'Drag to move · double-click to edit' }), a.x, a.y);
    const span = document.createElement('span');
    span.textContent = it.text;
    node.appendChild(span);
    node.insertAdjacentHTML('beforeend', '<button type="button" class="draw-del" aria-label="Delete note" title="Delete">×</button>');
    node.querySelector('button').addEventListener('click', () => removeDrawing(it.i));
    node.querySelector('button').addEventListener('mousedown', (e) => e.stopPropagation());
    node.addEventListener('mousedown', (e) => startDrag(e, it.i, null));
    node.addEventListener('dblclick', () => editNote(it.i));
    overlay.appendChild(node);
  },
};

// ---------- text notes ----------
const MAX_NOTE = 80;
// ponytail: window.prompt is the whole text editor — fine for a short note; an inline editor if notes grow.
function askNote(current = '') {
  const text = window.prompt('Note text', current);
  return text === null ? null : text.trim().slice(0, MAX_NOTE);
}
function editNote(i) {
  const text = askNote(drawings[i].text);
  if (text === null) return;
  if (!text) { removeDrawing(i); return; }
  drawings[i] = { ...drawings[i], text };
  persist();
  render();
}

// ---------- dragging ----------
function pointAt(e) {
  const r = overlay.getBoundingClientRect();
  return pointFromXY(e.clientX - r.left, e.clientY - r.top);
}

function startDrag(e, i, anchor) {
  if (mode || e.button !== 0) return;
  const start = pointAt(e);
  if (!start) return;
  e.preventDefault();
  e.stopPropagation();
  drag = { i, anchor, start, orig: drawings[i], moved: false };
  // ponytail: mouse only — touch drag would need pointer events and touch-action tuning.
  document.addEventListener('mousemove', onDragMove);
  document.addEventListener('mouseup', onDragEnd, { once: true });
}

function onDragMove(e) {
  const p = drag && pointAt(e);
  if (!p) return;
  drag.moved = true;
  drawings[drag.i] = drag.anchor === null
    ? moveDrawing(drag.orig, p.t - drag.start.t, p.price - drag.start.price, stepSec())
    : setAnchor(drag.orig, drag.anchor, p);
  render();
}

function onDragEnd() {
  document.removeEventListener('mousemove', onDragMove);
  if (drag?.moved) persist();
  drag = null;
}

// ---------- placing ----------
function setMode(next) {
  // Always unsubscribe first: switching straight from one mode to another (trend ->
  // hline without passing through "off") must not leave a stale registration of the
  // same onClick behind — subscribeClick doesn't dedupe, so that would double-fire it.
  chart.unsubscribeClick(onClick);
  mode = mode === next ? null : next;
  pending = [];
  if (mode) {
    toggleMeasure(true); // only one click-to-place tool active at a time
    chart.subscribeClick(onClick);
  }
  for (const [tool, btn] of Object.entries(buttons)) btn.setAttribute('aria-pressed', String(mode === tool));
  render();
}

function onClick(param) {
  if (!mode) return;
  const point = pointFromParam(param);
  if (!point) return;
  pending.push(point);
  // Multi-click tools stay active after each one is placed — ready for the next, like measure.
  if (pending.length < TOOL_CLICKS[mode]) { render(); return; }
  const pts = pending;
  pending = [];
  if (mode === 'hline') drawings.push({ type: 'hline', price: pts[0].price });
  else if (mode === 'trend') drawings.push({ type: 'trend', a: pts[0], b: pts[1] });
  else if (mode === 'text') {
    const text = askNote();
    if (text) drawings.push({ type: 'text', pts, text });
  } else drawings.push({ type: mode, pts });
  persist();
  render();
}

export function turnOffDrawing() {
  if (mode) setMode(mode); // toggles it off via the XOR in setMode
}

for (const [tool, btn] of Object.entries(buttons)) btn.addEventListener('click', () => setMode(tool));
// Clear wipes everything drawn on this chart: saved drawings, a half-placed one, and the measure
// tool's current measurement.
clearBtn.addEventListener('click', () => {
  drawings = [];
  pending = [];
  persist();
  clearMeasure();
  render();
});
document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape' || !mode) return;
  if (pending.length) { pending = []; render(); } else setMode(mode);
});

chart.timeScale().subscribeVisibleTimeRangeChange(render);
new ResizeObserver(render).observe($('chart'));
setInterval(visible(render), 1000); // catches autoscale drift from live ticks, same tradeoff measure.js accepts
render();
