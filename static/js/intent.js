// What the person typed into the search box, read as intent — pure, unit-tested (tests/frontend/intent.test.mjs).
//   "tcs peers"                     -> TCS · Company fundamentals        (runs "TCS FA")
//   "nifty gex"                     -> NIFTY · Options analytics          (runs "NIFTY OPT")
//   "tcs vs infy"                   -> Compare TCS with INFY              (runs "TCS CMP INFY")
//   "cheap IT stocks with high ROE" -> Screen NSE stocks for it           (plain-English screen, Find tab)
//   "insider"                       -> Insider buys and sells             (runs ":INS")
// Every action shows the command it runs, so using the box teaches the fast path. The box still searches symbols:
// actions only lead when the words say so (strong), otherwise they sit under the symbol matches.
import { FUNCTIONS } from './command-parse.js';

// Everyday words -> command mnemonic. Single words only; the first match per command wins.
const WORDS = {
  peers: 'FA', peer: 'FA', fundamentals: 'FA', fundamental: 'FA', valuation: 'FA', financials: 'FA', ratios: 'FA', company: 'FA', profile: 'FA', pe: 'FA',
  results: 'ERN', earnings: 'ERN', quarterly: 'ERN',
  insider: 'INS', insiders: 'INS', promoters: 'INS',
  shareholding: 'HOLD', holding: 'HOLD', holdings: 'HOLD', fii: 'FLOW', dii: 'FLOW', flows: 'FLOW',
  filings: 'FIL', filing: 'FIL', announcements: 'FIL', concall: 'FIL', transcript: 'FIL',
  options: 'OPT', option: 'OPT', gex: 'OPT', gamma: 'OPT', iv: 'OPT', volatility: 'OPT', skew: 'OPT', chain: 'CHAIN', oi: 'CHAIN', straddle: 'CHAIN',
  seasonality: 'SEAS', seasonal: 'SEAS', news: 'NEWS', headlines: 'NEWS',
  ipo: 'IPO', ipos: 'IPO', listing: 'IPO', listings: 'IPO', dividend: 'IPO', dividends: 'IPO', split: 'IPO', bonus: 'IPO', buyback: 'IPO',
  rates: 'RATES', yields: 'RATES', curve: 'RATES', bonds: 'BONDS', gsec: 'BONDS', fed: 'WIRP', rbi: 'WIRP', hikes: 'WIRP', cuts: 'WIRP',
  size: 'SIZE', sizing: 'SIZE', risk: 'SIZE', stop: 'SIZE', portfolio: 'PORT', alert: 'ALRT', alerts: 'ALRT', journal: 'JRNL',
  breadth: 'BRD', rotation: 'RRG', sectors: 'RRG', correlation: 'CORR', beta: 'CORR', delivery: 'DLV', deals: 'DLV', block: 'DLV', bulk: 'DLV',
  rollover: 'ROLL', backtest: 'OBT', excel: 'XL', spreadsheet: 'XL', macro: 'ECO', economy: 'ECO', calendar: 'ECO', inflation: 'ECO', cpi: 'ECO',
  brief: 'BRIEF', morning: 'BRIEF', changed: 'NEW', changes: 'NEW', today: 'NEW', watchlist: 'WL', event: 'EVT', movers: 'MOV', gainers: 'MOV', losers: 'MOV',
  screen: 'FIND', screener: 'FIND', find: 'FIND', grid: 'GRID', sources: 'SRC', settings: 'SET', layout: 'WS', auction: 'CAS', help: 'HELP', commands: 'HELP',
};
// Words that make a phrase a screen ("stocks with ROE above 20"), not a symbol plus a command.
const SCREEN = new Set(['stocks', 'stock', 'companies', 'company', 'shares', 'with', 'above', 'below', 'under', 'over', 'than', 'high', 'higher', 'low', 'lower',
  'cheap', 'undervalued', 'expensive', 'debt', 'free', 'roe', 'roce', 'p/e', 'pe', 'pb', 'p/b', 'dividend', 'yield', 'promoter', 'near', '52', 'week', 'golden',
  'cross', 'breakout', 'quality', 'growth', 'margin', 'eps', 'market', 'cap', 'large', 'small', 'mid', 'momentum', 'return', 'returns', 'dma']);
const FILLER = new Set(['the', 'a', 'an', 'of', 'for', 'show', 'me', 'open', 'see', 'and', 'on', 'in', 'its', 'what', 'is', 'are', 'whats', 'how']);

export function readIntent(text) {
  const raw = (text || '').trim();
  if (!raw || raw.startsWith(':')) return { actions: [], strong: false };
  const words = raw.toLowerCase().split(/\s+/);
  const actions = [];

  const screenish = words.filter(w => SCREEN.has(w)).length;
  if (words.length >= 3 && screenish >= 2) {
    actions.push({ kind: 'screen', label: `Screen NSE stocks: “${raw}”`, hint: ':FIND', run: raw });
  }

  const vs = words.indexOf('vs') > 0 ? words.indexOf('vs') : words.indexOf('versus');
  if (vs > 0 && words[vs + 1]) {
    const a = words.slice(0, vs).join(' ').toUpperCase(), b = words.slice(vs + 1).join(' ').toUpperCase();
    actions.push({ kind: 'cmd', label: `Compare ${a} with ${b}`, hint: `${a} CMP ${b}`, run: `${a} CMP ${b}` });
  }

  const fns = [...new Set(words.map(w => WORDS[w]).filter(Boolean))].filter(fn => FUNCTIONS[fn]);
  const rest = words.filter(w => !WORDS[w] && !FILLER.has(w));
  // A symbol is a short leftover word ("tcs", "nifty", "reliance.ns"), never a screening phrase.
  const sym = !actions.length && rest.length === 1 && /^[a-z0-9&.^=-]{2,20}$/.test(rest[0]) ? rest[0].toUpperCase() : null;
  for (const fn of fns.slice(0, 3)) {
    const [, desc] = FUNCTIONS[fn];
    if (sym && fn !== 'HELP') actions.push({ kind: 'cmd', label: `${sym} · ${desc}`, hint: `${sym} ${fn}`, run: `${sym} ${fn}` });
    else if (!rest.length || !sym) actions.push({ kind: 'cmd', label: desc, hint: `:${fn}`, run: `:${fn}` });
  }
  // Strong: the words clearly asked for something, so Enter runs it instead of searching for a ticker.
  const strong = actions.length > 0 && (actions[0].kind === 'screen' || vs > 0 || (fns.length > 0 && words.length >= 2) || (fns.length > 0 && !rest.length));
  return { actions: actions.slice(0, 4), strong };
}
