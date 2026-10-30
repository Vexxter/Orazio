// Bonds panel: which yields flash after a poll, years to maturity, and grouping the global curve.
import test from 'node:test';
import assert from 'node:assert/strict';
import { browseCountries, changedYields, curveGeometry, groupCountries, tenorMonths, yearsTo, yieldMap } from '../../static/js/bonds-policy.js';

const before = [{ security: 'A', ltYield: 7.35 }, { security: 'B', ltYield: 6.5 }, { security: 'C', ltYield: null }];

test('only yields that moved flash, with their direction', () => {
  const after = [{ security: 'A', ltYield: 7.36 }, { security: 'B', ltYield: 6.5 }, { security: 'C', ltYield: 7.1 }, { security: 'D', ltYield: 7 }];
  assert.deepEqual([...changedYields(yieldMap(before), after)], [['A', 'up']]);
  assert.deepEqual([...changedYields(yieldMap(before), [{ security: 'B', ltYield: 6.4 }])], [['B', 'down']]);
});

test('flash works on any key/value pair (corporate bonds: symbol + ytm)', () => {
  const prev = yieldMap([{ symbol: 'X', ytm: 9 }], 'symbol', 'ytm');
  assert.deepEqual([...changedYields(prev, [{ symbol: 'X', ytm: 8.9 }], 'symbol', 'ytm')], [['X', 'down']]);
});

test('the first poll flashes nothing', () => {
  assert.equal(changedYields(null, before).size, 0);
});

test('years to maturity', () => {
  const now = Date.parse('2026-10-19');
  assert.equal(yearsTo('2036-05-11', now), 9.6);
  assert.equal(yearsTo(null, now), null);
});

test('tenors order by months', () => {
  assert.deepEqual(['30Y', '3M', '10Y', '1Y', '6M'].sort((a, b) => tenorMonths(a) - tenorMonths(b)), ['3M', '6M', '1Y', '10Y', '30Y']);
});

test('countries group by region in server order; headline is the 10Y or the nearest maturity', () => {
  const rows = [
    { country: 'US', name: 'United States', region: 'Americas', tenor: '30Y', yield: 5.4 },
    { country: 'US', name: 'United States', region: 'Americas', tenor: '2Y', yield: 4.7 },
    { country: 'US', name: 'United States', region: 'Americas', tenor: '10Y', yield: 5.0 },
    { country: 'GB', name: 'United Kingdom', region: 'Europe', tenor: '10Y', yield: 5.3 },
    { country: 'AR', name: 'Argentina', region: 'Americas', tenor: '20Y', yield: 11 },
    { country: 'EG', name: 'Egypt', region: 'Middle East & Africa', tenor: '3M', yield: 25 },
    { country: 'EG', name: 'Egypt', region: 'Middle East & Africa', tenor: '1Y', yield: 24 },
  ];
  const g = groupCountries(rows);
  assert.deepEqual(g.map(r => r.region), ['Americas', 'Europe', 'Middle East & Africa']);
  assert.deepEqual(g[0].countries.map(c => c.country), ['US', 'AR']);
  const us = g[0].countries[0];
  assert.deepEqual(us.curve.map(r => r.tenor), ['2Y', '10Y', '30Y']);
  assert.equal(us.headline.tenor, '10Y');
  assert.equal(g[0].countries[1].headline.tenor, '20Y');
  assert.equal(g[2].countries[0].headline.tenor, '1Y');
});

const CURVES = [
  { country: 'US', name: 'United States', region: 'Americas', tenor: '2Y', yield: 4.7, changeBp: -5 },
  { country: 'US', name: 'United States', region: 'Americas', tenor: '10Y', yield: 5.0, changeBp: -4 },
  { country: 'BR', name: 'Brazil', region: 'Americas', tenor: '10Y', yield: 15.3, changeBp: null },
  { country: 'DE', name: 'Germany', region: 'Europe', tenor: '1Y', yield: 2.1, changeBp: 1 },
  { country: 'DE', name: 'Germany', region: 'Europe', tenor: '10Y', yield: 3.4, changeBp: 2 },
];

test('browse: filter by name or ISO code, headline at the chosen tenor (or nearest)', () => {
  assert.deepEqual(browseCountries(CURVES, { q: 'ger' }).map(g => g.region), ['Europe']);
  assert.equal(browseCountries(CURVES, { q: 'us' })[0].countries[0].country, 'US');
  const two = browseCountries(CURVES, { tenor: '2Y' });
  assert.equal(two[0].countries[0].headline.tenor, '2Y');
  assert.equal(two[1].countries[0].headline.tenor, '1Y');      // Germany has no 2Y: nearest is 1Y
  assert.deepEqual(browseCountries(CURVES, { q: 'zz' }), []);
});

test('browse: yield/change sorts flatten into one list, highest first, missing last', () => {
  const byYield = browseCountries(CURVES, { sort: 'yield' });
  assert.equal(byYield.length, 1);
  assert.deepEqual(byYield[0].countries.map(c => c.country), ['BR', 'US', 'DE']);
  assert.deepEqual(browseCountries(CURVES, { sort: 'change' })[0].countries.map(c => c.country), ['DE', 'US', 'BR']);
});

test('curve geometry spans the box and inverts y', () => {
  const g = curveGeometry(CURVES.slice(0, 2), 100, 40, 0);
  assert.deepEqual(g.map(p => [p.x, p.y]), [[0, 40], [100, 0]]);
  assert.equal(curveGeometry(CURVES.slice(2, 3), 100, 40), null);
});

test('browse: a stand-in maturity sorts after every country quoting the tenor itself', () => {
  // Brazil's 10Y (15.3%) stands in for a 2Y it doesn't have: it goes after the real 2Y quotes.
  assert.deepEqual(browseCountries(CURVES, { tenor: '2Y', sort: 'yield' })[0].countries.map(c => c.country), ['US', 'BR', 'DE']);
});
