// Bloomberg-style commands typed into the symbol search: "NIFTY OPT", "RELIANCE.NS SEAS", "NIFTY 5M",
// "NIFTY CMP SPX", ":FLOW". Pure — unit-tested in Node (tests/frontend/command-parse.test.mjs).
// A single word needs a leading ":" so ordinary ticker searches (ROLL, SEAS...) are never hijacked, and aliases
// avoid words that end company names ("... BANK", "... MOTORS").

// mnemonic -> [action, description, aliases]. `tab:` opens an Insights tab, `btn:` clicks a panel button.
export const FUNCTIONS = {
  GP: ['chart:', 'Chart the symbol', ['CHART']],
  OPT: ['tab:options', 'Options analytics: GEX, IV smile and term structure, OI build-up', ['GEX', 'OI', 'IV']],
  CHAIN: ['btn:fno-btn', 'Futures and option chain panel', ['OMON', 'FNO']],
  FLOW: ['tab:flows', 'FII/DII cash flows and participant-wise OI', ['FII', 'DII']],
  BRD: ['tab:breadth', 'Market breadth', ['BREADTH']],
  DLV: ['tab:delivery', 'Delivery spikes, bulk and block deals', ['DEALS', 'DELIV']],
  ROLL: ['tab:rollover', 'Futures rollover', []],
  RRG: ['tab:rotation', 'Sector rotation', ['ROT', 'SECT']],
  CORR: ['tab:correlation', 'Correlation and beta matrix', ['BETA']],
  SEAS: ['tab:seasonality', 'Seasonality by month and weekday', []],
  EVT: ['tab:events', 'Event study', ['EVENTS']],
  RATES: ['tab:rates', 'Yield curve, spreads, corporate bond spreads', ['GC', 'CURVE', 'YC']],
  ECO: ['tab:macro', 'Economic calendar and RBI liquidity', ['MACRO', 'CAL', 'LIQ']],
  BRIEF: ['tab:brief', 'Cross-asset dashboard and pre-open brief', ['DASH', 'BRF']],
  WL: ['tab:watchlist', 'Watchlist', ['WATCH']],
  ALRT: ['tab:alerts', 'Alerts', ['ALERT', 'ALERTS']],
  JRNL: ['tab:journal', 'Trade journal', ['JOURNAL', 'TRADES']],
  CAS: ['btn:cas-move-open', 'Live closing-auction (CAS) movement', []],
  CMP: ['compare:', 'Compare with another symbol or formula: NIFTY CMP SPX', ['COMP', 'VS']],
  GRID: ['btn:grid-btn', 'Multi-chart grid', ['MULTI']],
  NEWS: ['btn:news-btn', 'News panel', []],
  BONDS: ['btn:bonds-btn', 'Bonds panel', ['GOVT']],
  SCRN: ['btn:screener-btn', 'Screener', ['EQS', 'SCREEN']],
  MOV: ['btn:movers-btn', 'Top movers', ['MOVERS']],
  WS: ['tab:workspaces', 'Save and switch layouts (Expiry day, Bond desk, Pre-open)', ['LAYOUT', 'LAYOUTS']],
  HELP: ['tab:commands', 'List every command', ['?']],
};
const ALIAS = new Map(Object.entries(FUNCTIONS).flatMap(([k, [, , al]]) => [[k, k], ...al.map(a => [a, k])]));
const INTERVALS = { '1M': '1m', '5M': '5m', '15M': '15m', '1H': '1h', '1D': '1d', D: '1d', '1W': '1wk', W: '1wk' };

// -> { fn, symbol, arg, interval } or null when the text is an ordinary search.
export function parseCommand(text) {
  const raw = (text || '').trim();
  const colon = raw.startsWith(':');
  const tokens = raw.replace(/^:/, '').trim().split(/\s+/).filter(Boolean).map(t => t.toUpperCase());
  if (!tokens.length) return null;
  if (tokens.length === 1) {
    if (!colon) return null;
    const fn = ALIAS.get(tokens[0]);
    return fn ? { fn, symbol: null, arg: null, interval: null } : null;
  }
  // SYMBOL FN [ARG...] or FN ARG (CMP SPX) or SYMBOL INTERVAL
  const [first, second, ...rest] = tokens;
  if (INTERVALS[second] && !rest.length) return { fn: 'GP', symbol: first, arg: null, interval: INTERVALS[second] };
  if (ALIAS.has(second)) return { fn: ALIAS.get(second), symbol: first, arg: rest.length ? rest.join(' ') : null, interval: null };
  if (ALIAS.has(first)) return { fn: ALIAS.get(first), symbol: null, arg: [second, ...rest].join(' '), interval: null };
  return null;
}
