// The search box reads intent: a symbol plus a word runs a view, a sentence runs a screen, a bare ticker stays a search.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readIntent } from '../../static/js/intent.js';

const first = (t) => readIntent(t).actions[0];

test('symbol plus a word runs that view on the symbol, and says the command', () => {
  assert.deepEqual(first('tcs peers'), { kind: 'cmd', label: 'TCS · Company fundamentals: profile, ratios, statements, peers', hint: 'TCS FA', run: 'TCS FA' });
  assert.equal(first('nifty gex').run, 'NIFTY OPT');
  assert.equal(first('show me reliance results').run, 'RELIANCE ERN');
  assert.ok(readIntent('tcs peers').strong);
});

test('a bare word opens its view; a bare ticker is still just a search', () => {
  assert.equal(first('insider').run, ':INS');
  assert.ok(readIntent('insider').strong);
  assert.deepEqual(readIntent('tcs'), { actions: [], strong: false });
  assert.deepEqual(readIntent('nifty 50').actions, []);
});

test('a screening sentence becomes a plain-English screen', () => {
  const r = readIntent('cheap stocks with high ROE');
  assert.equal(r.actions[0].kind, 'screen');
  assert.equal(r.actions[0].run, 'cheap stocks with high ROE');
  assert.ok(r.strong);
});

test('a vs b compares', () => {
  assert.equal(first('tcs vs infy').run, 'TCS CMP INFY');
});

test('commands typed with a colon are left to the command line', () => {
  assert.deepEqual(readIntent(':FA'), { actions: [], strong: false });
});
