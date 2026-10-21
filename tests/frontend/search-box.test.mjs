// Typed symbols: a bare NSE ticker must load its NSE listing, not an empty "ADANIENT" chart.
import test from 'node:test';
import assert from 'node:assert/strict';
import { pickTyped } from '../../static/js/search-box.js';

const results = (...syms) => syms.map(symbol => ({ symbol }));

test('a bare NSE ticker resolves to its .NS listing', () => {
  assert.equal(pickTyped('adanient', results('ADANIENT.NS', 'ADANIENT.BO')), 'ADANIENT.NS');
  assert.equal(pickTyped('TCS', results('TCS', 'TCS.NS')), 'TCS.NS');           // NSE first: this is an Indian app
});

test('exact foreign tickers, BSE-only names and our own aliases are kept', () => {
  assert.equal(pickTyped('AAPL', results('AAPL', 'AAPL.MX')), 'AAPL');
  assert.equal(pickTyped('XYZ', results('XYZ.BO')), 'XYZ.BO');
  assert.equal(pickTyped('NIFTY', results('NIFTY.NS'), ['NIFTY', 'SENSEX']), 'NIFTY');
  assert.equal(pickTyped('^NSEI', results('^NSEI')), '^NSEI');
  assert.equal(pickTyped('RELIANCE-FUT', []), 'RELIANCE-FUT');
  assert.equal(pickTyped('unknown', []), 'UNKNOWN');
});
