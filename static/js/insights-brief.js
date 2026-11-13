// Insights › Brief: one screen for the open. Cross-asset tiles (Indian indices, GIFT Nifty, VIX, rupee, rates,
// crude, gold, US, crypto), the opening gap GIFT Nifty implies for NIFTY, yesterday's FII/DII cash, today's
// high-impact releases and the top NIFTY headlines. Click a tile to chart it. Refreshes every 15 s.
import { esc } from './format.js';
import { registerTab } from './insights.js';

const TILES = [
  ['NIFTY', 'NIFTY 50'], ['BANKNIFTY', 'Bank Nifty'], ['SENSEX', 'Sensex'], ['GIFTNIFTY', 'GIFT Nifty'],
  ['^INDIAVIX', 'India VIX'], ['INR=X', 'USD/INR'], ['IN10Y-IN', 'India 10Y'], ['US10Y', 'US 10Y'],
  ['DX-Y.NYB', 'Dollar index'], ['BRENT', 'Brent'], ['GOLD', 'Gold'], ['SPX', 'S&P 500'], ['NASDAQ', 'Nasdaq'], ['BTC', 'Bitcoin'],
];
const YIELDS = new Set(['IN10Y-IN', 'US10Y']);
const nf = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 });
const istTime = new Intl.DateTimeFormat('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', hour12: false });
const istDate = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kolkata' });

const getJson = (url) => fetch(url).then(r => (r.ok ? r.json() : null)).catch(() => null);

function tile(sym, label, q) {
  if (!q || !Number.isFinite(q.price)) return `<div class="ins-card" data-symbol="${esc(sym)}" role="button" tabindex="0"><div class="k">${esc(label)}</div><div class="v dim">–</div></div>`;
  const chg = YIELDS.has(sym) ? `${q.change >= 0 ? '+' : ''}${Math.round(q.change * 100)} bp` : `${q.changePercent >= 0 ? '+' : ''}${q.changePercent.toFixed(2)}%`;
  return `<div class="ins-card" data-symbol="${esc(sym)}" role="button" tabindex="0" title="Chart ${esc(label)}"><div class="k">${esc(label)}</div><div class="v">${nf.format(q.price)}</div><div class="s ${q.change >= 0 ? 'up' : 'down'}">${chg}</div></div>`;
}

async function render(body, ctx) {
  const [quotes, flows, macro, news] = await Promise.all([
    Promise.all(TILES.map(([s]) => getJson(`/api/quote?symbol=${encodeURIComponent(s)}`))),
    getJson('/api/flows'), getJson('/api/macro'), getJson('/api/news?symbol=NIFTY'),
  ]);
  if (ctx.stale()) return;
  ctx.pill('Live');
  const q = Object.fromEntries(TILES.map(([s], i) => [s, quotes[i]]));
  const nifty = q.NIFTY, gift = q.GIFTNIFTY;
  // Outside 09:15–15:30 IST NIFTY's quote is its last close, so GIFT − NIFTY is the gap the open would show;
  // during the session it is just GIFT's premium (mostly carry) over the live index.
  let gap = '';
  if (nifty && gift) {
    const pts = gift.price - nifty.price;
    const hm = +istTime.format(new Date()).replace(':', '');
    const live = hm >= 915 && hm < 1530;
    gap = `<div class="ins-card"><div class="k">${live ? 'GIFT Nifty premium over NIFTY' : 'Gap GIFT Nifty implies for the open'}</div><div class="v ${pts >= 0 ? 'up' : 'down'}">${pts >= 0 ? '+' : ''}${nf.format(pts)} pts</div><div class="s">${((pts / nifty.price) * 100).toFixed(2)}% vs NIFTY ${live ? 'live' : 'last close'} ${nf.format(nifty.price)}${live ? '' : ' (includes GIFT’s small futures premium)'}</div></div>`;
  }
  const cash = flows?.cash?.at(-1);
  const flowCard = cash ? `<div class="ins-card" data-tab-link="flows" role="button" tabindex="0"><div class="k">FII / DII cash · ${esc(cash.date)}</div><div class="v"><span class="${cash.fii?.net >= 0 ? 'up' : 'down'}">${nf.format(cash.fii?.net ?? 0)}</span> / <span class="${cash.dii?.net >= 0 ? 'up' : 'down'}">${nf.format(cash.dii?.net ?? 0)}</span></div><div class="s">₹ Cr net</div></div>` : '';
  const today = istDate.format(new Date());
  const events = (macro?.calendar || []).filter(e => e.impact === 'High' && istDate.format(new Date(e.time)) === today)
    .sort((a, b) => Date.parse(a.time) - Date.parse(b.time));
  const liq = macro?.liquidity?.at(-1);
  const liqCard = liq ? `<div class="ins-card"><div class="k">System liquidity · ${esc(liq.date)}</div><div class="v ${liq.net <= 0 ? 'up' : 'down'}">${nf.format(liq.net)} Cr</div><div class="s">${liq.net <= 0 ? 'surplus' : 'deficit'} · call ${liq.call}%</div></div>` : '';
  body.innerHTML = `<div class="ins-cards">${TILES.map(([s, l]) => tile(s, l, q[s])).join('')}</div>
    <div class="ins-cards">${gap}${flowCard}${liqCard}</div>
    <div class="ins-grid2">
      <div class="ins-sec"><h3>High-impact releases today (IST)</h3>${events.length ? `<table class="opt-table"><tbody>${events.map(e => `<tr><td>${esc(istTime.format(new Date(e.time)))}</td><td>${esc(e.country)}</td><td style="text-align:left">${esc(e.title)}</td><td>${esc(e.forecast || '–')}</td></tr>`).join('')}</tbody></table>` : '<div class="ins-note">None scheduled today.</div>'}</div>
      <div class="ins-sec"><h3>Top headlines · NIFTY</h3>${(news?.items || []).slice(0, 6).map(n => `<div class="brief-news"><a href="${esc(n.url)}" target="_blank" rel="noopener noreferrer">${esc(n.title)}</a><span class="ins-note"> · ${esc(n.publisher || '')}</span></div>`).join('') || '<div class="ins-note">No headlines.</div>'}</div>
    </div>`;
  body.querySelector('[data-tab-link]')?.addEventListener('click', () => document.querySelector('#insights-tabs [data-tab="flows"]')?.click());
}

registerTab('brief', 'Brief', render, { pollMs: 15000, title: 'Cross-asset dashboard and pre-open brief' });
