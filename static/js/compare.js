// Compare: a second chart beside the main one for any other symbol (index, stock, commodity, crypto).
// It follows the main chart's bar interval and history range, scrolls and zooms with it by TIME (so
// NIFTY next to SPX shows the same wall-clock window even though their sessions differ), mirrors the
// crosshair, and keeps its newest bar live from its own quote stream. The header compares both
// symbols' % change over the window currently on screen.
import { chart } from './chart.js';
import { feedQuery } from './feed-policy.js';
import { attachSearch, pickTyped } from './search-box.js';
import { $, COLORS, INTERVAL_SECONDS, dateFmt, dateTimeFmt, displayName, esc, isDaily, state, timeFmt, token } from './state.js';

const KEY = 'orazio.compare.v1';
const wrap = $('compare-wrap');
const btn = $('compare-btn');
const input = $('compare-input');

let symbol = 'SENSEX';
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
  try { localStorage.setItem(KEY, JSON.stringify({ open: !wrap.hidden, symbol })); } catch (e) { /* not persisted */ }
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
  series = cmp.addCandlestickSeries({ upColor: COLORS.up, downColor: COLORS.down, borderVisible: false, wickUpColor: COLORS.up, wickDownColor: COLORS.down });

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
    renderLegend(p.time ? p.seriesData.get(series) : null);
  });
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

async function load() {
  if (wrap.hidden) return;
  const my = ++generation;
  driver = 'main';
  const key = `${symbol}|${state.currentInterval}|${state.currentRange}`;
  $('compare-note').textContent = loadedFor === key ? '' : 'Loading…';
  try {
    const res = await fetch(`/api/candles?symbol=${encodeURIComponent(symbol)}&interval=${state.currentInterval}&range=${state.currentRange}${feedFor(symbol)}`);
    if (!res.ok) throw new Error(res.status === 400 ? 'Not a valid symbol' : `HTTP ${res.status}`);
    const d = await res.json();
    if (my !== generation) return;
    bars = d.candles || [];
    // A bare ticker saved before search resolution existed (ADANIENT) has no data: resolve it once.
    if (!bars.length && /^[A-Z0-9&-]+$/.test(symbol)) {
      const items = await fetch(`/api/search?q=${encodeURIComponent(symbol)}`).then(r => (r.ok ? r.json() : [])).catch(() => []);
      const picked = pickTyped(symbol, items, state.CONFIG.quickIndices || []);
      if (picked !== symbol && my === generation) { input.value = picked; choose(picked); return; }
    }
    series.setData(bars);
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
  if (wrap.hidden || typeof EventSource === 'undefined') return;
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
    series.update(bars.at(-1));
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
$('compare-close').addEventListener('click', () => setOpen(false));
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
  series.applyOptions({ upColor: COLORS.up, downColor: COLORS.down, wickUpColor: COLORS.up, wickDownColor: COLORS.down });
});

try {
  const saved = JSON.parse(localStorage.getItem(KEY) || 'null');
  if (saved && typeof saved.symbol === 'string' && /^[A-Z0-9^.\-=]{1,20}$/.test(saved.symbol)) symbol = saved.symbol;
  if (saved && saved.open) setOpen(true);
} catch (e) { /* no saved compare state */ }
