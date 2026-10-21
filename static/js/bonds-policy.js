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
    c.headline = c.curve.reduce((best, r) => (Math.abs(tenorMonths(r.tenor) - 120) < Math.abs(tenorMonths(best.tenor) - 120) ? r : best));
  }
  return regions;
}
