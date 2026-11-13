// Insights › What changed (:NEW): one ranked inbox of surprises across your watchlist — moves that are big for that
// stock, volume spikes, 52-week breaks, results this week, insider money, ex-dates — scored against each stock's own
// history so the rare things rise. With an empty watchlist it watches the NIFTY heavyweights. The Insights button
// shows how many notable items are waiting. Scoring: changes-math.js (unit-tested).
import { eventSurprises, surprises } from './changes-math.js';
import { esc } from './format.js';
import { historyBars, registerTab } from './insights.js';
import { watchlistSymbols } from './insights-watchlist.js';
import { $ } from './state.js';

const DEFAULT = ['RELIANCE.NS', 'HDFCBANK.NS', 'ICICIBANK.NS', 'INFY.NS', 'TCS.NS', 'BHARTIARTL.NS', 'ITC.NS', 'LT.NS', 'SBIN.NS', 'BAJFINANCE.NS',
  'HINDUNILVR.NS', 'AXISBANK.NS', 'KOTAKBANK.NS', 'MARUTI.NS', 'SUNPHARMA.NS', 'NIFTY', 'BANKNIFTY'];
const NOTABLE = 2.5;
const TTL_MS = 5 * 60000;
const KIND = { move: 'Move', volume: 'Volume', high: '52W high', low: '52W low', results: 'Results', insider: 'Insiders', action: 'Ex-date' };
const json = (url) => fetch(url).then(r => (r.ok ? r.json() : null)).catch(() => null);
let cache = null;   // { at, key, items, watched, own }

const ticker = (s) => s.replace(/\.NS$/, '');

async function gather() {
  const own = watchlistSymbols();
  const watched = own.length ? own.slice(0, 40) : DEFAULT;
  const key = watched.join(',');
  if (cache && cache.key === key && Date.now() - cache.at < TTL_MS) return cache;
  const stocks = watched.filter(s => s.endsWith('.NS'));
  const [bars, cal, ins, act] = await Promise.all([
    Promise.all(watched.map(s => historyBars(s, '1Y').catch(() => []))),
    stocks.length ? json(`/api/earnings/calendar?symbols=${encodeURIComponent(stocks.map(ticker).join(','))}`) : null,
    json('/api/insider'), json('/api/corp-actions'),
  ]);
  const set = new Set(stocks);
  const since = new Date(Date.now() - 30 * 86400000).toISOString().slice(0, 10);
  const items = [
    ...watched.flatMap((s, i) => surprises(bars[i]).map(x => ({ ...x, symbol: s, cmd: s.endsWith('.NS') ? 'FA' : 'GP' }))),
    ...eventSurprises({
      results: cal?.rows || [],
      insider: (ins?.rows || []).filter(r => set.has(r.chartSymbol) && r.date >= since),
      actions: (act?.rows || []).filter(r => set.has(r.chartSymbol)),
    }, new Date().toISOString().slice(0, 10)),
  ].sort((a, b) => b.score - a.score);
  cache = { at: Date.now(), key, items, watched, own: own.length > 0 };
  badge(items.filter(x => x.score >= NOTABLE).length);
  return cache;
}

function badge(n) {
  const btn = $('insights-btn');
  let b = btn.querySelector('.ins-badge');
  if (!n) { b?.remove(); return; }
  if (!b) { b = document.createElement('span'); b.className = 'ins-badge'; btn.appendChild(b); }
  b.textContent = String(n);
  b.title = `${n} notable change${n === 1 ? '' : 's'} on your watchlist`;
}

async function render(body, ctx) {
  const d = await gather();
  if (ctx.stale()) return;
  const notable = d.items.filter(x => x.score >= NOTABLE).length;
  ctx.pill(`${d.items.length} changes · ${notable} notable`, true);
  const head = `<p class="ins-note">${d.own ? `Watching your ${d.watched.length} watchlist symbols.` : `Watching the NIFTY heavyweights. Add stocks to your watchlist (<b>:WL</b>) to make this yours.`} Ranked by how unusual each is for that stock: σ is today's move against its own last 60 days.</p>`;
  if (!d.items.length) { body.innerHTML = `${head}<div class="empty-note">A quiet day: nothing unusual across ${d.watched.length} symbols.</div>`; return; }
  body.innerHTML = `${head}<div class="chg-list">${d.items.slice(0, 60).map((x, i) => `
    <div class="chg-card${x.score >= NOTABLE ? ' hot' : ''}" data-symbol="${esc(x.symbol)}" tabindex="0" role="button" style="animation-delay:${Math.min(i, 12) * 30}ms">
      <span class="chg-kind">${esc(KIND[x.kind] || x.kind)}</span>
      <span class="chg-sym">${esc(ticker(x.symbol))}</span>
      <span class="chg-text">${esc(x.text)}</span>
      <span class="chg-score" title="How unusual, roughly in standard deviations">${x.score.toFixed(1)}</span></div>`).join('')}</div>
    <p class="ins-note">Click a card to chart the stock; its Lens (right) explains the rest.</p>`;
}

registerTab('changes', 'What changed', render, { pollMs: 300000, title: 'Surprises across your watchlist, ranked' });
setTimeout(() => gather().catch(() => {}), 6000);   // light the Insights badge soon after the page opens
