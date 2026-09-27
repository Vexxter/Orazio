// Two-point measure tool: click point A, click point B, see the price/% change between
// them. A DOM overlay positioned via the same timeToCoordinate/priceToCoordinate
// technique chart.js already uses for the day-boundary lines (Lightweight Charts v4 has
// no primitives API for custom drawings).
import { chart, priceSeriesByStyle } from './chart.js';
import { $, state } from './state.js';

const overlay = $('measure-overlay');
const btn = $('measure-btn');
let active = false;
let pointA = null;
let pointB = null;

function toXY(time, price) {
  const x = chart.timeScale().timeToCoordinate(time);
  const y = priceSeriesByStyle[state.currentStyle].priceToCoordinate(price);
  return { x, y };
}

function render() {
  overlay.innerHTML = '';
  if (!pointA) return;
  const a = toXY(pointA.time, pointA.price);
  if (a.x === null || a.y === null) return;

  if (!pointB) {
    const dot = document.createElement('div');
    dot.className = 'measure-dot';
    dot.style.left = `${a.x}px`;
    dot.style.top = `${a.y}px`;
    overlay.appendChild(dot);
    return;
  }

  const b = toXY(pointB.time, pointB.price);
  if (b.x === null || b.y === null) return;

  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('class', 'measure-svg');
  const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
  line.setAttribute('x1', a.x); line.setAttribute('y1', a.y);
  line.setAttribute('x2', b.x); line.setAttribute('y2', b.y);
  line.setAttribute('class', 'measure-line-el');
  svg.appendChild(line);
  overlay.appendChild(svg);

  const diff = pointB.price - pointA.price;
  const pct = pointA.price ? (diff / pointA.price) * 100 : 0;
  const up = diff >= 0;
  const span = formatSpan(Math.abs(pointB.time - pointA.time));

  const label = document.createElement('div');
  label.className = `measure-label ${up ? 'up' : 'down'}`;
  label.style.left = `${(a.x + b.x) / 2}px`;
  label.style.top = `${Math.min(a.y, b.y) - 10}px`;
  label.textContent = `${up ? '▲' : '▼'} ${up ? '+' : ''}${diff.toFixed(2)} (${up ? '+' : ''}${pct.toFixed(2)}%) · ${span}`;
  overlay.appendChild(label);
}

function formatSpan(sec) {
  const d = Math.floor(sec / 86400);
  const h = Math.floor((sec % 86400) / 3600);
  const m = Math.floor((sec % 3600) / 60);
  if (d) return `${d}d ${h}h`;
  if (h) return `${h}h ${m}m`;
  return `${m}m`;
}

function clear() {
  pointA = null;
  pointB = null;
  overlay.innerHTML = '';
}

function onClick(param) {
  if (!active || !param.point || param.time === undefined) return;
  const price = priceSeriesByStyle[state.currentStyle].coordinateToPrice(param.point.y);
  if (price === null || price === undefined) return;
  const point = { time: param.time, price };
  if (!pointA || pointB) {
    pointA = point;
    pointB = null;
  } else {
    pointB = point;
  }
  render();
}

export function toggleMeasure(forceOff) {
  active = forceOff ? false : !active;
  btn.setAttribute('aria-pressed', String(active));
  if (active) chart.subscribeClick(onClick);
  else { chart.unsubscribeClick(onClick); clear(); }
}

chart.timeScale().subscribeVisibleTimeRangeChange(render);
new ResizeObserver(render).observe($('chart'));
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && active) toggleMeasure(true); });
btn.addEventListener('click', () => toggleMeasure());
