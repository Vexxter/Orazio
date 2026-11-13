// Symbol search ranking — pure, no DOM (tests/frontend/search-rank.test.mjs).
// Works the way TradingView's and Bloomberg's security finders do: a local symbol list scored in tiers
// (exact ticker > ticker prefix > name words > acronym > substring > typo), ties broken by how much the
// instrument matters to this app (an Indian index or F&O stock before an obscure listing), then by length.

export const TIER = { EXACT: 100, PREFIX: 90, WORDS: 80, ACRONYM: 70, ACRONYM_PREFIX: 65, TICKER_SUB: 60, NAME_SUB: 55, FUZZY: 40 };
const REMOTE_PENALTY = 25;

const STOP = new Set(['LTD', 'LIMITED', 'THE', 'OF', 'AND', '&', 'CO', 'INC', 'CORP', 'PLC', 'COMPANY']);
const compact = (s) => s.replace(/[^A-Z0-9]/g, '');
const words = (s) => s.split(/[^A-Z0-9&]+/).filter(Boolean);

// Item fields: symbol (what loads), ticker (shown), name, exch, type, pop (0-9), fno, alt (synonyms),
// remote (came from Yahoo, not the local master).
export function prepare(item) {
  const T = String(item.ticker || item.symbol).toUpperCase();
  const N = String(item.name || '').toUpperCase();
  const w = words(N);
  const alt = [item.symbol, ...(item.alt || [])].map(a => String(a).toUpperCase());
  return {
    ...item, ticker: item.ticker || item.symbol,
    _T: T, _Tc: compact(T), _N: N, _w: [compact(T), ...w],
    _acr: w.filter(x => !STOP.has(x)).map(x => x[0]).join(''), _acrAll: w.map(x => x[0]).join(''),
    _alt: alt, _altc: alt.map(compact),
  };
}

// "NSE:RELIANCE" (TradingView syntax) -> { text: 'RELIANCE', exch: 'NSE' }.
export function parseQuery(raw) {
  const m = String(raw || '').trim().match(/^([A-Za-z]{2,8}):\s*(.*)$/);
  return m ? { text: m[2].trim().toUpperCase(), exch: m[1].toUpperCase() } : { text: String(raw || '').trim().toUpperCase(), exch: null };
}

// Optimal-string-alignment distance (Damerau-Levenshtein with adjacent swaps), giving up past `max`.
export function editDistance(a, b, max) {
  if (Math.abs(a.length - b.length) > max) return max + 1;
  let prev2 = null, prev = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    const cur = [i];
    let rowMin = i;
    for (let j = 1; j <= b.length; j++) {
      let d = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) d = Math.min(d, prev2[j - 2] + 1);
      cur.push(d);
      rowMin = Math.min(rowMin, d);
    }
    if (rowMin > max) return max + 1;
    prev2 = prev; prev = cur;
  }
  return prev[b.length];
}

// Every query word starts a different word of the name (or the ticker).
function wordsMatch(tokens, w) {
  const used = new Set();
  return tokens.every(t => {
    const i = w.findIndex((x, k) => !used.has(k) && x.startsWith(t));
    if (i < 0) return false;
    used.add(i);
    return true;
  });
}

export function score(it, q) {
  const qc = compact(q);
  if (!qc) return 0;
  if (it._T === q || it._Tc === qc || it._alt.includes(q) || it._altc.includes(qc)) return TIER.EXACT;
  if (it._T.startsWith(q) || it._Tc.startsWith(qc)) return TIER.PREFIX;
  const tokens = words(q).map(t => (t === '&' ? t : compact(t))).filter(Boolean);
  // Starting the company's name counts as much as starting its ticker: "bajaj" -> BAJFINANCE, ranked by popularity.
  if (tokens.length && wordsMatch(tokens, it._w)) return it._w[1] && it._w[1].startsWith(tokens[0]) ? TIER.PREFIX : TIER.WORDS;
  if (qc.length >= 2 && tokens.length === 1 && (it._acr === qc || it._acrAll === qc)) return TIER.ACRONYM;
  if (qc.length >= 3 && tokens.length === 1 && (it._acr.startsWith(qc) || it._acrAll.startsWith(qc))) return TIER.ACRONYM_PREFIX;
  if (qc.length >= 2 && it._Tc.includes(qc)) return TIER.TICKER_SUB;
  if (q.length >= 3 && it._N.includes(q)) return TIER.NAME_SUB;
  return 0;
}

function fuzzy(it, qc) {
  const max = qc.length >= 7 ? 2 : 1;
  return [it._Tc, ...it._w].some(x => x.length >= 3 && editDistance(qc, x, max) <= max) ? TIER.FUZZY : 0;
}

const KIND_FILTER = { stock: ['stock', 'etf'] };   // the Stocks chip includes ETFs, as on TradingView
export function matchesKind(it, kind) {
  return !kind || kind === 'all' || (KIND_FILTER[kind] || [kind]).includes(it.type);
}

// Ranked [{ item, tier }], every hit (filter by chip with matchesKind). Typo matches only when the real
// tiers find fewer than 5 hits.
export function rank(items, raw) {
  const { text: q, exch } = parseQuery(raw);
  if (!q) return [];
  const pool = exch ? items.filter(it => String(it.exch || '').toUpperCase().startsWith(exch)) : items;
  let hits = [];
  for (const it of pool) {
    const tier = score(it, q);
    if (tier) hits.push({ item: it, tier });
  }
  const qc = compact(q);
  if (hits.length < 5 && qc.length >= 4) {
    const seen = new Set(hits.map(h => h.item));
    for (const it of pool) if (!seen.has(it) && fuzzy(it, qc)) hits.push({ item: it, tier: TIER.FUZZY });
  }
  // Home market first (TradingView's region preference): a remote (Yahoo) row ranks a step and a half lower,
  // so a foreign fund ticked "SBI" sits below SBIN, while AAPL still beats a typo match.
  const rankOf = h => h.tier - (h.item.remote ? REMOTE_PENALTY : 0);
  return hits.sort((a, b) => rankOf(b) - rankOf(a) || (b.item.pop || 0) - (a.item.pop || 0)
    || a.item._T.length - b.item._T.length || (a.item._T < b.item._T ? -1 : a.item._T > b.item._T ? 1 : 0));
}

// [start, end) ranges of `text` to highlight for query `raw`: each query word at a word start, else anywhere.
export function highlightRanges(text, raw) {
  const T = String(text || '').toUpperCase();
  const tokens = words(parseQuery(raw).text);
  const out = [];
  for (const t of tokens) {
    let i = -1;
    for (let at = T.indexOf(t); at >= 0; at = T.indexOf(t, at + 1)) {
      if (at === 0 || !/[A-Z0-9]/.test(T[at - 1])) { i = at; break; }
    }
    if (i < 0) i = T.indexOf(t);
    if (i >= 0 && !out.some(([a, b]) => i < b && i + t.length > a)) out.push([i, i + t.length]);
  }
  return out.sort((a, b) => a[0] - b[0]);
}
