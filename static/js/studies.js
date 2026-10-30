// Indicators: three configurable moving averages (SMA/EMA, any length, on the chart's bars or on another
// timeframe — e.g. the 200-day SMA drawn on a 5-minute chart), VWAP, Bollinger Bands, RSI and MACD.
// The math is in indicators.js; this module owns the series, the Indicators panel and the extra
// history a higher-timeframe average needs.
import { chart, onRenderIndicators, renderIndicators } from './chart.js';
import { currentFeedQuery } from './data.js';
import { TF_SECONDS, bollinger, ema, htfAverage, macd, rangeFor, resampleWeekly, rsi, sma, tfUsable, vwap, weekKey } from './indicators.js';
import { savePrefs } from './prefs.js';
import { $, alpha, dayKey, isDaily, state, token } from './state.js';

// Series colours live in styles.css (--ma-1 .. --macd) so the Indicators panel swatches match the lines.
export const MA_COLORS = ['--ma-1', '--ma-2', '--ma-3'].map(token);
const [VWAP_C, BB_C, RSI_C, MACD_C] = ['--vwap', '--bb', '--rsi', '--macd'].map(token);
const TF_LABEL = { chart: '', '5m': '5m', '15m': '15m', '1h': '1h', '1d': '1D', '1w': '1W' };
const HTF_TTL_MS = 60000;

const line = (color, extra = {}) => chart.addLineSeries({ color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false, ...extra });
const maSeries = MA_COLORS.map(c => line(c));
const vwapSeries = line(VWAP_C, { lineWidth: 2 });
const bbUpper = line(alpha(BB_C, .8));
const bbMid = line(alpha(BB_C, .5), { lineStyle: 2 });
const bbLower = line(alpha(BB_C, .8));
const rsiSeries = line(RSI_C, { priceScaleId: 'rsi', lineWidth: 1.5 });
rsiSeries.createPriceLine({ price: 70, color: 'rgba(152, 162, 179, .5)', lineStyle: 2, lineWidth: 1, axisLabelVisible: false });
rsiSeries.createPriceLine({ price: 30, color: 'rgba(152, 162, 179, .5)', lineStyle: 2, lineWidth: 1, axisLabelVisible: false });
const macdHist = chart.addHistogramSeries({ priceScaleId: 'macd', priceLineVisible: false, lastValueVisible: false });
const macdLine = line(MACD_C, { priceScaleId: 'macd' });
const macdSignal = line(VWAP_C, { priceScaleId: 'macd' });

// ---------- higher-timeframe history ----------
const htfCache = new Map();   // "symbol|feed|tf|range" -> { at, bars, interval, pending }

function htfBars(tf, len) {
  const fetchTf = tf === '1w' ? '1d' : tf;
  const range = rangeFor(tf, len);
  const key = `${state.currentSymbol}|${currentFeedQuery()}|${fetchTf}|${range}`;
  const hit = htfCache.get(key);
  if (hit && (hit.pending || Date.now() - hit.at < HTF_TTL_MS)) return hit;
  const entry = { at: Date.now(), bars: hit?.bars || null, interval: hit?.interval, pending: true };
  htfCache.set(key, entry);
  fetch(`/api/candles?symbol=${encodeURIComponent(state.currentSymbol)}&interval=${fetchTf}&range=${range}${currentFeedQuery()}`)
    .then(r => (r.ok ? r.json() : Promise.reject()))
    .then(d => { entry.bars = d.candles; entry.interval = d.interval; })
    .catch(() => { /* keep the previous bars, if any; retried after the TTL */ })
    .finally(() => { entry.pending = false; entry.at = Date.now(); renderStudies(); });
  return entry;
}

// One moving average's points, or { note } when it can't be drawn.
function maPoints(cfg) {
  const bars = state.latestCandles;
  const chartTf = state.currentInterval === '1wk' ? '1w' : state.currentInterval;   // studies call weekly '1w'
  if (cfg.tf === 'chart' || cfg.tf === chartTf) return { points: cfg.type === 'ema' ? ema(bars, cfg.len) : sma(bars, cfg.len) };
  if (!tfUsable(cfg.tf, chartTf)) return { points: [], note: `${TF_LABEL[cfg.tf]} is finer than the chart's bars` };
  const fetchTf = cfg.tf === '1w' ? '1d' : cfg.tf;
  const h = htfBars(cfg.tf, cfg.len);
  if (!h.bars) return { points: [], note: h.pending ? 'loading…' : 'history unavailable' };
  if (h.interval !== fetchTf) return { points: [], note: `not enough ${TF_LABEL[cfg.tf]} history` };
  const htf = cfg.tf === '1w' ? resampleWeekly(h.bars) : h.bars;
  return { points: htfAverage(bars, htf, cfg.len, cfg.type, TF_SECONDS[cfg.tf], cfg.tf === '1w' ? weekKey : null) };
}

// ---------- render ----------
const legendEl = $('study-legend');
const fmt = (v) => (v === undefined || v === null ? '–' : v.toFixed(2));

export function renderStudies() {
  const s = state.studies;
  const bars = state.latestCandles;
  const intraday = !isDaily(state.currentInterval);
  const items = [];

  s.ma.forEach((cfg, i) => {
    const r = cfg.on ? maPoints(cfg) : { points: [] };
    maSeries[i].setData(r.points);
    if (cfg.on) items.push({ color: MA_COLORS[i], label: `${cfg.type.toUpperCase()} ${cfg.len}${cfg.tf !== 'chart' ? ` · ${TF_LABEL[cfg.tf]}` : ''}`, value: r.note || fmt(r.points.at(-1)?.value) });
  });

  const vw = s.vwap && intraday ? vwap(bars, dayKey) : [];
  vwapSeries.setData(vw);
  if (s.vwap) items.push({ color: VWAP_C, label: 'VWAP', value: !intraday ? 'intraday only' : vw.length ? fmt(vw.at(-1).value) : 'no volume' });

  const bb = s.bb ? bollinger(bars, 20, 2) : { upper: [], mid: [], lower: [] };
  bbUpper.setData(bb.upper); bbMid.setData(bb.mid); bbLower.setData(bb.lower);
  if (s.bb) items.push({ color: BB_C, label: 'BB 20, 2', value: `${fmt(bb.upper.at(-1)?.value)} / ${fmt(bb.lower.at(-1)?.value)}` });

  const r = s.rsi ? rsi(bars, 14) : [];
  rsiSeries.setData(r);
  const m = s.macd ? macd(bars) : { macd: [], signal: [], hist: [] };
  macdLine.setData(m.macd);
  macdSignal.setData(m.signal);
  macdHist.setData(m.hist.map(p => ({ ...p, color: p.value >= 0 ? 'rgba(38, 166, 154, .5)' : 'rgba(239, 83, 80, .5)' })));

  legendEl.innerHTML = items.map(it => `<span><i style="background:${it.color}"></i>${it.label} <b class="num">${it.value}</b></span>`).join('');
  oscLabel('osc-rsi', s.rsi, `RSI 14 <b class="num">${fmt(r.at(-1)?.value)}</b>`);
  oscLabel('osc-macd', s.macd, `MACD 12 26 9 <b class="num">${fmt(m.macd.at(-1)?.value)}</b> <span class="faint">signal</span> <b class="num">${fmt(m.signal.at(-1)?.value)}</b>`);
  const count = s.ma.filter(x => x.on).length + ['vwap', 'bb', 'rsi', 'macd'].filter(k => s[k]).length;
  $('ind-count').textContent = count ? String(count) : '';
}

// Each oscillator band gets a caption at its top edge (overlay scales draw no axis of their own).
let lastBands = null;
function oscLabel(id, on, html) {
  const el = $(id);
  el.hidden = !on;
  if (!on) return;
  el.innerHTML = html;
  const band = lastBands && lastBands[id === 'osc-rsi' ? 'rsi' : 'macd'];
  if (band) el.style.top = `calc(${(band.top - 0.02) * 100}% + 2px)`;
}

onRenderIndicators((bands) => { lastBands = bands; renderStudies(); });

// ---------- the Indicators panel ----------
const panel = $('ind-panel');
const btn = $('ind-btn');

function syncPanel() {
  const s = state.studies;
  panel.querySelectorAll('[data-ma]').forEach(row => {
    const cfg = s.ma[+row.dataset.ma];
    row.querySelector('[name=on]').checked = cfg.on;
    row.querySelector('[name=type]').value = cfg.type;
    row.querySelector('[name=len]').value = cfg.len;
    row.querySelector('[name=tf]').value = cfg.tf;
  });
  for (const k of ['vwap', 'bb', 'rsi', 'macd']) panel.querySelector(`[name=${k}]`).checked = s[k];
}

function readPanel() {
  const s = state.studies;
  panel.querySelectorAll('[data-ma]').forEach(row => {
    const cfg = s.ma[+row.dataset.ma];
    cfg.on = row.querySelector('[name=on]').checked;
    cfg.type = row.querySelector('[name=type]').value === 'ema' ? 'ema' : 'sma';
    const len = Math.round(Number(row.querySelector('[name=len]').value));
    if (len >= 1 && len <= 1000) cfg.len = len;
    cfg.tf = row.querySelector('[name=tf]').value;
  });
  for (const k of ['vwap', 'bb', 'rsi', 'macd']) s[k] = panel.querySelector(`[name=${k}]`).checked;
}

function setOpen(open) {
  panel.hidden = !open;
  btn.setAttribute('aria-expanded', String(open));
  if (open) syncPanel();
}

btn.addEventListener('click', () => setOpen(panel.hidden));
document.addEventListener('mousedown', (e) => { if (!panel.hidden && !e.target.closest('.ind-wrap')) setOpen(false); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !panel.hidden) { setOpen(false); btn.focus(); } });
panel.addEventListener('change', () => {
  readPanel();
  renderIndicators();     // re-lays out the bands too: RSI/MACD on or off changes the price area
  savePrefs();
});

// Restore saved settings (and the old SMA 20/50/200 checkboxes from before this panel existed).
export function restoreStudies(p) {
  const s = state.studies;
  if (p.studies && Array.isArray(p.studies.ma)) {
    p.studies.ma.slice(0, 3).forEach((m, i) => {
      if (!m) return;
      s.ma[i] = {
        on: !!m.on, type: m.type === 'ema' ? 'ema' : 'sma',
        len: Number.isInteger(m.len) && m.len >= 1 && m.len <= 1000 ? m.len : s.ma[i].len,
        tf: m.tf in TF_LABEL ? m.tf : 'chart',
      };
    });
    for (const k of ['vwap', 'bb', 'rsi', 'macd']) s[k] = !!p.studies[k];
  } else {
    ['sma20', 'sma50', 'sma200'].forEach((k, i) => { if (typeof p[k] === 'boolean') s.ma[i].on = p[k]; });
  }
}
