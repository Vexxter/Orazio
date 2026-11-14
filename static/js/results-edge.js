// Results edge: how big a move the options market prices through a company's results, as a % of spot — the ATM straddle
// on the first expiry after the results date. Compared with the stock's usual results move (insights-math.js
// resultsReactions), it says whether options are rich or cheap going into the number. Used by the Lens and Earnings.
const MONTHS = { Jan: 0, Feb: 1, Mar: 2, Apr: 3, May: 4, Jun: 5, Jul: 6, Aug: 7, Sep: 8, Oct: 9, Nov: 10, Dec: 11 };
export const expiryTime = (s) => { const [d, m, y] = String(s).split('-'); return Date.UTC(+y, MONTHS[m], +d); };   // '25-Nov-2026'
const json = (url) => fetch(url).then(r => (r.ok ? r.json() : null)).catch(() => null);

let fnoList = null;
export const fnoStocks = () => (fnoList ||= json('/api/fno/symbols').then(d => new Set(d?.stocks || [])));

// ticker 'TCS', results 'YYYY-MM-DD' -> { move (% of spot), expiry } or null (no F&O, no chain, no straddle).
export async function impliedMove(ticker, resultsIso) {
  if (!(await fnoStocks()).has(ticker)) return null;
  const first = await json(`/api/fno?symbol=${encodeURIComponent(`${ticker}.NS`)}`);
  const at = Date.parse(`${resultsIso}T00:00:00Z`);
  const exp = (first?.chain?.expiries || []).find(e => expiryTime(e) >= at);
  if (!exp) return null;
  const ch = exp === first.chain.expiry ? first.chain : (await json(`/api/fno?symbol=${encodeURIComponent(`${ticker}.NS`)}&expiry=${encodeURIComponent(exp)}`))?.chain;
  return ch?.straddle && ch.spot ? { move: ch.straddle / ch.spot * 100, expiry: exp } : null;
}
