// Small inline-SVG charts for the Insights tabs: grouped bars, lines and a labelled scatter. Pure string
// builders — no DOM, no app state — unit-tested in Node (tests/frontend/minichart.test.mjs). Colours are CSS
// custom properties (var(--up)), so the charts follow the theme without a redraw.
import { esc } from './format.js';

export const scale = (lo, hi, a, b) => { const span = hi - lo || 1; return (v) => a + ((v - lo) / span) * (b - a); };

// Lowest/highest finite value across every series (and 0, so bars and spreads always show their zero line).
export function extent(series, withZero = true) {
  const vals = series.flatMap(s => s.values).filter(Number.isFinite);
  if (withZero) vals.push(0);
  return vals.length ? [Math.min(...vals), Math.max(...vals)] : [0, 1];
}

// Axis labels stay short: 2.58L / 1.2Cr (Indian units), 12.5k, 3.98.
export function fmtTick(v) {
  const a = Math.abs(v);
  if (a >= 1e7) return `${+(v / 1e7).toFixed(2)}Cr`;
  if (a >= 1e5) return `${+(v / 1e5).toFixed(2)}L`;
  if (a >= 1e4) return `${+(v / 1e3).toFixed(1)}k`;
  if (a >= 100) return String(Math.round(v));
  return String(+v.toFixed(2));
}
const text = (x, y, s, anchor = 'end') => `<text x="${x}" y="${y}" text-anchor="${anchor}" class="mc-t">${esc(s)}</text>`;

function frame({ w, h, pad, lo, hi, labels, y }) {
  const ticks = [...new Set([lo, hi, lo < 0 && hi > 0 ? 0 : null].filter(v => v !== null))];
  const grid = ticks.map(v => `<line x1="${pad}" x2="${w - 4}" y1="${y(v)}" y2="${y(v)}" class="mc-g${v === 0 ? ' mc-z' : ''}"/>${text(pad - 4, y(v) + 3, fmtTick(v))}`).join('');
  const n = labels.length;
  const xs = n ? [...new Set([0, Math.floor((n - 1) / 2), n - 1])] : [];
  const xl = xs.map(i => text(pad + ((i + 0.5) * (w - pad - 4)) / n, h - 4, labels[i], i === 0 && n > 1 ? 'start' : i === n - 1 && n > 1 ? 'end' : 'middle')).join('');
  return grid + xl;
}

// Grouped bars around zero. series: [{ name, values, color }], each value aligned with labels.
export function bars({ labels, series, w = 640, h = 180, pad = 52 }) {
  const [lo, hi] = extent(series);
  const y = scale(lo, hi, h - 18, 6);
  const slot = (w - pad - 4) / Math.max(labels.length, 1);
  const bw = Math.min(36, Math.max(1, (slot * 0.8) / series.length));
  const inset = (slot - bw * series.length) / 2;
  const rects = series.map((s, k) => s.values.map((v, i) => {
    if (!Number.isFinite(v)) return '';
    const x = pad + i * slot + inset + k * bw;
    const top = Math.min(y(v), y(0));
    const tip = `${labels[i]} · ${s.name}: ${fmtTick(v)}`;
    return `<rect x="${x.toFixed(1)}" y="${top.toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(0.5, Math.abs(y(v) - y(0))).toFixed(1)}" fill="${s.color(v)}"><title>${esc(tip)}</title></rect>`;
  }).join('')).join('');
  return `<svg class="mc" viewBox="0 0 ${w} ${h}" role="img">${frame({ w, h, pad, lo, hi, labels, y })}${rects}</svg>`;
}

// Lines on a shared x (index). Nulls break the line. series: [{ name, values, color }].
export function lines({ labels, series, w = 640, h = 180, pad = 52, withZero = false }) {
  const [lo, hi] = extent(series, withZero);
  const y = scale(lo, hi, h - 18, 6);
  const slot = (w - pad - 4) / Math.max(labels.length, 1);
  const x = (i) => pad + (i + 0.5) * slot;
  const paths = series.map((s) => {
    let d = '', pen = 'M';
    s.values.forEach((v, i) => {
      if (!Number.isFinite(v)) { pen = 'M'; return; }
      d += `${pen}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
      pen = 'L';
    });
    return `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="1.6"><title>${esc(s.name)}</title></path>`;
  }).join('');
  return `<svg class="mc" viewBox="0 0 ${w} ${h}" role="img">${frame({ w, h, pad, lo, hi, labels, y })}${paths}</svg>`;
}

// Labelled points with optional trails, split into quadrants at (cx, cy) — the RRG layout.
// points: [{ label, x, y, trail: [[x, y], ...], color }]
export function scatter({ points, cx, cy, w = 640, h = 420, pad = 44, quadrants = [] }) {
  const xsAll = points.flatMap(p => [p.x, ...(p.trail || []).map(t => t[0])]).concat(cx);
  const ysAll = points.flatMap(p => [p.y, ...(p.trail || []).map(t => t[1])]).concat(cy);
  const m = (lo, hi) => [lo - (hi - lo) * 0.08 - 0.01, hi + (hi - lo) * 0.08 + 0.01];
  const [x0, x1] = m(Math.min(...xsAll), Math.max(...xsAll));
  const [y0, y1] = m(Math.min(...ysAll), Math.max(...ysAll));
  const X = scale(x0, x1, pad, w - 8), Y = scale(y0, y1, h - 20, 8);
  const cross = `<line x1="${X(cx)}" x2="${X(cx)}" y1="8" y2="${h - 20}" class="mc-g mc-z"/><line x1="${pad}" x2="${w - 8}" y1="${Y(cy)}" y2="${Y(cy)}" class="mc-g mc-z"/>`;
  const quads = quadrants.map(([label, qx, qy]) => text(qx ? w - 12 : pad + 4, qy ? 20 : h - 26, label, qx ? 'end' : 'start')).join('');
  const dots = points.map((p) => {
    const trail = (p.trail || []).length ? `<path d="${p.trail.map((t, i) => `${i ? 'L' : 'M'}${X(t[0]).toFixed(1)},${Y(t[1]).toFixed(1)}`).join('')}L${X(p.x).toFixed(1)},${Y(p.y).toFixed(1)}" fill="none" stroke="${p.color}" stroke-opacity=".5" stroke-width="1.3"/>` : '';
    return `${trail}<circle cx="${X(p.x).toFixed(1)}" cy="${Y(p.y).toFixed(1)}" r="4.5" fill="${p.color}"><title>${esc(`${p.label}: ${p.x.toFixed(2)}, ${p.y.toFixed(2)}`)}</title></circle>${text(X(p.x) + 7, Y(p.y) - 6, p.label, 'start')}`;
  }).join('');
  return `<svg class="mc" viewBox="0 0 ${w} ${h}" role="img">${cross}${quads}${dots}</svg>`;
}

export const legend = (series) => `<div class="mc-legend">${series.map(s => `<span><i style="background:${typeof s.color === 'function' ? s.color(1) : s.color}"></i>${esc(s.name)}</span>`).join('')}</div>`;

// Diverging background for a heatmap cell: green for positive, red for negative, opacity by |v| / max.
export function heat(v, max) {
  if (!Number.isFinite(v) || !max) return '';
  const a = Math.min(1, Math.abs(v) / max) * 0.55;
  return `background: color-mix(in srgb, var(${v >= 0 ? '--up' : '--down'}) ${(a * 100).toFixed(0)}%, transparent)`;
}

export const signColor = (v) => (v >= 0 ? 'var(--up)' : 'var(--down)');

// A plain table. cols: [{ key, label, title?, fmt?(v, row), cls?(v, row) }]; a row with chartSymbol becomes
// clickable (insights.js charts it). Sorted by `sort` = { key, dir } when given.
export function table(cols, rows, sort = null) {
  const list = sort ? [...rows].sort((a, b) => {
    const x = a[sort.key], y = b[sort.key];
    if (x === y) return 0;
    if (x === null || x === undefined) return 1;
    if (y === null || y === undefined) return -1;
    return (x < y ? -1 : 1) * sort.dir;
  }) : rows;
  const head = cols.map(c => `<th${c.title ? ` title="${esc(c.title)}"` : ''}><button type="button" class="th-sort" data-sort="${esc(c.key)}"${sort && sort.key === c.key ? ` data-dir="${sort.dir > 0 ? 'asc' : 'desc'}"` : ''}>${esc(c.label)}</button></th>`).join('');
  const body = list.map(r => `<tr${r.chartSymbol ? ` data-symbol="${esc(r.chartSymbol)}" tabindex="0"` : ''}>${cols.map(c => {
    const v = r[c.key];
    const shown = c.fmt ? c.fmt(v, r) : v === null || v === undefined ? '–' : esc(v);
    return `<td class="${c.cls ? c.cls(v, r) : ''}">${shown}</td>`;
  }).join('')}</tr>`).join('');
  return `<table class="opt-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

// Click a header to sort by it (again to flip). Returns the new sort for the caller to store.
export const nextSort = (sort, key) => (sort && sort.key === key ? { key, dir: -sort.dir } : { key, dir: -1 });
