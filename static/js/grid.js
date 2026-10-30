// Multi-chart grid: 2, 3 or 4 charts side by side, each with its own bar size. A pane either follows the main
// chart's symbol ("linked", the default: one symbol on several timeframes) or holds its own symbol. Crosshairs
// are synced by time. Each pane reloads every 60 s while the grid is open. Layout is remembered.
import { $, COLORS, dateFmt, dateTimeFmt, isDaily, state, timeFmt, token } from './state.js';

const KEY = 'orazio.grid.v1';
const modal = $('grid-modal');
const host = $('grid-panes');
const INTERVALS = [['1m', '1m'], ['5m', '5m'], ['15m', '15m'], ['1h', '1h'], ['1d', '1D'], ['1wk', '1W']];
const RANGE = { '1m': '1D', '5m': '1W', '15m': '1M', '1h': '3M', '1d': '1Y', '1wk': '5Y' };
let cfg = { n: 4, panes: [{ symbol: '', interval: '5m' }, { symbol: '', interval: '15m' }, { symbol: '', interval: '1h' }, { symbol: '', interval: '1d' }] };
try { const s = JSON.parse(localStorage.getItem(KEY) || 'null'); if (s?.panes?.length === 4) cfg = s; } catch (e) { /* default layout */ }
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(cfg)); } catch (e) { /* not persisted */ } };
let panes = [];   // { chart, series, bars, el }
let timer = null, trigger = null;

const symbolOf = (p) => p.symbol || state.currentSymbol;

function makeChart(el, interval) {
  const chart = LightweightCharts.createChart(el, {
    autoSize: true,
    layout: { background: { color: COLORS.bg }, textColor: COLORS.text, fontFamily: token('--font'), fontSize: 11 },
    grid: { vertLines: { color: COLORS.grid }, horzLines: { color: COLORS.grid } },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    rightPriceScale: { borderColor: COLORS.border },
    timeScale: { borderColor: COLORS.border, timeVisible: !isDaily(interval), tickMarkFormatter: (t) => (isDaily(interval) ? dateFmt : timeFmt).format(new Date(t * 1000)) },
    localization: { timeFormatter: (t) => dateTimeFmt.format(new Date(t * 1000)) + ' IST' },
  });
  const series = chart.addCandlestickSeries({ upColor: COLORS.up, downColor: COLORS.down, borderVisible: false, wickUpColor: COLORS.up, wickDownColor: COLORS.down });
  return { chart, series };
}

async function loadPane(i) {
  const p = cfg.panes[i], pane = panes[i];
  if (!pane) return;
  const sym = symbolOf(p);
  pane.sym = sym;
  pane.el.querySelector('.gp-sym').value = p.symbol;
  pane.el.querySelector('.gp-sym').placeholder = `${state.currentSymbol} (linked)`;
  try {
    const res = await fetch(`/api/candles?symbol=${encodeURIComponent(sym)}&interval=${p.interval}&range=${RANGE[p.interval]}`);
    const d = res.ok ? await res.json() : { candles: [] };
    if (panes[i] !== pane) return;
    pane.bars = d.candles || [];
    pane.series.setData(pane.bars);
    const last = pane.bars.at(-1);
    pane.el.querySelector('.gp-px').textContent = last ? `${sym} ${last.close.toLocaleString('en-IN', { maximumFractionDigits: 2 })}` : 'No data';
    if (!pane.fitted) { pane.chart.timeScale().fitContent(); pane.fitted = true; }
  } catch (e) {
    pane.el.querySelector('.gp-px').textContent = 'Load failed';
  }
}

function build() {
  for (const p of panes) p.chart.remove();
  panes = [];
  host.dataset.n = cfg.n;
  host.innerHTML = cfg.panes.slice(0, cfg.n).map((p, i) => `<div class="gp" data-i="${i}">
    <div class="gp-head"><input class="ins-input gp-sym" aria-label="Pane ${i + 1} symbol (empty = follow the main chart)" value="" placeholder="">
      <select class="select gp-iv" aria-label="Pane ${i + 1} bar size">${INTERVALS.map(([v, l]) => `<option value="${v}"${v === p.interval ? ' selected' : ''}>${l}</option>`).join('')}</select>
      <span class="gp-px"></span></div><div class="gp-chart"></div></div>`).join('');
  host.querySelectorAll('.gp').forEach((el) => {
    const i = +el.dataset.i;
    const { chart, series } = makeChart(el.querySelector('.gp-chart'), cfg.panes[i].interval);
    panes.push({ chart, series, bars: [], el, fitted: false });
    el.querySelector('.gp-sym').addEventListener('change', (e) => { cfg.panes[i].symbol = e.target.value.trim().toUpperCase(); panes[i].fitted = false; save(); loadPane(i); });
    el.querySelector('.gp-iv').addEventListener('change', (e) => { cfg.panes[i].interval = e.target.value; save(); build(); });
  });
  // Crosshair sync by time: each pane shows the bar at or before the hovered moment.
  panes.forEach((src, i) => src.chart.subscribeCrosshairMove((pt) => {
    panes.forEach((dst, j) => {
      if (j === i) return;
      const b = pt.time ? [...dst.bars].reverse().find(x => x.time <= pt.time) : null;
      if (b) dst.chart.setCrosshairPosition(b.close, b.time, dst.series); else dst.chart.clearCrosshairPosition();
    });
  }));
  panes.forEach((_, i) => loadPane(i));
}

function open() {
  trigger = document.activeElement;
  modal.classList.add('open');
  $('grid-n').value = String(cfg.n);
  build();
  clearInterval(timer);
  timer = setInterval(() => { if (!document.hidden) panes.forEach((_, i) => loadPane(i)); }, 60000);
}

function close() {
  modal.classList.remove('open');
  clearInterval(timer);
  for (const p of panes) p.chart.remove();
  panes = [];
  host.innerHTML = '';
  trigger?.focus();
}

$('grid-btn').addEventListener('click', open);
$('grid-close').addEventListener('click', close);
$('grid-n').addEventListener('change', (e) => { cfg.n = +e.target.value; save(); build(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && modal.classList.contains('open')) close(); });
// Linked panes follow the main chart's symbol.
document.addEventListener('candles:loaded', () => {
  if (!modal.classList.contains('open')) return;
  cfg.panes.slice(0, cfg.n).forEach((p, i) => { if (!p.symbol && panes[i] && panes[i].sym !== state.currentSymbol) { panes[i].fitted = false; loadPane(i); } });
});
