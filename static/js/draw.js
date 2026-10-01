// Trendline + horizontal-line drawing tools, built the same way measure.js is: a DOM/SVG
// overlay positioned via logicalToCoordinate/priceToCoordinate (Lightweight Charts v4 has no
// primitives API of its own). Unlike measure, these persist — per symbol, in localStorage —
// and survive reloads, symbol switches and theme changes.
import { chart, priceSeriesByStyle, syncOverlayInset } from './chart.js';
import { pointFromParam, toXY, trendReadout } from './anchor.js';
import { $, state } from './state.js';
import { createDrawingStore, browserStorage } from './drawings-store.js';
import { clearMeasure, toggleMeasure } from './measure.js';

const store = createDrawingStore(browserStorage);
const overlay = $('draw-overlay');
const trendBtn = $('trend-btn');
const hlineBtn = $('hline-btn');
const clearBtn = $('draw-clear-btn');

let mode = null; // 'trend' | 'hline' | null
let pendingA = null; // first click of a trendline, awaiting the second
let drawings = []; // [{type:'trend', a:{t,price}, b:{t,price}} | {type:'hline', price}]
let lastSymbol = null;

function persist() { store.set(state.currentSymbol, drawings); }
function loadForCurrentSymbol() { drawings = store.get(state.currentSymbol); }

function removeDrawing(index) {
  drawings.splice(index, 1);
  persist();
  render();
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

  const round = (v) => Math.round(v * 2) / 2;
  const items = [];
  drawings.forEach((d, i) => {
    if (d.type === 'trend') {
      const a = toXY(d.a);
      const b = toXY(d.b);
      if (a.x !== null && a.y !== null && b.x !== null && b.y !== null) {
        items.push({ kind: 'trend', i, a: { x: round(a.x), y: round(a.y) }, b: { x: round(b.x), y: round(b.y) }, read: trendReadout(d.a, d.b) });
      }
    } else {
      const y = priceSeriesByStyle[state.currentStyle].priceToCoordinate(d.price);
      if (y !== null && y !== undefined) items.push({ kind: 'hline', i, y: round(y) });
    }
  });
  if (mode === 'trend' && pendingA) {
    const a = toXY(pendingA);
    if (a.x !== null && a.y !== null) items.push({ kind: 'dot', x: round(a.x), y: round(a.y) });
  }

  const key = JSON.stringify(items);
  if (key === lastKey) return;
  lastKey = key;

  overlay.innerHTML = '';
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('class', 'draw-svg');
  overlay.appendChild(svg);
  for (const it of items) {
    if (it.kind === 'trend') renderTrend(it, svg);
    else if (it.kind === 'hline') renderHLine(it);
    else {
      const dot = document.createElement('div');
      dot.className = 'draw-dot';
      dot.style.left = `${it.x}px`;
      dot.style.top = `${it.y}px`;
      overlay.appendChild(dot);
    }
  }
}

function renderTrend(it, svg) {
  const { a, b, i } = it;
  const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
  line.setAttribute('x1', a.x); line.setAttribute('y1', a.y);
  line.setAttribute('x2', b.x); line.setAttribute('y2', b.y);
  line.setAttribute('class', 'trend-line-el');
  svg.appendChild(line);

  const mid = document.createElement('div');
  mid.className = 'draw-handle';
  mid.style.left = `${(a.x + b.x) / 2}px`;
  mid.style.top = `${(a.y + b.y) / 2}px`;
  mid.innerHTML = '<button type="button" class="draw-del" aria-label="Delete trendline" title="Delete">×</button>';
  mid.querySelector('button').addEventListener('click', () => removeDrawing(i));
  overlay.appendChild(mid);

  // The trend readout: how far price moved between the two points, and over how long.
  const label = document.createElement('div');
  label.className = `measure-label trend-label ${it.read.up ? 'up' : 'down'}`;
  label.style.left = `${(a.x + b.x) / 2}px`;
  label.style.top = `${(a.y + b.y) / 2 - 14}px`;
  label.textContent = it.read.text;
  overlay.appendChild(label);
}

function renderHLine(it) {
  const row = document.createElement('div');
  row.className = 'hline-row';
  row.style.top = `${it.y}px`;
  row.innerHTML = `<div class="hline-el"></div><div class="hline-hit"></div><button type="button" class="draw-del hline-del" aria-label="Delete line" title="Delete">×</button>`;
  row.querySelector('button').addEventListener('click', () => removeDrawing(it.i));
  overlay.appendChild(row);
}

function setMode(next) {
  // Always unsubscribe first: switching straight from one mode to another (trend ->
  // hline without passing through "off") must not leave a stale registration of the
  // same onClick behind — subscribeClick doesn't dedupe, so that would double-fire it.
  chart.unsubscribeClick(onClick);
  mode = mode === next ? null : next;
  pendingA = null;
  if (mode) {
    toggleMeasure(true); // only one click-to-place tool active at a time
    chart.subscribeClick(onClick);
  }
  trendBtn.setAttribute('aria-pressed', String(mode === 'trend'));
  hlineBtn.setAttribute('aria-pressed', String(mode === 'hline'));
  render();
}

function onClick(param) {
  if (!mode) return;
  const point = pointFromParam(param);
  if (!point) return;
  const price = point.price;

  if (mode === 'hline') {
    drawings.push({ type: 'hline', price });
    persist();
    render();
    return;
  }

  // trendline: first click starts it, second click completes it and the tool stays
  // active — ready for the next one, exactly like the measure tool's flow.
  if (!pendingA) {
    pendingA = point;
  } else {
    drawings.push({ type: 'trend', a: pendingA, b: point });
    pendingA = null;
    persist();
  }
  render();
}

export function turnOffDrawing() {
  if (mode) setMode(mode); // toggles it off via the XOR in setMode
}

trendBtn.addEventListener('click', () => setMode('trend'));
hlineBtn.addEventListener('click', () => setMode('hline'));
// Clear wipes everything drawn on this chart: saved trendlines/lines, a half-placed trendline, and
// the measure tool's current measurement (it used to ignore the measure tool entirely).
clearBtn.addEventListener('click', () => {
  drawings = [];
  pendingA = null;
  persist();
  clearMeasure();
  render();
});
document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape' || !mode) return;
  if (pendingA) { pendingA = null; render(); } else setMode(mode);
});

chart.timeScale().subscribeVisibleTimeRangeChange(render);
new ResizeObserver(render).observe($('chart'));
setInterval(render, 1000); // catches autoscale drift from live ticks, same tradeoff measure.js accepts
render();
