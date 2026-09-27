import { $, COLORS, INTERVAL_LABEL, alpha, dateFmt, dateTimeFmt, dayKey, displayName, esc, state, timeFmt, token } from './state.js';

export const chart = LightweightCharts.createChart(document.getElementById('chart'), {
  autoSize: true,
  layout: { background: { color: COLORS.bg }, textColor: COLORS.text, fontFamily: token('--font'), fontSize: 12 },
  grid: { vertLines: { color: COLORS.grid }, horzLines: { color: COLORS.grid } },
  crosshair: {
    mode: LightweightCharts.CrosshairMode.Normal,
    vertLine: { color: COLORS.crosshair, labelBackgroundColor: token('--bg-3') },
    horzLine: { color: COLORS.crosshair, labelBackgroundColor: token('--bg-3') },
  },
  rightPriceScale: { autoScale: true, borderColor: COLORS.border, scaleMargins: { top: 0.08, bottom: 0.35 } },
  handleScroll: { mouseWheel: true },
  handleScale: { mouseWheel: true },
  watermark: { visible: false, color: 'rgba(230, 234, 242, 0.05)', fontSize: 56, horzAlign: 'center', vertAlign: 'center', text: '' },
  timeScale: {
    borderColor: COLORS.border,
    timeVisible: true,
    secondsVisible: false,
    // Default minBarSpacing (0.5px) caps how far fitContent() can zoom out — past
    // ~2300 bars on a ~1150px chart it silently clamps and anchors to the most recent
    // data instead of showing everything, with no visual indication. "All" (4600+
    // daily bars) hit this. A tiny minimum lets fitContent genuinely fit all of it.
    minBarSpacing: 0.05,
    tickMarkFormatter: (time) => state.currentInterval === '1d'
      ? dateFmt.format(new Date(time * 1000))
      : timeFmt.format(new Date(time * 1000)),
  },
  localization: {
    timeFormatter: (time) => dateTimeFmt.format(new Date(time * 1000)) + ' IST',
  },
});

export const candleSeries = chart.addCandlestickSeries({
  upColor: COLORS.up, downColor: COLORS.down, borderVisible: false,
  wickUpColor: COLORS.up, wickDownColor: COLORS.down,
});
export const barSeries = chart.addBarSeries({ upColor: COLORS.up, downColor: COLORS.down, visible: false });
export const lineSeries = chart.addLineSeries({ color: COLORS.accent, lineWidth: 2, visible: false });
export const areaSeries = chart.addAreaSeries({
  lineColor: COLORS.accent, topColor: alpha(COLORS.accent, 0.35), bottomColor: alpha(COLORS.accent, 0),
  visible: false,
});

export const volumeSeries = chart.addHistogramSeries({
  priceFormat: { type: 'volume' }, priceScaleId: '', scaleMargins: { top: 0.93, bottom: 0 },
  priceLineVisible: false, lastValueVisible: false,
});
export const sma20Series = chart.addLineSeries({ color: '#f0b90b', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
export const sma50Series = chart.addLineSeries({ color: '#7e57c2', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
// Blue is otherwise unused now that the Line/Area price series itself is colored by
// up/down direction (see applyLineAreaColor below) rather than a fixed accent color.
export const sma200Series = chart.addLineSeries({ color: '#4c8dff', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });

export const priceSeriesByStyle = { candle: candleSeries, bar: barSeries, line: lineSeries, area: areaSeries };

export function applyStyle(style) {
  state.currentStyle = style;
  for (const [key, series] of Object.entries(priceSeriesByStyle)) {
    series.applyOptions({ visible: key === style });
  }
  syncStyleData();
  updateLegend(null);
}

export function computeDayBoundaries() {
  state.dayBoundaryTimes = new Set();
  if (state.currentInterval === '1d' || state.latestCandles.length < 2) { renderDayLines(); return; }
  let prevDay = dayKey(state.latestCandles[0].time);
  for (let i = 1; i < state.latestCandles.length; i++) {
    const dk = dayKey(state.latestCandles[i].time);
    if (dk !== prevDay) state.dayBoundaryTimes.add(state.latestCandles[i].time);
    prevDay = dk;
  }
  renderDayLines();
}

// Thin dotted vertical line at each session boundary — a DOM overlay (Lightweight
// Charts v4 has no primitives API for custom drawings), repositioned on every pan/zoom.
const dayLinesEl = $('day-lines');
export function renderDayLines() {
  dayLinesEl.innerHTML = '';
  if (state.currentInterval === '1d' || !state.dayBoundaryTimes.size) return;
  const ts = chart.timeScale();
  dayLinesEl.style.setProperty('--axis-h', `${ts.height ? ts.height() : 26}px`);
  for (const t of state.dayBoundaryTimes) {
    const x = ts.timeToCoordinate(t);
    if (x === null) continue;
    const div = document.createElement('div');
    div.className = 'day-line';
    div.style.left = `${x}px`;
    dayLinesEl.appendChild(div);
  }
}
chart.timeScale().subscribeVisibleTimeRangeChange(renderDayLines);
new ResizeObserver(renderDayLines).observe($('chart'));

export function syncStyleData() {
  // Hidden series must be emptied: the time scale is built from EVERY series' data, so
  // stale bars left behind by a previous style stretch the axis and break fitContent().
  for (const [key, series] of Object.entries(priceSeriesByStyle)) {
    if (key !== state.currentStyle) series.setData([]);
  }
  if (state.currentStyle === 'candle') candleSeries.setData(state.latestCandles);
  else if (state.currentStyle === 'bar') barSeries.setData(state.latestCandles);
  else {
    const closeData = state.latestCandles.map(c => ({ time: c.time, value: c.close }));
    if (state.currentStyle === 'line') lineSeries.setData(closeData);
    else areaSeries.setData(closeData);
  }
}

function sma(data, period) {
  const out = [];
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) continue;
    let sum = 0;
    for (let j = i - period + 1; j <= i; j++) sum += data[j].close;
    out.push({ time: data[i].time, value: sum / period });
  }
  return out;
}

export function renderIndicators() {
  sma20Series.setData($('sma20').checked ? sma(state.latestCandles, 20) : []);
  sma50Series.setData($('sma50').checked ? sma(state.latestCandles, 50) : []);
  sma200Series.setData($('sma200').checked ? sma(state.latestCandles, 200) : []);
  volumeSeries.setData($('vol').checked ? state.latestCandles.map(c => ({
    time: c.time, value: c.volume,
    color: c.close >= c.open ? COLORS.volUp : COLORS.volDown,
  })) : []);
}

// Line/Area styles have no per-bar up/down of their own (unlike Candle/Bar), so they're
// colored by the session's own direction — current price vs. previous close — the same
// comparison the price chip already uses. Called from pollQuote() on every live tick, and
// from applyThemeToChart() to reapply the same direction against a new theme's palette.
export function applyLineAreaColor(isUp) {
  const changed = state.lineAreaUp !== isUp;
  state.lineAreaUp = isUp;
  const color = isUp ? COLORS.up : COLORS.down;
  lineSeries.applyOptions({ color });
  areaSeries.applyOptions({ lineColor: color, topColor: alpha(color, 0.35), bottomColor: alpha(color, 0) });
  if (changed && (state.currentStyle === 'line' || state.currentStyle === 'area')) updateLegend(null);
}

export function updateWatermark() {
  chart.applyOptions({ watermark: { visible: !!state.resolvedSymbol, text: displayName(state.currentSymbol) } });
}

// OHLC readout: the last bar by default, the hovered bar while the crosshair is on the chart.
const legendEl = $('legend');
export function updateLegend(bar) {
  const b = bar || state.latestCandles[state.latestCandles.length - 1];
  if (!b) { legendEl.innerHTML = ''; return; }
  const head = `<span class="lg-sym">${esc(displayName(state.currentSymbol))}</span><span class="lg-tag">${INTERVAL_LABEL[state.currentInterval] || esc(state.currentInterval)}</span>`;
  const f = (v) => v.toFixed(2);
  if (b.open === undefined || state.currentStyle === 'line' || state.currentStyle === 'area') {
    const lineCls = state.lineAreaUp === false ? 'down' : state.lineAreaUp === true ? 'up' : '';
    legendEl.innerHTML = `${head}<span><span class="lg-k">Close</span><span class="num ${lineCls}">${f(b.close ?? b.value)}</span></span>`;
    return;
  }
  const cls = b.close >= b.open ? 'up' : 'down';
  legendEl.innerHTML = head + [['Open', b.open], ['High', b.high], ['Low', b.low], ['Close', b.close]]
    .map(([k, v]) => `<span><span class="lg-k">${k}</span><span class="num ${cls}">${f(v)}</span></span>`).join('');
}
chart.subscribeCrosshairMove((param) => {
  const d = param.time ? param.seriesData.get(priceSeriesByStyle[state.currentStyle]) : null;
  updateLegend(d || null);
});

// Chart construction above only sets colors once, at module load. Lightweight Charts
// doesn't watch CSS variables, so a theme switch must explicitly reapply every color —
// `COLORS` itself is refreshed first (see state.js refreshColors()), this just pushes it.
export function applyThemeToChart() {
  chart.applyOptions({
    layout: { background: { color: COLORS.bg }, textColor: COLORS.text },
    grid: { vertLines: { color: COLORS.grid }, horzLines: { color: COLORS.grid } },
    crosshair: {
      vertLine: { color: COLORS.crosshair, labelBackgroundColor: token('--bg-3') },
      horzLine: { color: COLORS.crosshair, labelBackgroundColor: token('--bg-3') },
    },
    rightPriceScale: { borderColor: COLORS.border },
    timeScale: { borderColor: COLORS.border },
  });
  candleSeries.applyOptions({ upColor: COLORS.up, downColor: COLORS.down, wickUpColor: COLORS.up, wickDownColor: COLORS.down });
  barSeries.applyOptions({ upColor: COLORS.up, downColor: COLORS.down });
  if (state.lineAreaUp !== null) applyLineAreaColor(state.lineAreaUp);
  else {
    lineSeries.applyOptions({ color: COLORS.accent });
    areaSeries.applyOptions({ lineColor: COLORS.accent, topColor: alpha(COLORS.accent, 0.35), bottomColor: alpha(COLORS.accent, 0) });
  }
  renderIndicators();
}

// fitContent() butts the first candle against the left edge (half-clipped) and the newest
// one against the price axis; a little air on both sides reads as finished.
export function fitWithPadding() {
  // Set the padded range directly: reading the range back right after fitContent()
  // returns the PREVIOUS view, and re-applying that would undo the fit.
  chart.timeScale().setVisibleLogicalRange({ from: -1, to: state.latestCandles.length - 1 + 4 });
}
