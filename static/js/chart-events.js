// Event layer on the main chart (the "Events" toggle): results days, dividends, splits/bonuses, bulk/block deals
// for NSE stocks; big FII days for Indian indices; RBI rate decisions on rate-sensitive Indian charts; and your
// own journal trades (always shown). Hover a
// marker's bar to read what happened. Data: /api/chart-events (orazio/chart_events.py) + rbi-dates.js.
import { chart, priceSeriesByStyle } from './chart.js';
import { esc } from './format.js';
import { loadTrades } from './insights-journal.js';
import { placeEvents } from './insights-math.js';
import { RBI_DECISIONS } from './rbi-dates.js';
import { $, COLORS, state, token } from './state.js';

const KEY = 'orazio.events.v1';
const toggle = $('events-toggle');
const tip = $('event-tip');
const RBI_SYMBOLS = new Set(['NIFTY', 'BANKNIFTY', 'SENSEX', 'NIFTYIT', '^NSEI', '^NSEBANK', '^BSESN', 'IN10Y-IN', 'IN30Y-IN', 'INR=X', 'USDINR']);
const STYLE = {
  results: ['aboveBar', 'circle', () => COLORS.accent, 'R'],
  dividend: ['belowBar', 'circle', () => COLORS.up, 'D'],
  split: ['belowBar', 'square', () => token('--warn'), 'S'],
  bonus: ['belowBar', 'square', () => token('--warn'), 'B'],
  rights: ['belowBar', 'square', () => token('--warn'), 'Ri'],
  deal: ['aboveBar', 'arrowDown', () => token('--reb'), 'Deal'],
  fii: ['belowBar', 'arrowUp', () => COLORS.text, 'FII'],
  rbi: ['aboveBar', 'square', () => token('--warn'), 'RBI'],
  buy: ['belowBar', 'arrowUp', () => COLORS.up, 'Buy'],
  sell: ['aboveBar', 'arrowDown', () => COLORS.down, 'Sell'],
};
let cache = { symbol: null, events: [] };
let placed = new Map();   // bar time -> events

try { toggle.checked = localStorage.getItem(KEY) === '1'; } catch (e) { /* off */ }

function rbiEvents(symbol) {
  if (!RBI_SYMBOLS.has(symbol)) return [];
  return RBI_DECISIONS.map(([date, bp]) => ({ date, kind: 'rbi', text: `RBI repo ${bp > 0 ? '+' : ''}${bp} bp` }));
}

async function eventsFor(symbol) {
  if (cache.symbol === symbol) return cache.events;
  const own = await fetch(`/api/chart-events?symbol=${encodeURIComponent(symbol)}`).then(r => (r.ok ? r.json() : [])).catch(() => []);
  cache = { symbol, events: [...own, ...rbiEvents(symbol)] };
  return cache.events;
}

function clear() {
  for (const s of Object.values(priceSeriesByStyle)) s.setMarkers([]);
  placed = new Map();
  tip.hidden = true;
}

// Journal trades in this symbol always show; market events only with the toggle on.
const tradeEvents = (symbol) => loadTrades().filter(t => t.symbol === symbol)
  .map(t => ({ date: t.date, kind: t.side, text: `You ${t.side === 'buy' ? 'bought' : 'sold'} ${t.qty} @ ${t.price}${t.setup ? ` (${t.setup})` : ''}` }));

export async function renderEvents() {
  clear();
  const symbol = state.currentSymbol;
  const events = [...(toggle.checked ? await eventsFor(symbol) : []), ...tradeEvents(symbol)];
  if (symbol !== state.currentSymbol || !events.length) return;
  const groups = placeEvents(state.latestCandles, events);
  placed = new Map(groups.map(g => [g.time, g.events]));
  const markers = groups.map(({ time, events: list }) => {
    const [position, shape, color] = STYLE[list[0].kind] || STYLE.results;
    const tags = [...new Set(list.map(e => (e.kind === 'fii' ? (e.text.includes('-') ? 'FII−' : 'FII+') : (STYLE[e.kind] || STYLE.results)[3])))];
    return { time, position, shape, color: list[0].kind === 'fii' ? (list[0].text.includes('-') ? COLORS.down : COLORS.up) : color(), text: tags.join(' ') };
  });
  priceSeriesByStyle[state.currentStyle]?.setMarkers(markers);
}

chart.subscribeCrosshairMove((p) => {
  const list = p.time ? placed.get(p.time) : null;
  tip.hidden = !list;
  if (list) tip.innerHTML = list.map(e => `<div>${esc(e.date)} · ${esc(e.text)}</div>`).join('');
});

toggle.addEventListener('change', () => {
  try { localStorage.setItem(KEY, toggle.checked ? '1' : '0'); } catch (e) { /* not persisted */ }
  renderEvents();
});
document.addEventListener('candles:loaded', renderEvents);
document.addEventListener('journal:changed', renderEvents);
$('style').addEventListener('change', () => setTimeout(renderEvents));
