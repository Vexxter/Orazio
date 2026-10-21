// Bar replay: pick a bar, every bar after it disappears, then reveal them one at a time (or play at
// 1/3/10 bars a second) to practise reading the chart without seeing what comes next.
//
// It works by swapping state.latestCandles for a slice of the loaded bars, so everything that already
// draws from it — studies, volume, legend, drawings — shows only the replayed bars, for free. While
// state.replay is set, data.js leaves the chart alone: live ticks aren't folded in, the minute refresh
// is skipped, and any other reload (symbol, interval, range) ends the replay. Exit puts the full set
// back and catches up with live data.
import { chart, computeDayBoundaries, priceSeriesByStyle, renderDayLines, renderIndicators, syncStyleData, updateLegend } from './chart.js';
import { loadCandles } from './data.js';
import { turnOffDrawing } from './draw.js';
import { toggleMeasure } from './measure.js';
import { SPEEDS, atEnd, canStartAt, indexAtTime, nextIndex, tickMs } from './replay-policy.js';
import { $, dateTimeFmt, dayKey, isDaily, state } from './state.js';

const btn = $('replay-btn');
const bar = $('replay-bar');
const playBtn = $('replay-play');
const speedSel = $('replay-speed');
const labelEl = $('replay-label');

let picking = false;
let timer = null;

speedSel.innerHTML = SPEEDS.map(s => `<option value="${s}">${s} bar${s > 1 ? 's' : ''}/s</option>`).join('');

function redraw() {
  syncStyleData();
  renderIndicators();
  computeDayBoundaries();
  updateLegend(null);
}

function showBar() {
  const on = !!state.replay;
  bar.hidden = !on && !picking;
  bar.classList.toggle('picking', picking);
  btn.setAttribute('aria-pressed', String(on || picking));
  btn.querySelector('.dt-cap').textContent = on || picking ? 'Stop' : 'Start';   // the strip says what a click will do
  playBtn.textContent = timer ? '❚❚' : '▶';
  playBtn.setAttribute('aria-label', timer ? 'Pause' : 'Play');
  if (picking) { labelEl.textContent = 'Click a bar to replay from it · Esc to cancel'; return; }
  if (!on) return;
  const { full, idx } = state.replay;
  labelEl.textContent = `Replay · ${dateTimeFmt.format(new Date(full[idx].time * 1000))} · bar ${idx + 1}/${full.length}`;
}

// ---------- picking the start bar ----------
function setPicking(next) {
  picking = next;
  chart.unsubscribeClick(onPick);
  if (picking) {
    turnOffDrawing();
    toggleMeasure(true);
    chart.subscribeClick(onPick);
  }
  showBar();
}

function onPick(param) {
  if (!param.time) return;
  const idx = indexAtTime(state.latestCandles, param.time);
  if (!canStartAt(idx, state.latestCandles.length)) return;
  setPicking(false);
  start(idx);
}

// ---------- replaying ----------
function start(idx) {
  const full = state.latestCandles;
  state.replay = { full, idx };
  state.latestCandles = full.slice(0, idx + 1);
  redraw();
  chart.timeScale().scrollToRealTime();
  showBar();
}

function step() {
  const r = state.replay;
  if (!r) return;
  if (atEnd(r.idx, r.full.length)) { pause(); return; }
  r.idx = nextIndex(r.idx, r.full.length);
  const b = r.full[r.idx];
  const prev = state.latestCandles[state.latestCandles.length - 1];
  state.latestCandles.push(b);
  // update() rather than setData(): it appends one bar and keeps the chart scrolled to the newest.
  const series = priceSeriesByStyle[state.currentStyle];
  series.update(state.currentStyle === 'line' || state.currentStyle === 'area' ? { time: b.time, value: b.close } : b);
  if (!isDaily(state.currentInterval) && prev && dayKey(prev.time) !== dayKey(b.time)) {
    state.dayBoundaryTimes.add(b.time);
    renderDayLines();
  }
  renderIndicators();
  updateLegend(null);
  showBar();
  if (atEnd(r.idx, r.full.length)) pause();
}

function play() {
  if (!state.replay || timer) return;
  timer = setInterval(step, tickMs(+speedSel.value));
  showBar();
}
function pause() {
  clearInterval(timer);
  timer = null;
  showBar();
}

function exit() {
  pause();
  const r = state.replay;
  if (!r) return;
  state.replay = null;
  state.latestCandles = r.full;
  redraw();
  showBar();
  loadCandles({ preserveView: true });   // catch up with whatever arrived while replaying
}

// ---------- wiring ----------
btn.addEventListener('click', () => {
  if (state.replay) exit();
  else setPicking(!picking);
});
$('replay-exit').addEventListener('click', () => (picking ? setPicking(false) : exit()));
$('replay-step').addEventListener('click', () => { pause(); step(); });
playBtn.addEventListener('click', () => (timer ? pause() : play()));
speedSel.addEventListener('change', () => { if (timer) { pause(); play(); } });

// data.js ends a replay itself when the symbol, interval or range changes.
document.addEventListener('replay:ended', () => { pause(); showBar(); });

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && picking) { setPicking(false); return; }
  if (!state.replay || e.target.closest('input, select, textarea')) return;
  if (e.key === ' ') { e.preventDefault(); timer ? pause() : play(); }
  else if (e.key === 'ArrowRight') { e.preventDefault(); pause(); step(); }
});
