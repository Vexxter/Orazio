// Symbol search ranking: the queries that went wrong with Yahoo's own ranking must put the right row first.
import test from 'node:test';
import assert from 'node:assert/strict';
import { editDistance, highlightRanges, matchesKind, parseQuery, prepare, rank, TIER } from '../../static/js/search-rank.js';

const I = (symbol, name, extra = {}) => prepare({ symbol, ticker: symbol.replace(/\.(NS|BO)$/, ''), name, exch: 'NSE', type: 'stock', pop: 5, ...extra });
const ITEMS = [
  I('NIFTY', 'Nifty 50', { ticker: 'NIFTY', type: 'index', pop: 9, alt: ['^NSEI', 'NIFTY50'] }),
  I('BANKNIFTY', 'Nifty Bank', { type: 'index', pop: 9, alt: ['^NSEBANK'] }),
  I('CRUDE', 'WTI Crude Oil', { type: 'commodity', exch: 'NYMEX', pop: 9, alt: ['CL=F', 'WTI', 'USOIL'] }),
  I('TCS.NS', 'Tata Consultancy Services Limited', { pop: 7, fno: true }),
  I('TCS-FUT', 'Tata Consultancy Services Limited Futures', { ticker: 'TCS-FUT', type: 'future', exch: 'NFO', pop: 4 }),
  I('HDFCBANK.NS', 'HDFC Bank Limited', { pop: 7 }),
  I('HDFCLIFE.NS', 'HDFC Life Insurance Company Limited', { pop: 7 }),
  I('SBIN.NS', 'State Bank of India', { pop: 7 }),
  I('SBICARD.NS', 'SBI Cards and Payment Services Limited', { pop: 7 }),
  I('HINDUNILVR.NS', 'Hindustan Unilever Limited', { pop: 7 }),
  I('M&M.NS', 'Mahindra & Mahindra Limited', { pop: 7 }),
  I('MMTC.NS', 'MMTC Limited'),
  I('RELIANCE.NS', 'Reliance Industries Limited', { pop: 7 }),
  I('RPOWER.NS', 'Reliance Power Limited'),
  I('BAJFINANCE.NS', 'Bajaj Finance Limited', { pop: 7 }),
  I('BAJAJFINSV.NS', 'Bajaj Finserv Limited', { pop: 7 }),
  I('INFY.NS', 'Infosys Limited', { pop: 7 }),
  I('BAJAJHIND.NS', 'Bajaj Hindusthan Sugar Limited'),
  I('US10Y', 'United States 10Y Govt Bond Yield', { type: 'bond', exch: 'Govt', pop: 3 }),
  I('IN10Y-IN', 'India 10Y Govt Bond Yield', { ticker: 'IN10Y', type: 'bond', exch: 'Govt', pop: 3 }),
  I('HDB', 'HDFC Bank Limited', { ticker: 'HDB', exch: 'NYSE', pop: 2 }),
];
const top = (q) => rank(ITEMS, q)[0]?.item.symbol;

test('exact ticker, alias and synonym win', () => {
  assert.equal(top('TCS'), 'TCS.NS');
  assert.equal(top('tcs'), 'TCS.NS');
  assert.equal(top('^NSEI'), 'NIFTY');
  assert.equal(top('usoil'), 'CRUDE');
  assert.equal(top('M&M'), 'M&M.NS');
  assert.equal(top('mm'), 'M&M.NS');                 // ampersand-less, still exact
  assert.equal(top('US10Y'), 'US10Y');
});

test('ticker prefix: popular and shorter first', () => {
  assert.equal(top('BAJF'), 'BAJFINANCE.NS');
  assert.equal(top('INF'), 'INFY.NS');                // INFY before nothing longer; prefix beats IN10Y name words
  assert.equal(top('BANK'), 'BANKNIFTY');             // the index outranks stocks
  assert.equal(top('SBI'), 'SBIN.NS');
  assert.equal(rank(ITEMS, 'TCS')[1].item.symbol, 'TCS-FUT');
});

test('company-name words: the Indian listing beats the US ADR', () => {
  const r = rank(ITEMS, 'hdfc bank');
  assert.equal(r[0].item.symbol, 'HDFCBANK.NS');
  assert.equal(r[0].tier, TIER.EXACT);               // "hdfc bank" compacts to the ticker HDFCBANK
  assert.ok(r.findIndex(h => h.item.symbol === 'HDB') > 0);
  assert.equal(top('hdfc insurance'), 'HDFCLIFE.NS');
  assert.equal(rank(ITEMS, 'hdfc insurance')[0].tier, TIER.PREFIX);   // starts the name: as good as a ticker prefix
  assert.equal(rank(ITEMS, 'life insurance').find(h => h.item.symbol === 'HDFCLIFE.NS').tier, TIER.WORDS);
  const bajaj = rank(ITEMS, 'bajaj').map(h => h.item.symbol);
  assert.ok(bajaj.indexOf('BAJFINANCE.NS') < bajaj.indexOf('BAJAJHIND.NS'), 'popular name match beats an obscure ticker prefix');
  assert.equal(top('reliance power'), 'RPOWER.NS');
  assert.equal(top('india 10y'), 'IN10Y-IN');
  assert.equal(top('tata fut'), 'TCS-FUT');
});

test('home market first: a foreign exact ticker sits below an Indian prefix match, but beats a typo', () => {
  const remote = [I('SBI', 'Western Asset Fund', { exch: 'NYSE', pop: 3, remote: true }),
    I('HULC', 'Global X US Large Cap', { exch: 'TSX', pop: 1, remote: true }),
    I('AAPL', 'Apple Inc.', { exch: 'NASDAQ', pop: 3, remote: true })];
  const all = ITEMS.concat(remote, [I('APLAPOLLO.NS', 'APL Apollo Tubes Limited')]);
  assert.equal(rank(all, 'SBI')[0].item.symbol, 'SBIN.NS');
  assert.equal(rank(all, 'HUL')[0].item.symbol, 'HINDUNILVR.NS');
  assert.equal(rank(all, 'AAPL')[0].item.symbol, 'AAPL');
});

test('acronyms: SBI, HUL', () => {
  assert.equal(rank(ITEMS, 'HUL')[0].item.symbol, 'HINDUNILVR.NS');
  assert.equal(rank(ITEMS, 'HUL')[0].tier, TIER.ACRONYM);
  assert.ok(rank(ITEMS, 'SBI').some(h => h.item.symbol === 'SBIN.NS'));
});

test('typos only when nothing better', () => {
  assert.equal(top('relaince'), 'RELIANCE.NS');
  assert.equal(top('infosis'), 'INFY.NS');
  assert.equal(rank(ITEMS, 'zzzz').length, 0);
});

test('exchange prefix filters (TradingView NSE:XYZ)', () => {
  assert.deepEqual(parseQuery('nse: infy'), { text: 'INFY', exch: 'NSE' });
  assert.deepEqual(parseQuery('^NSEI'), { text: '^NSEI', exch: null });
  assert.equal(top('NSE:hdfc bank'), 'HDFCBANK.NS');
  assert.equal(top('NYSE:hdfc bank'), 'HDB');
});

test('kind filter: Stocks includes ETFs', () => {
  assert.ok(matchesKind({ type: 'etf' }, 'stock'));
  assert.ok(!matchesKind({ type: 'index' }, 'stock'));
  assert.ok(matchesKind({ type: 'index' }, 'all'));
});

test('edit distance with adjacent swaps', () => {
  assert.equal(editDistance('RELAINCE', 'RELIANCE', 2), 1);
  assert.equal(editDistance('ABC', 'ABC', 1), 0);
  assert.equal(editDistance('ABCDEF', 'UVWXYZ', 1), 2);    // gives up past max
});

test('highlight ranges: word starts first, no overlaps', () => {
  assert.deepEqual(highlightRanges('HDFC Bank Limited', 'hdfc bank'), [[0, 4], [5, 9]]);
  assert.deepEqual(highlightRanges('Bajaj Finance', 'fin'), [[6, 9]]);
  assert.deepEqual(highlightRanges('BAJFINANCE', 'fin'), [[3, 6]]);
  assert.deepEqual(highlightRanges('Nifty', ''), []);
});

test('2,600-symbol master ranks in under 15 ms', () => {
  const many = Array.from({ length: 2600 }, (_, i) => I(`SYM${i}.NS`, `Company Number ${i} Industries Limited`));
  const t = performance.now();
  for (const q of ['s', 'sym12', 'company 99', 'industres']) rank(many, q);
  assert.ok((performance.now() - t) / 4 < 15, 'too slow');
});
