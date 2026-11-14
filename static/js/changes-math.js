// "What changed": surprises in a stock's own daily bars, scored against its own history so a 2% day in a sleepy
// utility outranks a 2% day in a small-cap. Pure — unit-tested in tests/frontend/changes-math.test.mjs.
// Bars: daily, oldest first, the last one being today (or the last session). -> [{ kind, score, text }].
// Score is a rough z: about 2 = notable, 3+ = rare.

const sd = (a) => { const m = a.reduce((s, x) => s + x, 0) / a.length; return Math.sqrt(a.reduce((s, x) => s + (x - m) ** 2, 0) / (a.length - 1)); };

export function surprises(bars) {
  const out = [];
  const b = bars.filter(x => x.close > 0);
  if (b.length < 30) return out;
  const last = b.at(-1), prev = b.at(-2);
  const rets = b.slice(-61).map((x, i, a) => (i ? Math.log(x.close / a[i - 1].close) : null)).slice(1);
  const hist = rets.slice(0, -1), today = rets.at(-1);
  const vol = sd(hist);
  if (vol > 0) {
    const z = today / vol;
    if (Math.abs(z) >= 2) out.push({ kind: 'move', score: Math.abs(z), text: `${today > 0 ? '+' : ''}${((last.close / prev.close - 1) * 100).toFixed(1)}% today, a ${Math.abs(z).toFixed(1)}σ move for it` });
  }
  const vols = b.slice(-21, -1).map(x => x.volume).filter(v => v > 0);
  if (vols.length >= 10 && last.volume > 0) {
    const ratio = last.volume / (vols.reduce((s, v) => s + v, 0) / vols.length);
    if (ratio >= 2) out.push({ kind: 'volume', score: 1 + Math.log2(ratio), text: `Volume ${ratio.toFixed(1)}× its 20-day average` });
  }
  const year = b.slice(-253, -1);
  if (year.length >= 120) {
    const hi = Math.max(...year.map(x => x.high ?? x.close)), lo = Math.min(...year.map(x => x.low ?? x.close));
    if (last.close > hi) out.push({ kind: 'high', score: 2.5, text: 'Closed at a new 52-week high' });
    else if (last.close < lo) out.push({ kind: 'low', score: 2.5, text: 'Closed at a new 52-week low' });
  }
  return out;
}

// Event surprises from feeds, already filtered to the watchlist: results soon, insider money, ex-dates.
export function eventSurprises({ results = [], insider = [], actions = [] }, todayIso) {
  const days = (iso) => Math.round((Date.parse(`${iso}T00:00:00Z`) - Date.parse(`${todayIso}T00:00:00Z`)) / 86400000);
  const out = [];
  for (const r of results) {
    const d = days(r.date);
    if (d >= 0 && d <= 7) out.push({ symbol: r.chartSymbol, kind: 'results', score: 3.2 - d * 0.25, text: `Results ${d === 0 ? 'today' : d === 1 ? 'tomorrow' : `in ${d} days`} (${r.date})`, cmd: 'ERN' });
  }
  const net = new Map();
  for (const t of insider) net.set(t.chartSymbol, (net.get(t.chartSymbol) || 0) + (t.side === 'buy' ? t.valueCr : -t.valueCr));
  for (const [sym, cr] of net) {
    if (Math.abs(cr) >= 1) out.push({ symbol: sym, kind: 'insider', score: 1.5 + Math.log10(Math.abs(cr) + 1), text: `Insiders net ${cr > 0 ? 'bought' : 'sold'} ₹${Math.abs(cr).toFixed(1)} Cr recently`, cmd: 'INS' });
  }
  for (const a of actions) {
    const d = days(a.date);
    if (d >= 0 && d <= 5) out.push({ symbol: a.chartSymbol, kind: 'action', score: 2 - d * 0.2, text: `${a.subject}: ex-date ${d === 0 ? 'today' : d === 1 ? 'tomorrow' : `in ${d} days`}`, cmd: 'IPO' });
  }
  return out;
}
