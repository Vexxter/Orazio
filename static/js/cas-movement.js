// Call auction: live movement modal (Indian indices, one quadrant each).
// Every chart is measured against the REFERENCE: the last value at 15:14:59, the final traded
// value before continuous trading stops. A baseline series draws green above it, red below it.
import { CAS_PHASE_NAME, fmtCountdown } from './cas-panel.js';
import { $, COLORS, alpha, dayKey, esc, istHms, timeFmt, token } from './state.js';

const moveModal = $('move-modal');
let movePoll = null, moveTrigger = null;
const moveCharts = {};
const MOVE_INDICES = [
  ['NIFTY', 'Nifty 50'], ['BANKNIFTY', 'Bank Nifty'],
  ['NIFTYIT', 'Nifty IT'], ['SENSEX', 'BSE Sensex'],
];

// Epoch seconds of HH:MM today in IST.
function istToday(h, m, sec = 0) {
  const pad = (n) => String(n).padStart(2, '0');
  return Date.parse(`${dayKey(Date.now() / 1000)}T${pad(h)}:${pad(m)}:${pad(sec)}+05:30`) / 1000;
}

function buildQuads() {
  $('move-grid').innerHTML = MOVE_INDICES.map(([alias, name]) => `
    <section class="quad" data-alias="${alias}">
      <header class="quad-head">
        <div class="quad-id"><b>${alias}</b><span>${esc(name)}</span></div>
        <div class="quad-val"><span class="num quad-num">–</span><span class="num quad-delta">–</span></div>
        <em class="move-tag">Last</em>
      </header>
      <div class="quad-chart" id="quad-chart-${alias}"></div>
      <footer class="quad-foot"><span class="quad-ref">Reference locks at 15:14:59</span><span class="quad-src"></span></footer>
    </section>`).join('');

  for (const [alias] of MOVE_INDICES) {
    const chart = LightweightCharts.createChart($(`quad-chart-${alias}`), {
      autoSize: true,
      layout: { background: { color: COLORS.bg }, textColor: COLORS.text, fontFamily: token('--font'), fontSize: 11 },
      grid: { vertLines: { color: COLORS.grid }, horzLines: { color: COLORS.grid } },
      crosshair: { mode: LightweightCharts.CrosshairMode.Normal,
        vertLine: { color: COLORS.crosshair, labelBackgroundColor: token('--bg-3') },
        horzLine: { color: COLORS.crosshair, labelBackgroundColor: token('--bg-3') } },
      rightPriceScale: { borderColor: COLORS.border, scaleMargins: { top: 0.12, bottom: 0.12 } },
      timeScale: { borderColor: COLORS.border, timeVisible: true, secondsVisible: false, rightOffset: 0, fixLeftEdge: true, fixRightEdge: true,
        tickMarkFormatter: (t) => timeFmt.format(new Date(t * 1000)) },
      localization: { timeFormatter: (t) => istHms.format(new Date(t * 1000)) + ' IST' },
    });
    const series = chart.addBaselineSeries({
      baseValue: { type: 'price', price: 0 },
      topLineColor: COLORS.up, bottomLineColor: COLORS.down, lineWidth: 2,
      topFillColor1: alpha(COLORS.up, 0.32), topFillColor2: alpha(COLORS.up, 0.04),
      bottomFillColor1: alpha(COLORS.down, 0.04), bottomFillColor2: alpha(COLORS.down, 0.32),
      priceLineVisible: false, lastValueVisible: true,
    });
    moveCharts[alias] = { chart, series, refLine: null, refValue: null };
  }
}

function destroyQuads() {
  for (const k of Object.keys(moveCharts)) { moveCharts[k].chart.remove(); delete moveCharts[k]; }
  $('move-grid').innerHTML = '';
}

// One point per second, forward-filled, then whitespace to 15:36 — so the x-axis is proportional
// to real time (a 2/s stream and an 11s tick would otherwise be spaced by index, not time).
function timeline(points, from, to, nowSec) {
  const byT = new Map();
  for (const p of points) {
    const v = (p[2] !== null && p[2] !== undefined) ? p[2] : p[1];
    if (v !== null && v !== undefined) byT.set(Math.floor(p[0]), v);
  }
  const data = [];
  let carry = null;
  const known = [...byT.keys()].sort((a, b) => a - b);
  let ki = 0;
  for (let t = from; t <= to; t++) {
    while (ki < known.length && known[ki] <= t) { carry = byT.get(known[ki]); ki++; }
    if (t > nowSec) data.push({ time: t });
    else if (carry !== null) data.push({ time: t, value: carry });
  }
  return data;
}

function renderMove(d) {
  const live = ['pre-open', 'closing-auction', 'post-market'].includes(d.phase);
  const pill = $('move-pill');
  pill.dataset.live = String(live);
  pill.textContent = live
    ? `${CAS_PHASE_NAME[d.phase] || d.phase} · ${d.secondsRemaining == null ? 'running' : fmtCountdown(d.secondsRemaining) + ' left'}`
    : `Auction starts 15:15 · ${d.nseStatus || 'watching'}`;
  pill.title = d.stage || '';
  $('move-strip').innerHTML =
    (d.stage ? `<span class="feed-stage">${esc(d.stage)}</span>` : '') +
    `<span>Measured against the last value at <b>15:14:59</b> · green above, red below</span>` +
    `<span class="feed-strip-val">BSE stream: ${d.stream.connected ? '<span class="up">connected</span>' : '<span class="down">down — using REST</span>'}</span>`;

  const nowSec = Math.floor(Date.now() / 1000);
  const from = istToday(15, 10), to = istToday(15, 36);
  for (const idx of d.indices) {
    const q = moveCharts[idx.alias];
    const card = document.querySelector(`.quad[data-alias="${idx.alias}"]`);
    if (!q || !card) continue;

    const ref = idx.reference ? idx.reference.value : null;
    const cur = (idx.indicative !== null && idx.indicative !== undefined) ? idx.indicative : idx.last;
    const isInd = idx.indicative !== null && idx.indicative !== undefined;

    // baseline = the reference once locked; before that, the current value keeps the line neutral
    q.series.applyOptions({ baseValue: { type: 'price', price: ref !== null ? ref : (cur ?? 0) } });
    q.series.setData(timeline(idx.points, from, to, nowSec));
    if (q.refValue !== ref) {
      if (q.refLine) q.series.removePriceLine(q.refLine);
      q.refLine = ref !== null ? q.series.createPriceLine({ price: ref, color: '#98a2b3', lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle.Dashed, axisLabelVisible: true, title: 'REF 15:14:59' }) : null;
      q.refValue = ref;
    }
    try { q.chart.timeScale().setVisibleRange({ from, to }); } catch (e) { /* no data yet */ }

    card.querySelector('.quad-num').textContent = cur === null || cur === undefined ? '–' : Number(cur).toFixed(2);
    const delta = card.querySelector('.quad-delta');
    if (ref !== null && cur !== null && cur !== undefined) {
      const diff = cur - ref, pct = diff / ref * 100, up = diff >= 0;
      delta.className = `num quad-delta ${up ? 'up' : 'down'}`;
      delta.textContent = `${up ? '▲ +' : '▼ '}${diff.toFixed(2)} pts  (${up ? '+' : ''}${pct.toFixed(3)}%)`;
    } else {
      delta.className = 'num quad-delta';
      delta.textContent = d.referenceLocked ? 'reference unavailable' : 'awaiting reference';
    }
    const tag = card.querySelector('.move-tag');
    tag.textContent = isInd ? 'Indicative' : 'Last';
    tag.classList.toggle('ind', isInd);
    card.querySelector('.quad-ref').textContent = ref !== null
      ? `Reference ${Number(ref).toFixed(2)} · ${idx.reference.source}`
      : (d.referenceLocked ? 'Reference could not be determined' : 'Reference locks at 15:14:59');
    card.querySelector('.quad-src').textContent = idx.available ? `${idx.source} · ${idx.points.length} pts` : 'waiting for first tick';
  }
}

async function loadMove() {
  try {
    const res = await fetch('/api/cas/movement');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    renderMove(await res.json());
  } catch (e) { /* keep the last frame; the next poll retries */ }
}
function openMove() {
  moveTrigger = document.activeElement;
  moveModal.classList.add('open');
  $('move-close').focus();
  destroyQuads();
  buildQuads();
  loadMove();
  clearInterval(movePoll);
  movePoll = setInterval(loadMove, 2000);
}
function closeMove() {
  moveModal.classList.remove('open');
  clearInterval(movePoll); movePoll = null;
  destroyQuads();
  moveTrigger?.focus();
}
$('cas-move-open').addEventListener('click', openMove);
$('move-close').addEventListener('click', closeMove);
moveModal.addEventListener('mousedown', (e) => { if (e.target === moveModal) closeMove(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && moveModal.classList.contains('open')) closeMove(); });
