// Bonds panel rules as pure functions, unit-tested in Node (tests/frontend/bonds-policy.test.mjs).

// Rows whose yield moved since the previous poll (for the flash), keyed by `key`. The first poll
// (no previous map) flashes nothing.
export function changedYields(prev, rows, key = 'security', val = 'ltYield') {
  const out = new Map();
  if (!prev) return out;
  for (const r of rows) {
    const before = prev.get(r[key]);
    if (before != null && r[val] != null && before !== r[val]) out.set(r[key], r[val] > before ? 'up' : 'down');
  }
  return out;
}

export const yieldMap = (rows, key = 'security', val = 'ltYield') => new Map(rows.map(r => [r[key], r[val]]));

// Years to maturity from an ISO date, one decimal ("9.6y").
export function yearsTo(iso, now = Date.now()) {
  if (!iso) return null;
  return Math.round(((Date.parse(iso) - now) / (365.25 * 86400000)) * 10) / 10;
}

// "3M" -> 3, "10Y" -> 120: maturities in months, for ordering a curve.
export function tenorMonths(t) {
  const m = /^(\d+)([MY])$/.exec(t || '');
  return m ? +m[1] * (m[2] === 'Y' ? 12 : 1) : Infinity;
}

// The curve point at `tenor`, or the one nearest it (so a country without a 2Y still lines up on its 1Y/3Y).
export const nearestTenor = (curve, tenor) => {
  const want = tenorMonths(tenor);
  return curve.reduce((best, r) => (Math.abs(tenorMonths(r.tenor) - want) < Math.abs(tenorMonths(best.tenor) - want) ? r : best));
};

// What the Global tab shows: countries matching `q` (name or ISO code), each headlined at `tenor`.
// sort 'region' keeps the region groups; 'yield' / 'change' flatten to one list, highest first, with the
// countries that quote `tenor` itself ahead of those standing in with a nearby maturity.
export function browseCountries(rows, { q = '', tenor = '10Y', sort = 'region' } = {}) {
  const needle = q.trim().toLowerCase();
  const match = (c) => !needle || c.name.toLowerCase().includes(needle) || c.country.toLowerCase() === needle;
  const groups = groupCountries(rows)
    .map(g => ({ region: g.region, countries: g.countries.filter(match).map(c => ({ ...c, headline: nearestTenor(c.curve, tenor) })) }))
    .filter(g => g.countries.length);
  if (sort === 'region') return groups;
  const key = sort === 'change' ? 'changeBp' : 'yield';
  const all = groups.flatMap(g => g.countries);
  const exact = (c) => (c.headline.tenor === tenor ? 0 : 1);
  all.sort((a, b) => exact(a) - exact(b) || (b.headline[key] ?? -Infinity) - (a.headline[key] ?? -Infinity));
  return all.length ? [{ region: null, countries: all }] : [];
}

// SVG polyline points for a yield curve, x by log-maturity so 1M..30Y spread evenly. Returns
// [{ x, y, r }] in a w x h box with `pad` inset; null when fewer than two points have a yield.
export function curveGeometry(curve, w, h, pad = 6) {
  const pts = curve.filter(r => r.yield != null && Number.isFinite(tenorMonths(r.tenor)));
  if (pts.length < 2) return null;
  const xs = pts.map(r => Math.log(tenorMonths(r.tenor)));
  const ys = pts.map(r => r.yield);
  const [x0, x1] = [Math.min(...xs), Math.max(...xs)];
  let [y0, y1] = [Math.min(...ys), Math.max(...ys)];
  if (y1 - y0 < 0.05) { y0 -= 0.05; y1 += 0.05; }   // a flat curve still gets a readable line
  return pts.map((r, i) => ({
    r,
    x: pad + (xs[i] - x0) / (x1 - x0) * (w - 2 * pad),
    y: h - pad - (ys[i] - y0) / (y1 - y0) * (h - 2 * pad),
  }));
}

// Global yield rows -> [{ region, countries: [{ country, name, headline, curve }] }], keeping the server's
// region/country order. Headline = the 10Y, or the maturity nearest to it.
export function groupCountries(rows) {
  const regions = [];
  const byCountry = new Map();
  for (const r of rows) {
    let c = byCountry.get(r.country);
    if (!c) {
      c = { country: r.country, name: r.name, curve: [] };
      byCountry.set(r.country, c);
      let reg = regions.find(g => g.region === r.region);
      if (!reg) regions.push(reg = { region: r.region, countries: [] });
      reg.countries.push(c);
    }
    c.curve.push(r);
  }
  for (const c of byCountry.values()) {
    c.curve.sort((a, b) => tenorMonths(a.tenor) - tenorMonths(b.tenor));
    c.headline = nearestTenor(c.curve, '10Y');
  }
  return regions;
}
