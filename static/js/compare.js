// Compare: a second chart beside the main one for any other symbol (index, stock, commodity, crypto).
// It follows the main chart's bar interval and history range, scrolls and zooms with it by TIME (so
// NIFTY next to SPX shows the same wall-clock window even though their sessions differ), mirrors the
// crosshair, and keeps its newest bar live from its own quote stream. The header compares both
// symbols' % change over the window currently on screen.
import { chart } from './chart.js';
import { switchSymbol } from './symbol.js';
import { feedQuery } from './feed-policy.js';
import { combineBars, formulaText, parseFormula } from './formula.js';
import { heikinAshi } from './indicators.js';
import { attachSearch, pickTyped } from './search-box.js';
import { $, COLORS, INTERVAL_SECONDS, alpha, dateFmt, dateTimeFmt, displayName, esc, isDaily, state, timeFmt, token } from './state.js';

const KEY = 'orazio.compare.v1';
const wrap = $('compare-wrap');
const btn = $('compare-btn');
const input = $('compare-input');
const styleSel = $('compare-style');

let symbol = 'SENSEX';
let style = 'candle';   // candle | bar | ha | line | area | baseline
let bars = [];
let loadedFor = '';
let source = null;
let generation = 0;
// Which chart leads the scroll/zoom sync: the one the user last touched. Only the leader's range changes
// are copied to the other, so a chart re-fitting itself after new data (or echoing a range we just set
// on it) can never drag the leader around. Loading data hands the lead back to the main chart.
let driver = 'main';
let cmp = null;      // the second chart, created on first open
let series = null;

function save() {
  try { localStorage.setItem(KEY, JSON.stringify({ open: !wrap.hidden, symbol, style })); } catch (e) { /* not persisted */ }
}

function create() {
  cmp = LightweightCharts.createChart($('compare-chart'), {
    autoSize: true,
    layout: { background: { color: COLORS.bg }, textColor: COLORS.text, fontFamily: token('--font'), fontSize: 12 },
    grid: { vertLines: { color: COLORS.grid }, horzLines: { color: COLORS.grid } },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    rightPriceScale: { borderColor: COLORS.border, scaleMargins: { top: 0.08, bottom: 0.08 } },
    timeScale: {
      borderColor: COLORS.border, timeVisible: true, secondsVisible: false, minBarSpacing: 0.05,
      tickMarkFormatter: (t) => (isDaily(state.currentInterval) ? dateFmt : timeFmt).format(new Date(t * 1000)),
    },
    localization: { timeFormatter: (t) => dateTimeFmt.format(new Date(t * 1000)) + ' IST' },
  });
  makeSeries();

  // Pan/zoom either chart and the other follows, matched by time.
  const follow = (from, to) => (range) => {
    if (wrap.hidden || driver !== from || !range) return;
    try { to.timeScale().setVisibleRange(range); } catch (e) { /* the other chart has no data in that window yet */ }
    renderPerf();
  };
  chart.timeScale().subscribeVisibleTimeRangeChange(follow('main', cmp));
  cmp.timeScale().subscribeVisibleTimeRangeChange(follow('cmp', chart));
  for (const [id, who] of [['chart-wrap', 'main'], ['compare-chart', 'cmp']]) {
    for (const ev of ['pointerdown', 'wheel', 'touchstart']) $(id).addEventListener(ev, () => { driver = who; }, { passive: true });
  }

  // Crosshair mirror: hover one chart, the other shows the bar at (or just before) the same moment.
  chart.subscribeCrosshairMove((p) => {
    if (wrap.hidden || !cmp.setCrosshairPosition) return;
    const b = p.time ? barAtOrBefore(bars, p.time) : null;
    if (b) cmp.setCrosshairPosition(b.close, b.time, series); else cmp.clearCrosshairPosition();
  });
  cmp.subscribeCrosshairMove((p) => {
    renderLegend(p.time ? barAtOrBefore(bars, p.time) : null);
  });
}

// One series at a time, rebuilt when the style (or theme) changes. Legend/crosshair still read raw OHLC.
function makeSeries() {
  if (series) cmp.removeSeries(series);
  const ohlc = { upColor: COLORS.up, downColor: COLORS.down, borderVisible: false, wickUpColor: COLORS.up, wickDownColor: COLORS.down };
  series = style === 'bar' ? cmp.addBarSeries({ upColor: COLORS.up, downColor: COLORS.down })
    : style === 'line' ? cmp.addLineSeries({ color: COLORS.accent, lineWidth: 2 })
    : style === 'area' ? cmp.addAreaSeries({ lineColor: COLORS.accent, topColor: alpha(COLORS.accent, 0.35), bottomColor: alpha(COLORS.accent, 0) })
    : style === 'baseline' ? cmp.addBaselineSeries({
      topLineColor: COLORS.up, topFillColor1: alpha(COLORS.up, 0.3), topFillColor2: alpha(COLORS.up, 0),
      bottomLineColor: COLORS.down, bottomFillColor1: alpha(COLORS.down, 0), bottomFillColor2: alpha(COLORS.down, 0.3),
    })
    : cmp.addCandlestickSeries(ohlc);
  setSeriesData();
}

const isOhlc = () => style === 'candle' || style === 'bar' || style === 'ha';
const point = (b) => (isOhlc() ? b : { time: b.time, value: b.close });

function setSeriesData() {
  // Baseline splits green/red at the first loaded bar's close: above = up since the window began.
  if (style === 'baseline' && bars.length) series.applyOptions({ baseValue: { type: 'price', price: bars[0].close } });
  series.setData(style === 'ha' ? heikinAshi(bars) : bars.map(point));
}

export function barAtOrBefore(list, t) {
  let lo = 0, hi = list.length - 1, hit = null;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (list[mid].time <= t) { hit = list[mid]; lo = mid + 1; } else hi = mid - 1;
  }
  return hit;
}

// % change from the first to the last bar inside [from, to].
function windowChange(list, from, to) {
  const inside = list.filter(b => b.time >= from && b.time <= to);
  if (inside.length < 2) return null;
  return (inside.at(-1).close / inside[0].open - 1) * 100;
}

function renderPerf() {
  const r = chart.timeScale().getVisibleRange();
  const el = $('compare-perf');
  if (!r) { el.innerHTML = ''; return; }
  const fmt = (name, v) => `<span>${esc(name)} <b class="num ${v === null ? '' : v >= 0 ? 'up' : 'down'}">${v === null ? '–' : `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`}</b></span>`;
  el.innerHTML = 'On screen: ' + fmt(displayName(state.currentSymbol), windowChange(state.latestCandles, r.from, r.to)) + fmt(displayName(symbol), windowChange(bars, r.from, r.to));
}

function renderLegend(bar) {
  const b = bar || bars.at(-1);
  const el = $('compare-legend');
  if (!b) { el.innerHTML = ''; return; }
  const cls = b.close >= b.open ? 'up' : 'down';
  el.innerHTML = [['O', b.open], ['H', b.high], ['L', b.low], ['C', b.close]]
    .map(([k, v]) => `<span><span class="lg-k">${k}</span><span class="num ${cls}">${v.toFixed(2)}</span></span>`).join('');
}

const feedFor = (sym) => feedQuery({ symbol: sym, commodities: state.CONFIG.commodities, feed: state.commodityFeed });

async function fetchCandles(sym) {
  const res = await fetch(`/api/candles?symbol=${encodeURIComponent(sym)}&interval=${state.currentInterval}&range=${state.currentRange}${feedFor(sym)}`);
  if (!res.ok) throw new Error(res.status === 400 ? `${sym} is not a valid symbol` : `HTTP ${res.status}`);
  return res.json();
}

async function load() {
  if (wrap.hidden) return;
  const my = ++generation;
  driver = 'main';
  const key = `${symbol}|${state.currentInterval}|${state.currentRange}`;
  $('compare-note').textContent = loadedFor === key ? '' : 'Loading…';
  try {
    const f = parseFormula(symbol);
    let d;
    if (f) {
      const [da, db] = await Promise.all([fetchCandles(f.a), fetchCandles(f.b)]);
      d = { interval: da.interval, candles: combineBars(da.candles || [], db.candles || [], f.op, isDaily(da.interval)) };
    } else d = await fetchCandles(symbol);
    if (my !== generation) return;
    bars = d.candles || [];
    // A bare ticker saved before search resolution existed (ADANIENT) has no data: resolve it once.
    if (!f && !bars.length && /^[A-Z0-9&-]+$/.test(symbol)) {
      const items = await fetch(`/api/search?q=${encodeURIComponent(symbol)}`).then(r => (r.ok ? r.json() : [])).catch(() => []);
      const picked = pickTyped(symbol, items, state.CONFIG.quickIndices || []);
      if (picked !== symbol && my === generation) { input.value = picked; choose(picked); return; }
    }
    setSeriesData();
    loadedFor = key;
    $('compare-note').textContent = !bars.length ? `No data for ${symbol} in this range`
      : d.interval !== state.currentInterval ? `${symbol} has no ${state.currentInterval} bars here — showing ${d.interval}` : '';
    const r = chart.timeScale().getVisibleRange();
    try { if (r) cmp.timeScale().setVisibleRange(r); else cmp.timeScale().fitContent(); } catch (e) { cmp.timeScale().fitContent(); }
    renderLegend(null);
    renderPerf();
  } catch (e) {
    if (my === generation) $('compare-note').textContent = `Couldn't load ${symbol}: ${e.message}`;
  }
  openStream();
}

// Live quotes fold into the newest bar (and open a new one when the clock crosses a bar boundary).
function openStream() {
  source?.close();
  source = null;
  // ponytail: a formula has no quote stream; it refreshes with the main chart's once-a-minute reload.
  if (wrap.hidden || typeof EventSource === 'undefined' || parseFormula(symbol)) return;
  const sym = symbol;
  source = new EventSource(`/api/stream/quote?symbol=${encodeURIComponent(sym)}${feedFor(sym)}`);
  source.addEventListener('quote', (e) => {
    if (sym !== symbol || !bars.length) return;
    const q = JSON.parse(e.data);
    const up = q.change >= 0;
    $('compare-price').innerHTML = `<span class="num">${q.price.toFixed(2)}</span> <span class="chip ${up ? 'up' : 'down'}">${up ? '+' : ''}${q.changePercent.toFixed(2)}%</span>`;
    const last = bars.at(-1);
    const step = INTERVAL_SECONDS[state.currentInterval];
    const t = q.marketTime || q.time;
    if (!step || !t || t - last.time > 2 * step + 240) return;     // stale quote or daily bars: leave the bars alone
    const bucket = last.time + Math.floor((t - last.time) / step) * step;
    if (bucket > last.time) bars.push({ time: bucket, open: q.price, high: q.price, low: q.price, close: q.price, volume: 0 });
    else bars[bars.length - 1] = { ...last, close: q.price, high: Math.max(last.high, q.price), low: Math.min(last.low, q.price) };
    // ponytail: HA re-derives the whole chain per quote (O(n), fine for a few thousand bars); cache the HA tail if it lags.
    if (style === 'ha') series.setData(heikinAshi(bars)); else series.update(point(bars.at(-1)));
    renderLegend(null);
  });
}

function setOpen(open) {
  wrap.hidden = !open;
  btn.setAttribute('aria-pressed', String(open));
  document.querySelector('.charts').classList.toggle('split', open);
  if (open) {
    if (!cmp) create();
    input.value = displayName(symbol);
    $('compare-title').textContent = displayName(symbol);
    load();
  } else {
    source?.close();
    source = null;
  }
  save();
}

function choose(picked) {
  const s = picked.trim().toUpperCase();
  if (!s) return;
  symbol = s;
  loadedFor = '';
  bars = [];
  series.setData([]);
  $('compare-price').textContent = '';
  $('compare-title').textContent = displayName(symbol);
  save();
  load();
}

btn.addEventListener('click', () => setOpen(wrap.hidden));
// Another panel (Insights › Correlation) asks for a pair: chart `a`, compare against `b`.
document.addEventListener('compare:pair', (e) => {
  const { a, b } = e.detail;
  $('symbol-input').value = a;
  switchSymbol(a);
  if (wrap.hidden) { symbol = b.toUpperCase(); setOpen(true); } else { input.value = b; choose(b); }
});
$('compare-close').addEventListener('click', () => setOpen(false));
// "A / B", "A - B" (spaced), "A * B", "A + B": a formula series. Runs before the search box's own Enter.
input.addEventListener('keydown', (e) => {
  const f = e.key === 'Enter' && parseFormula(input.value);
  if (!f) return;
  e.preventDefault();
  e.stopImmediatePropagation();
  input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));   // close the results list
  input.value = formulaText(f);
  choose(formulaText(f));
});
// Same search as the toolbar: a results dropdown, and Enter on typed text resolves ADANIENT -> ADANIENT.NS.
attachSearch({ input, box: $('compare-results'), idPrefix: 'cr', onChoose: choose, aliases: () => state.CONFIG.quickIndices || [] });
// Main chart reloaded (new interval/range, or its once-a-minute refresh): follow it.
document.addEventListener('candles:loaded', () => { if (!wrap.hidden) load(); });
document.addEventListener('theme:changed', () => {
  if (!cmp) return;
  cmp.applyOptions({
    layout: { background: { color: COLORS.bg }, textColor: COLORS.text },
    grid: { vertLines: { color: COLORS.grid }, horzLines: { color: COLORS.grid } },
    rightPriceScale: { borderColor: COLORS.border }, timeScale: { borderColor: COLORS.border },
  });
  makeSeries();
});
styleSel.addEventListener('change', () => {
  style = styleSel.value;
  if (cmp) makeSeries();
  save();
});

try {
  const saved = JSON.parse(localStorage.getItem(KEY) || 'null');
  if (saved && typeof saved.symbol === 'string' && (/^[A-Z0-9^.\-=]{1,20}$/.test(saved.symbol) || parseFormula(saved.symbol))) symbol = saved.symbol;
  if (saved && ['candle', 'bar', 'ha', 'line', 'area', 'baseline'].includes(saved.style)) style = styleSel.value = saved.style;
  if (saved && saved.open) setOpen(true);
} catch (e) { /* no saved compare state */ }
