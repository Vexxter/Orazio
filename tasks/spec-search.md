# Spec: Symbol search (ticker-first, instant, ranked)

Status: APPROVED 23 Oct 2026, implemented. Deviations from v1 are marked (changed).

## Objective
Make the symbol search behave like TradingView's / Bloomberg's security finder: type a ticker, a company
name, an acronym or a typo and the right instrument is at the top, instantly.

Measured today (23 Oct 2026, `hdfc bank`):
- ~970 ms keystroke → results (300 ms debounce + ~670 ms Yahoo round trip).
- Ranking is Yahoo's: `HDB` (US ADR) above `HDFCBANK.NS`; mutual funds (`0P00012KBL.BO`) and US options fill slots.
- `M&M` returns US junk; `SBI` / `HUL` (acronyms) don't find State Bank / Hindustan Unilever.
- App-only instruments are unsearchable: `RELIANCE-FUT` (213 F&O futures), `US10Y` (161 bond yields), `GIFTNIFTY`, alias synonyms (`USOIL`, `NIFTY50`).
- Exchange shown as raw codes (`NSI`, `NYQ`); no type, no match highlight, no recents, no filters.

## Approach (how TradingView/Bloomberg do it)
Both run a **local symbol master + tiered ranker**, not a remote full-text search:
1. A prebuilt symbol list (ticker, name, exchange, type, popularity) searched in-process on every keystroke.
2. Tiered scoring — exact ticker > ticker prefix > name-word prefix > acronym > substring > fuzzy — with
   ties broken by popularity/liquidity and the user's home market.
3. Remote search only to fill the long tail (global listings).

Ours:
- **Master** = NSE equity list (`EQUITY_L.csv`, ~2,100 rows, public archive) + F&O stocks and their `-FUT`
  contracts + rail aliases and their synonyms + index futures + 161 bond yields. Served once by
  `GET /api/symbols`, cached 24 h server-side (NSE CSV also kept on disk), loaded at page boot.
  (changed) 3,019 symbols = 471 KB uncompressed, 13 ms on localhost; not gzipped (would need a dep or manual gzip).
- **Ranker** (pure JS, unit-tested), per item, best tier wins:

  | Tier | Score | Example |
  |---|---|---|
  | Exact ticker / alias / synonym | 100 | `TCS`, `USOIL`→CRUDE, `^NSEI`→NIFTY |
  | Ticker prefix | 90 | `BAJFI` → BAJFINANCE |
  | Every query word prefixes a name word | 80 | `hdfc bank` → HDFC Bank Ltd |
  | Acronym of name (skip Ltd/Limited/of/and/the) | 70 | `SBI`, `HUL`, `TCS` |
  | Substring of ticker / name | 60 / 55 | `FINANCE` → BAJFINANCE |
  | Fuzzy: 1 edit (len 4–6), 2 edits (7+) | 40 | `relaince` → RELIANCE |

  (changed) Starting the company's first name word counts as a ticker prefix (`bajaj` → BAJFINANCE).
  (changed) Yahoo rows rank 25 points lower (home-market preference), so an NYSE fund `SBI` sits below SBIN.
  Tiebreak: liquidity ladder — alias 9, Nifty 50 8, F&O 7, Nifty 500 6, NSE EQ 5, futures 4, bonds 3, Yahoo 1-3;
  then shorter ticker, then alphabetical. Fuzzy runs only when better tiers return < 5 hits.
- **Yahoo** stays for global coverage: fetched in parallel (debounce 150 ms), junk dropped
  (MUTUALFUND, OPTION, `0P…`, BSE futures), deduped against the master, scored by the same ranker so
  `AAPL` still lands on top.
- **Exchange syntax** (TradingView): `NSE:RELIANCE` → RELIANCE.NS, `BSE:TCS` → TCS.BO.

## UI
- Local results render with **no debounce** (< 16 ms); a "Searching global markets…" row while Yahoo is in flight.
- Row: **ticker** (matched chars highlighted) · name (highlighted, title case) · type badge (Stock / Index /
  Future / Bond / Crypto / Commodity / ETF / FX) · readable exchange (NSE, BSE, NASDAQ, NYSE…) · `F&O` tag.
- Filter chips above results: All · Stocks · Indices · Futures · Commodities · Bonds · Crypto.
  (changed) Chips are plain buttons in the Tab order (←/→ would steal caret movement), with per-type counts.
- Empty input on focus → **Recent** (last 8 picks, localStorage) .
- First row pre-selected: Enter opens the best match (TradingView behaviour). If only fuzzy/substring
  hits exist and Yahoo is still in flight, Enter waits for Yahoo before choosing.
- Type-to-search: pressing a letter/digit anywhere on the page (not in a field, no modifier) opens search
  with that character. `/` and Ctrl+K also focus it.
- Empty state: "No match for "xyz" — Enter loads it as a ticker". Footer hint: `↑↓ ↵ Esc · NSE:TICKER`.
- Dropdown 440 px wide, ≤ 10 visible rows, keyboard + screen-reader complete (combobox/listbox,
  `aria-activedescendant`, `aria-selected`, chips as `role=tab`).
- Compare pane uses the same component, so it gets all of the above.

## Tech stack / commands (unchanged, no new deps)
```
python app.py              # http://localhost:5000
python -m pytest           # backend tests
npm test                   # frontend pure-logic tests
```

## Files
```
orazio/symbol_master.py          NEW  build the master (NSE CSV + F&O + aliases + bonds), 24 h cache
orazio/routes/symbol_info.py     CHG  GET /api/symbols; /api/search drops junk + maps exchange names
orazio/constants.py              CHG  INDEX_META (names/groups) moves here from rail.js; served in /api/config
static/js/search-rank.js         NEW  pure: normalise, score, rank, highlight, parse NSE:/BSE: prefix
static/js/search-box.js          CHG  instant local results, Yahoo merge, chips, recents, highlight
static/js/symbol.js              CHG  type-to-search, Ctrl+K
static/js/rail.js                CHG  read names from config instead of its own table
static/index.html, styles.css    CHG  dropdown markup + styles
tests/frontend/search-rank.test.mjs   NEW
tests/test_symbol_master.py           NEW
```

## Testing
- `search-rank.test.mjs`: each tier with a real example above; tiebreaks (`hdfc bank` → HDFCBANK.NS before
  HDB; `TCS` → TCS.NS first); `NSE:`/`BSE:` parsing; highlight ranges; 2,600-item rank < 5 ms.
- `test_symbol_master.py`: CSV parsing, F&O flags, `-FUT` rows, alias synonyms, failure → aliases still served.
- Browser check: keystroke → first paint < 50 ms; queries `TCS`, `M&M`, `SBI`, `relaince`, `hdfc bank`,
  `RELIANCE-FUT`, `US10Y`, `AAPL`, `NSE:INFY` each put the expected item first; keyboard-only flow works.

## Boundaries
- Always: public sources only (NSE archive, Yahoo search) — no broker APIs; keep `pickTyped` behaviour for
  existing tests.
- Ask first: adding a BSE scrip master or G-sec (CCIL) entries to the master.
- Never: new npm/pip dependencies; send user input anywhere but `/api/search` → Yahoo (as today).

## Success criteria
1. The 9 browser-check queries above each return the expected instrument as row 1.
2. Local results paint < 50 ms after a keystroke (vs ~970 ms today).
3. No mutual funds / options / `0P…` rows; exchanges shown as readable names.
4. `npm test` and `python -m pytest` pass.

## Open questions
1. UI tweaks scope: search only (this spec), or also an app-wide polish pass after it lands?
