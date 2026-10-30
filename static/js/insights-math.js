// Research math for the Insights tabs: breadth summary, returns, correlation/beta, relative rotation,
// seasonality and event studies. Pure — no DOM, no fetch — and unit-tested in Node
// (tests/frontend/insights-math.test.mjs). Bars are the chart's {time, open, high, low, close}.

import { rsi, sma } from './indicators.js';

const finite = (v) => typeof v === 'number' && Number.isFinite(v);

// ---------- breadth (screener rows) ----------
export function breadthSummary(rows) {
  const pct = (pred, base) => { const b = rows.filter(base); return b.length ? Math.round((b.filter(pred).length / b.length) * 1000) / 10 : null; };
  const has = (k) => (r) => finite(r[k]);
  return {
    total: rows.length,
    advances: rows.filter(r => r.pChange > 0).length,
    declines: rows.filter(r => r.pChange < 0).length,
    above50: pct(r => r.vsSma50 > 0, has('vsSma50')),
    above200: pct(r => r.vsSma200 > 0, has('vsSma200')),
    nearHigh: rows.filter(r => finite(r.fromHigh) && r.fromHigh >= -2).length,
    nearLow: rows.filter(r => finite(r.fromLow) && r.fromLow <= 2).length,
    overbought: rows.filter(r => r.rsi >= 70).length,
    oversold: rows.filter(r => finite(r.rsi) && r.rsi <= 30).length,
    golden: rows.filter(r => r.cross === 'golden').map(r => r.symbol),
    death: rows.filter(r => r.cross === 'death').map(r => r.symbol),
  };
}

// Counts per bucket; edges ascending, values below/above the ends go in the first/last bucket.
export function histogram(values, edges) {
  const out = new Array(edges.length + 1).fill(0);
  for (const v of values) {
    if (!finite(v)) continue;
    let i = 0;
    while (i < edges.length && v >= edges[i]) i++;
    out[i]++;
  }
  return out;
}

// ---------- rollover ----------
// Put two futures series on one x axis counted back from expiry. `prev` ends on its expiry day; `cur` ends
// `left` sessions before its own. Returns equal-length arrays (nulls where a series has no point) and labels
// like "T-3" (T-0 = expiry day).
export function alignByExpiry(prev, cur, left) {
  const back = Math.max(prev.length - 1, cur.length - 1 + left);
  const n = back + 1;
  const p = new Array(n).fill(null), c = new Array(n).fill(null);
  prev.forEach((v, i) => { p[n - prev.length + i] = v; });
  cur.forEach((v, i) => { c[n - 1 - left - (cur.length - 1 - i)] = v; });
  return { prev: p, cur: c, labels: Array.from({ length: n }, (_, i) => `T-${back - i}`) };
}

// ---------- returns, correlation, beta ----------
// IST calendar day of a bar (NSE and US daily bars both land on the right local trading date).
export const dayKey = (t) => Math.floor((t + 19800) / 86400);

// Daily simple returns keyed by IST day: Map(day -> close / previous close - 1). For a yield, the move that
// matters is the change in level (bp), not its % change: pass diff = true.
export function dailyReturns(bars, diff = false) {
  const out = new Map();
  for (let i = 1; i < bars.length; i++) {
    const a = bars[i - 1].close, b = bars[i].close;
    if (diff ? Number.isFinite(a) && Number.isFinite(b) : a > 0 && b > 0) out.set(dayKey(bars[i].time), diff ? b - a : b / a - 1);
  }
  return out;
}

// Bond yield symbols (US10Y, IN10Y-IN, DE2Y): their "returns" are level changes.
export const isYield = (sym) => /^[A-Z]{2}\d+[MY](-[A-Z]{2})?$/.test(sym);

// Pearson correlation and beta of a on b over the days both have a return; null under `minN` shared days.
export function pairStats(a, b, minN = 20) {
  const xs = [], ys = [];
  for (const [d, v] of a) if (b.has(d)) { xs.push(v); ys.push(b.get(d)); }
  const n = xs.length;
  if (n < minN) return { n, corr: null, beta: null };
  const mx = xs.reduce((s, v) => s + v, 0) / n, my = ys.reduce((s, v) => s + v, 0) / n;
  let sxy = 0, sxx = 0, syy = 0;
  for (let i = 0; i < n; i++) { sxy += (xs[i] - mx) * (ys[i] - my); sxx += (xs[i] - mx) ** 2; syy += (ys[i] - my) ** 2; }
  return { n, corr: sxx && syy ? sxy / Math.sqrt(sxx * syy) : null, beta: syy ? sxy / syy : null };
}

// ---------- relative rotation (RRG) ----------
// Weekly closes of a sector and its benchmark, aligned on IST week -> RS-Ratio / RS-Momentum, both centred on
// 100 (the JdK idea, open-source approximation): RS = sector / benchmark; RS-Ratio = 100 x RS / its n-week
// mean; RS-Momentum = 100 x RS-Ratio / its m-week mean. Right = outperforming, up = gaining on it.
export function rrg(sector, bench, n = 10, m = 4, tail = 6) {
  const weekOf = (t) => Math.floor((dayKey(t) + 3) / 7);
  const last = (bars) => { const w = new Map(); for (const b of bars) w.set(weekOf(b.time), b.close); return w; };
  const s = last(sector), b = last(bench);
  const weeks = [...s.keys()].filter(k => b.has(k)).sort((x, y) => x - y);
  const rs = weeks.map(k => s.get(k) / b.get(k));
  const mean = (a, i, k) => (i + 1 >= k ? a.slice(i + 1 - k, i + 1).reduce((x, y) => x + y, 0) / k : null);
  const ratio = rs.map((v, i) => { const mu = mean(rs, i, n); return mu ? (100 * v) / mu : null; });
  // Momentum needs m ratio values, so it starts m - 1 weeks after the ratio does.
  const mom = ratio.map((v, i) => (v === null || i + 1 < m || ratio[i + 1 - m] === null ? null : (100 * v) / mean(ratio, i, m)));
  const pts = weeks.map((w, i) => [ratio[i], mom[i]]).filter(([x, y]) => x !== null && y !== null);
  return pts.length ? { x: pts.at(-1)[0], y: pts.at(-1)[1], trail: pts.slice(-tail - 1, -1) } : null;
}

export function quadrant(x, y) {
  if (x >= 100) return y >= 100 ? 'Leading' : 'Weakening';
  return y >= 100 ? 'Improving' : 'Lagging';
}

// ---------- seasonality ----------
const istDate = (t) => new Date((t + 19800) * 1000);   // read with getUTC* = IST calendar fields

// Month-on-month returns grouped by calendar month: [{ month 0-11, avg, median, up (share > 0), n }].
export function monthlySeasonality(bars) {
  const ends = new Map();     // 'YYYY-MM' -> last close of that month
  for (const b of bars) { const d = istDate(b.time); ends.set(d.getUTCFullYear() * 12 + d.getUTCMonth(), b.close); }
  const keys = [...ends.keys()].sort((a, b) => a - b);
  const by = Array.from({ length: 12 }, () => []);
  for (let i = 1; i < keys.length; i++) {
    if (keys[i] - keys[i - 1] !== 1) continue;
    by[keys[i] % 12].push((ends.get(keys[i]) / ends.get(keys[i - 1]) - 1) * 100);
  }
  return by.map((r, month) => ({ month, ...summary(r) }));
}

// Daily returns grouped by IST weekday (1 = Monday ... 5 = Friday).
export function weekdaySeasonality(bars) {
  const by = Array.from({ length: 7 }, () => []);
  for (let i = 1; i < bars.length; i++) {
    if (bars[i - 1].close > 0) by[istDate(bars[i].time).getUTCDay()].push((bars[i].close / bars[i - 1].close - 1) * 100);
  }
  return [1, 2, 3, 4, 5].map(wd => ({ weekday: wd, ...summary(by[wd]) }));
}

export function summary(r) {
  if (!r.length) return { avg: null, median: null, up: null, n: 0 };
  const s = [...r].sort((a, b) => a - b);
  const mid = s.length >> 1;
  return {
    avg: r.reduce((a, b) => a + b, 0) / r.length,
    median: s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2,
    up: (r.filter(v => v > 0).length / r.length) * 100,
    n: r.length,
  };
}

// ---------- event study ----------
// For each event day, the % move from that day's close to the close `h` sessions later. Events falling on a
// holiday use the next session. Returns per-horizon summaries, the per-event table and the average path.
export function eventStudy(bars, eventDays, horizons = [1, 5, 10, 20], pathLen = 20) {
  const days = bars.map(b => dayKey(b.time));
  const firstAtOrAfter = (d) => { let lo = 0, hi = days.length; while (lo < hi) { const mid = (lo + hi) >> 1; if (days[mid] < d) lo = mid + 1; else hi = mid; } return lo; };
  const seen = new Set();
  const events = [];
  for (const d of [...eventDays].sort((a, b) => a - b)) {
    const i = firstAtOrAfter(d);
    if (i >= bars.length || seen.has(i) || days[i] - d > 4) continue;
    seen.add(i);
    const fwd = Object.fromEntries(horizons.map(h => [h, i + h < bars.length ? (bars[i + h].close / bars[i].close - 1) * 100 : null]));
    events.push({ day: days[i], index: i, fwd });
  }
  const stats = horizons.map(h => ({ h, ...summary(events.map(e => e.fwd[h]).filter(v => v !== null)) }));
  const path = Array.from({ length: pathLen + 1 }, (_, k) => {
    const v = events.filter(e => e.index + k < bars.length).map(e => (bars[e.index + k].close / bars[e.index].close - 1) * 100);
    return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
  });
  return { events, stats, path };
}

// Price-derived events on the same bars: days whose close-to-close move (kind drop/rise) or opening gap
// (gapdown/gapup) crosses `threshold` %. Returns IST day keys.
export function priceEvents(bars, kind, threshold) {
  const out = [];
  for (let i = 1; i < bars.length; i++) {
    const prev = bars[i - 1].close, b = bars[i];
    const move = (b.close / prev - 1) * 100, gap = (b.open / prev - 1) * 100;
    if ((kind === 'drop' && move <= -threshold) || (kind === 'rise' && move >= threshold)
      || (kind === 'gapdown' && gap <= -threshold) || (kind === 'gapup' && gap >= threshold)) out.push(dayKey(b.time));
  }
  return out;
}

// ---------- rates ----------
// Last close at or before IST day `d` in each tenor's daily bars (bars ascending). null where a tenor has none.
export function curveAt(barsByTenor, d) {
  return barsByTenor.map((bars) => {
    let lo = 0, hi = bars.length - 1, hit = null;
    while (lo <= hi) { const mid = (lo + hi) >> 1; if (dayKey(bars[mid].time) <= d) { hit = bars[mid].close; lo = mid + 1; } else hi = mid - 1; }
    return hit;
  });
}

// Linear interpolation of a curve [{years, y}] (sorted) at `years`; flat beyond the ends.
export function interp(curve, years) {
  if (!curve.length) return null;
  if (years <= curve[0].years) return curve[0].y;
  for (let i = 1; i < curve.length; i++) {
    const a = curve[i - 1], b = curve[i];
    if (years <= b.years) return a.y + ((b.y - a.y) * (years - a.years)) / (b.years - a.years);
  }
  return curve.at(-1).y;
}

const median = (a) => { const s = [...a].sort((x, y) => x - y); const m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };

// Corporate bond spreads over the G-sec curve at the same maturity, grouped by rating (AAA, AA+, ...).
// bonds: [{rating, ytm, years}], gsec: [{years, y}] sorted. Yields outside 3–20 % are treated as bad prints.
export function ratingSpreads(bonds, gsec) {
  const by = new Map();
  for (const b of bonds) {
    if (!b.rating || !(b.ytm >= 3 && b.ytm <= 20) || !(b.years > 0.25)) continue;
    const r = b.rating.split('/')[0].trim().toUpperCase();
    const g = interp(gsec, b.years);
    if (g === null) continue;
    if (!by.has(r)) by.set(r, []);
    by.get(r).push({ ytm: b.ytm, bp: (b.ytm - g) * 100 });
  }
  const order = ['AAA', 'AA+', 'AA', 'AA-', 'A+', 'A', 'A-', 'BBB+', 'BBB', 'BBB-'];
  const rank = (r) => (order.includes(r) ? order.indexOf(r) : order.length);   // unknown grades last
  return [...by].map(([rating, v]) => ({ rating, n: v.length, ytm: median(v.map(x => x.ytm)), bp: median(v.map(x => x.bp)) }))
    .sort((a, b) => rank(a.rating) - rank(b.rating));
}

// ---------- chart events ----------
// events [{date 'YYYY-MM-DD', kind, text}] -> one entry per bar: the first bar on or after the event's IST day
// (within 4 days, so a holiday rolls to the next session; events outside the loaded bars are dropped).
export function placeEvents(bars, events) {
  if (!bars.length) return [];
  const days = bars.map(b => dayKey(b.time));
  const by = new Map();
  for (const e of events) {
    const d = Math.floor(Date.parse(`${e.date}T00:00:00Z`) / 86400000);
    if (d < days[0] || d > days.at(-1)) continue;
    let lo = 0, hi = days.length;
    while (lo < hi) { const mid = (lo + hi) >> 1; if (days[mid] < d) lo = mid + 1; else hi = mid; }
    if (lo >= bars.length || days[lo] - d > 4) continue;
    const t = bars[lo].time;
    if (!by.has(t)) by.set(t, []);
    by.get(t).push(e);
  }
  return [...by].sort((a, b) => a[0] - b[0]).map(([time, list]) => ({ time, events: list }));
}

// ---------- watchlist ----------
// Daily bars (today's bar carrying the live price) -> the watchlist's computed columns.
export function watchStats(bars) {
  if (bars.length < 2) return {};
  const last = bars.at(-1), price = last.close;
  const year = bars.slice(-252);
  const hi = Math.max(...year.map(b => b.high)), lo = Math.min(...year.map(b => b.low));
  const pct = (a, b) => (b ? (a / b - 1) * 100 : null);
  const s50 = sma(bars, 50).at(-1)?.value, s200 = sma(bars, 200).at(-1)?.value;
  const vols = bars.slice(-21, -1).map(b => b.volume || 0);
  const avgVol = vols.length ? vols.reduce((a, b) => a + b, 0) / vols.length : 0;
  return {
    fromHigh: pct(price, hi), fromLow: pct(price, lo),
    rsi: rsi(bars, 14).at(-1)?.value ?? null,
    vsSma50: s50 ? pct(price, s50) : null, vsSma200: s200 ? pct(price, s200) : null,
    relVol: avgVol && last.volume ? last.volume / avgVol : null,
  };
}
