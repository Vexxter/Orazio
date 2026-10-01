// Two-point measure tool: click point A, click point B, see the price/% change between
// them. A DOM overlay positioned via the same timeToCoordinate/priceToCoordinate
// technique chart.js already uses for the day-boundary lines (Lightweight Charts v4 has
// no primitives API for custom drawings).
import { chart, syncOverlayInset } from './chart.js';
import { pointFromParam, toXY, trendReadout } from './anchor.js';
import { $ } from './state.js';

const overlay = $('measure-overlay');
const btn = $('measure-btn');
let active = false;
let pointA = null;
let pointB = null;

function render() {
  syncOverlayInset();
  overlay.innerHTML = '';
  if (!pointA) return;
  const a = toXY(pointA);
  if (a.x === null || a.y === null) return;

  if (!pointB) {
    const dot = document.createElement('div');
    dot.className = 'measure-dot';
    dot.style.left = `${a.x}px`;
    dot.style.top = `${a.y}px`;
    overlay.appendChild(dot);
    return;
  }

  const b = toXY(pointB);
  if (b.x === null || b.y === null) return;

  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('class', 'measure-svg');
  const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
  line.setAttribute('x1', a.x); line.setAttribute('y1', a.y);
  line.setAttribute('x2', b.x); line.setAttribute('y2', b.y);
  line.setAttribute('class', 'measure-line-el');
  svg.appendChild(line);
  overlay.appendChild(svg);

  const { up, text } = trendReadout(pointA, pointB);

  const label = document.createElement('div');
  label.className = `measure-label ${up ? 'up' : 'down'}`;
  label.style.left = `${(a.x + b.x) / 2}px`;
  label.style.top = `${Math.min(a.y, b.y) - 10}px`;
  label.textContent = text;
  overlay.appendChild(label);
}

function clear() {
  pointA = null;
  pointB = null;
  overlay.innerHTML = '';
}

function onClick(param) {
  if (!active) return;
  const point = pointFromParam(param);
  if (!point) return;
  if (!pointA || pointB) {
    pointA = point;
    pointB = null;
  } else {
    pointB = point;
  }
  render();
}

// Wipes the current measurement but leaves the tool armed, so you can measure again straight away.
export function clearMeasure() { clear(); }

export function toggleMeasure(forceOff) {
  active = forceOff ? false : !active;
  btn.setAttribute('aria-pressed', String(active));
  if (active) {
    chart.subscribeClick(onClick);
    import('./draw.js').then(m => m.turnOffDrawing()); // only one click-to-place tool active at a time
  } else { chart.unsubscribeClick(onClick); clear(); }
}

chart.timeScale().subscribeVisibleTimeRangeChange(render);
new ResizeObserver(render).observe($('chart'));
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && active) toggleMeasure(true); });
btn.addEventListener('click', () => toggleMeasure());
