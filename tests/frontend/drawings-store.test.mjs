// Saved trendlines/lines: they must persist per symbol and never break the chart if storage misbehaves.
import test from 'node:test';
import assert from 'node:assert/strict';
import { createDrawingStore } from '../../static/js/drawings-store.js';

const memoryStorage = () => {
  const m = new Map();
  return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), raw: m };
};

const line = { type: 'trend', a: { t: 1, price: 10 }, b: { t: 2, price: 12 } };
const hline = { type: 'hline', price: 22_500 };

test('a symbol with nothing saved gets an empty list', () => {
  assert.deepEqual(createDrawingStore(memoryStorage()).get('NIFTY'), []);
});

test('drawings round-trip and stay separate per symbol', () => {
  const store = createDrawingStore(memoryStorage());
  store.set('NIFTY', [line]);
  store.set('RELIANCE.NS', [hline]);
  assert.deepEqual(store.get('NIFTY'), [line]);
  assert.deepEqual(store.get('RELIANCE.NS'), [hline]);
  assert.deepEqual(store.get('NIFTY-FUT'), [], 'the future is its own chart with its own drawings');
});

test('setting an empty list (what Clear does) removes that symbol\'s drawings only', () => {
  const store = createDrawingStore(memoryStorage());
  store.set('NIFTY', [line]);
  store.set('SENSEX', [hline]);
  store.set('NIFTY', []);
  assert.deepEqual(store.get('NIFTY'), []);
  assert.deepEqual(store.get('SENSEX'), [hline]);
});

test('corrupt or wrongly-shaped saved data is ignored, not thrown', () => {
  for (const junk of ['{not json', '[]', '"a string"', 'null', '{"NIFTY":"oops"}']) {
    const s = memoryStorage();
    s.setItem('orazio.drawings.v1', junk);
    assert.deepEqual(createDrawingStore(s).get('NIFTY'), [], `junk: ${junk}`);
  }
});

test('saving over corrupt data recovers instead of failing', () => {
  const s = memoryStorage();
  s.setItem('orazio.drawings.v1', '{not json');
  const store = createDrawingStore(s);
  store.set('NIFTY', [line]);
  assert.deepEqual(store.get('NIFTY'), [line]);
});

test('storage that throws (private window / blocked site data) degrades silently', () => {
  const broken = { getItem() { throw new Error('denied'); }, setItem() { throw new Error('denied'); } };
  const store = createDrawingStore(broken);
  assert.deepEqual(store.get('NIFTY'), []);
  assert.doesNotThrow(() => store.set('NIFTY', [line]));
});
