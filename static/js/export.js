// Download dialog: one-off OHLCV downloads, plus the saved end-of-day export schedule.
import { $, state } from './state.js';

const modal = $('export-modal');
let opts = null;
let trigger = null;

const setStatus = (el, text, kind = '') => { el.textContent = text; el.className = `export-status ${kind}`.trim(); };
const fillSelect = (el, items, current) => {
  el.innerHTML = items.map(i => `<option value="${i.value}">${i.label}</option>`).join('');
  if (current && items.some(i => i.value === current)) el.value = current;
};
const intervalInfo = (value) => opts.intervals.find(i => i.value === value);

async function openExport() {
  trigger = document.activeElement;
  modal.classList.add('open');
  $('export-close').focus();
  setStatus($('export-status'), 'Loading…');
  try {
    const res = await fetch(`/api/export/options?symbol=${encodeURIComponent(state.currentSymbol)}`);
    if (!res.ok) throw new Error();
    opts = await res.json();
  } catch (e) {
    setStatus($('export-status'), 'Could not load export options.', 'err');
    return;
  }
  setStatus($('export-status'), '');

  const prevUniverse = $('export-universe').value || 'CURRENT';
  fillSelect($('export-universe'), opts.universes, prevUniverse);
  const ivItems = opts.intervals.map(i => ({ value: i.value, label: i.label }));
  fillSelect($('export-interval'), ivItems, $('export-interval').value || state.currentInterval);
  const fmtItems = opts.formats.map(f => ({ value: f, label: f.toUpperCase() }));
  fillSelect($('export-format'), fmtItems, $('export-format').value);
  if (!$('export-day').value) $('export-day').value = opts.today;
  if (!$('export-from').value) $('export-from').value = opts.today;
  if (!$('export-to').value) $('export-to').value = opts.today;
  updateAvailability();

  const s = opts.schedule;
  fillSelect($('export-sched-universe'), opts.scheduleUniverses, s?.universe);
  fillSelect($('export-sched-interval'), ivItems, s?.interval || '1m');
  fillSelect($('export-sched-format'), fmtItems, s?.format);
  if (s) {
    $('export-sched-on').checked = !!s.enabled;
    $('export-sched-time').value = s.time || '15:31';
    $('export-sched-path').value = s.path || '';
  }
  showLastRun(s);
}

function closeExport() {
  modal.classList.remove('open');
  trigger?.focus();
}

// The dialog states what Yahoo still serves for the chosen bar size, and keeps the date
// pickers inside that window so an unavailable day can't be picked in the first place.
function updateAvailability() {
  if (!opts) return;
  const info = intervalInfo($('export-interval').value);
  const hint = $('export-avail');
  if (info.maxDays) {
    hint.textContent = `${info.label} bars: last ${info.maxDays} days available (from ${info.earliest} to ${opts.today}).`;
    $('export-all-label').textContent = `Entire available history (${info.maxDays} days)`;
  } else {
    hint.textContent = `${info.label} bars: full history available (since listing) up to ${opts.today}.`;
    $('export-all-label').textContent = 'Entire available history (since listing)';
  }
  for (const id of ['export-day', 'export-from', 'export-to']) {
    const el = $(id);
    el.max = opts.today;
    if (info.earliest) el.min = info.earliest; else el.removeAttribute('min');
    if (info.earliest && el.value && el.value < info.earliest) el.value = info.earliest;
    if (el.value && el.value > opts.today) el.value = opts.today;
  }
}

function selectedMode() { return document.querySelector('input[name="export-mode"]:checked').value; }

async function download() {
  const btn = $('export-download');
  const status = $('export-status');
  const mode = selectedMode();
  const params = new URLSearchParams({
    symbol: state.currentSymbol, universe: $('export-universe').value, interval: $('export-interval').value,
    mode, format: $('export-format').value,
  });
  if (mode === 'day') params.set('day', $('export-day').value);
  if (mode === 'range') { params.set('from', $('export-from').value); params.set('to', $('export-to').value); }

  btn.disabled = true;
  setStatus(status, 'Fetching bars… a full index can take up to a minute.');
  try {
    const res = await fetch(`/api/export/download?${params}`);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.error || `HTTP ${res.status}`);
    }
    const name = /filename="([^"]+)"/.exec(res.headers.get('Content-Disposition') || '')?.[1] || 'orazio-export';
    const url = URL.createObjectURL(await res.blob());
    const a = Object.assign(document.createElement('a'), { href: url, download: name });
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    setStatus(status, `Saved ${name}`, 'ok');
  } catch (e) {
    setStatus(status, e.message, 'err');
  } finally {
    btn.disabled = false;
  }
}

function showLastRun(s) {
  const el = $('export-sched-status');
  const r = s?.lastRun;
  if (!s) { setStatus(el, ''); return; }
  if (!r) { setStatus(el, s.enabled ? 'Scheduled — no run yet.' : 'Schedule is off.'); return; }
  setStatus(el, `Last run ${r.date}: ${r.message}${r.dir ? ` → ${r.dir}` : ''}`, r.ok ? 'ok' : 'err');
}

async function postSchedule(url, body) {
  const res = await fetch(url, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

async function saveSchedule() {
  const status = $('export-sched-status');
  try {
    const cfg = await postSchedule('/api/export/schedule', {
      enabled: $('export-sched-on').checked, time: $('export-sched-time').value,
      path: $('export-sched-path').value.trim(), format: $('export-sched-format').value,
      interval: $('export-sched-interval').value, universe: $('export-sched-universe').value,
    });
    if (opts) opts.schedule = cfg;
    setStatus(status, cfg.enabled ? `Saved — runs weekdays at ${cfg.time} IST.` : 'Schedule turned off.', 'ok');
  } catch (e) { setStatus(status, e.message, 'err'); }
}

async function runNow() {
  const status = $('export-sched-status');
  const btn = $('export-sched-run');
  btn.disabled = true;
  setStatus(status, 'Running…');
  try {
    // Saves the form first so "Run now" uses exactly what is on screen.
    await saveSchedule();
    const cfg = await postSchedule('/api/export/schedule/run');
    if (opts) opts.schedule = cfg;
    showLastRun(cfg);
  } catch (e) { setStatus(status, e.message, 'err'); }
  finally { btn.disabled = false; }
}

$('export-btn').addEventListener('click', openExport);
$('export-close').addEventListener('click', closeExport);
modal.addEventListener('mousedown', (e) => { if (e.target === modal) closeExport(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && modal.classList.contains('open')) closeExport(); });
$('export-interval').addEventListener('change', updateAvailability);
$('export-download').addEventListener('click', download);
$('export-sched-save').addEventListener('click', saveSchedule);
$('export-sched-run').addEventListener('click', runNow);
