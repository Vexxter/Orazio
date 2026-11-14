// Insights › Company (:FA): what the business is, what it earns, what it's worth against its peers. Bloomberg's
// DES + FA + RV on public data. Follows the chart's NSE stock. Data: /api/fundamentals and /api/peers
// (orazio/fundamentals.py): NSE MarketLens first (profile, ratios, quarters, peers), Yahoo where it lags (annual
// statements, balance sheet and cash-flow history, EV/EBITDA, blanks). A value Yahoo filled is tagged "Yahoo".
import { esc } from './format.js';
import { registerTab } from './insights.js';
import { bars, legend } from './minichart.js';
import { state } from './state.js';

const nf0 = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 });
const nf2 = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 });
const n = (v, f = nf0) => (v === null || v === undefined ? '–' : f.format(v));
const pct = (v) => (v === null || v === undefined ? '–' : `${nf2.format(v)}%`);
const x = (v) => (v === null || v === undefined ? '–' : `${nf2.format(v)}x`);
const card = (k, v, s = '') => `<div class="ins-card"><div class="k">${esc(k)}</div><div class="v">${v}</div><div class="s">${s}</div></div>`;
// "Yahoo" under a value Yahoo filled because NSE MarketLens had none; NSE values carry no tag (the default source).
const tag = (src, key, s = '') => [s, src?.[key] === 'yahoo' ? 'Yahoo' : ''].filter(Boolean).join(' · ');
const isStock = (s) => /\.(NS|BO)$/.test(s) || /^[A-Z0-9&-]+$/.test(s);
const qLabel = (p) => new Date(`${p}T00:00:00Z`).toLocaleDateString('en-IN', { month: 'short', year: '2-digit', timeZone: 'UTC' });

// One statement as a table: periods across, line items down (the way annual reports print them).
function statementTable(periods, lines, title) {
  if (!periods.length) return '';
  const head = periods.map(p => `<th>${esc(qLabel(p.period))}</th>`).join('');
  const val = (p, key) => (typeof key === 'function' ? key(p) : p[key]);
  const shown = lines.filter(([key]) => periods.some(p => val(p, key) !== null && val(p, key) !== undefined));
  const body = shown.map(([key, label, fmt = n]) => `<tr><td style="text-align:left">${esc(label)}</td>${periods.map(p => `<td>${fmt(val(p, key))}</td>`).join('')}</tr>`).join('');
  return `<div class="ins-sec"><h3>${esc(title)}</h3><table class="opt-table"><thead><tr><th style="text-align:left">₹ Cr</th>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

const margin = (p) => (p.netIncome !== null && p.revenue ? p.netIncome / p.revenue * 100 : null);
const INCOME_LINES = [['revenue', 'Revenue'], ['ebitda', 'EBITDA'], ['operatingIncome', 'Operating profit'], ['profitBeforeTax', 'Profit before tax'], ['netIncome', 'Net profit'],
  [margin, 'Net margin', pct], ['eps', 'EPS (₹)', (v) => n(v, nf2)]];

function peersTable(p, me) {
  if (!p?.available) return `<div class="ins-sec"><h3>Peers</h3><div class="empty-note">${esc(p?.reason || 'Peers unavailable.')}</div></div>`;
  const cols = [['marketCapCr', 'Mkt cap ₹ Cr', n], ['pe', 'P/E', x], ['pb', 'P/B', x], ['evEbitda', 'EV/EBITDA', x], ['roe', 'ROE', pct], ['roce', 'ROCE', pct],
    ['margin', 'Margin', pct], ['revenueGrowth', 'Rev growth', pct], ['dividendYield', 'Div yield', pct], ['ch365', '1Y', pct]]
    .filter(([k]) => p.rows.some(r => r[k] !== null && r[k] !== undefined));   // a column no source filled is noise
  const rows = p.rows.map(r => `<tr data-symbol="${esc(r.chartSymbol)}" tabindex="0" role="button"${r.symbol === me ? ' class="ins-me"' : ''}>
      <td style="text-align:left"><strong>${esc(r.symbol)}</strong> <span class="ins-note">${esc(r.name)}</span></td>${cols.map(([k, , f]) => `<td>${f(r[k])}</td>`).join('')}</tr>`).join('');
  const med = `<tr><td style="text-align:left"><b>Peer median</b></td>${cols.map(([k, , f]) => `<td><b>${k in p.median ? f(p.median[k]) : ''}</b></td>`).join('')}</tr>`;
  return `<div class="ins-sec"><h3>Peers · ${esc(p.industry)} (${esc(p.basis || 'same industry')})</h3><table class="opt-table"><thead><tr><th style="text-align:left">Company</th>${cols.map(([, l]) => `<th>${esc(l)}</th>`).join('')}</tr></thead><tbody>${rows}${med}</tbody></table></div>`;
}

// "Cheaper than peers" reads: the stock's P/E against the peer median, and its ROE against theirs.
function verdict(r, med) {
  if (!med || r.pe === null || med.pe === null) return '';
  const prem = (r.pe / med.pe - 1) * 100;
  const quality = r.roe !== null && med.roe !== null ? (r.roe >= med.roe ? 'higher' : 'lower') : null;
  return `P/E ${prem >= 0 ? `${nf0.format(prem)}% above` : `${nf0.format(-prem)}% below`} the peer median${quality ? `, with ${quality} ROE (${pct(r.roe)} vs ${pct(med.roe)})` : ''}.`;
}

async function render(body, ctx) {
  const sym = state.currentSymbol;
  if (!isStock(sym) || sym.startsWith('^')) { ctx.pill(''); body.innerHTML = '<div class="empty-note">Chart an NSE stock (like TCS.NS) to see its fundamentals.</div>'; return; }
  ctx.pill(`${sym} · loading`, false);
  const [f, p] = await Promise.all([
    fetch(`/api/fundamentals?symbol=${encodeURIComponent(sym)}`).then(r => r.json()),
    fetch(`/api/peers?symbol=${encodeURIComponent(sym)}`).then(r => r.json()).catch(() => null),
  ]);
  if (ctx.stale()) return;
  if (!f.available) { ctx.pill('Unavailable', false); body.innerHTML = `<div class="empty-note">${esc(f.reason)}</div>`; return; }
  ctx.pill(`${sym} · ${f.nseUpdated ? `NSE ${f.nseUpdated.slice(0, 16).replace('T', ' ')}` : 'Yahoo'}`, false);
  const r = f.ratios, q = f.quarterly, src = f.ratioSource || {};
  const qs = [{ name: 'Revenue', values: q.map(p => p.revenue), color: () => 'var(--accent)' }, { name: 'Net profit', values: q.map(p => p.netIncome), color: () => 'var(--up)' }];
  const next = f.nextEarnings ? new Date(f.nextEarnings * 1000).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : null;
  body.innerHTML = `<div class="ins-sec"><h3>${esc(f.name)}</h3>
      <p class="ins-note">${[f.sector, f.industry].filter(Boolean).map(esc).join(' · ')}${f.headquarters ? ` · ${esc(f.headquarters)}` : ''}${f.founded ? ` · since ${esc(f.founded)}` : ''}${f.employees ? ` · ${nf0.format(f.employees)} employees` : ''}${next ? ` · next results ${esc(next)}` : ''}${f.website ? ` · <a href="${esc(f.website)}" target="_blank" rel="noopener noreferrer">website</a>` : ''}</p>
      ${f.summary ? `<details><summary class="ins-note">What it does</summary><p class="ins-note">${esc(f.summary)}</p></details>` : ''}</div>
    <div class="ins-cards">
      ${card('Market cap', `₹${n(r.marketCapCr)} Cr`, tag(src, 'marketCapCr'))}${card('P/E (TTM)', x(r.pe), tag(src, 'pe', r.forwardPe ? `forward ${x(r.forwardPe)}` : ''))}
      ${card('P/B', x(r.pb), tag(src, 'pb', r.bookValue ? `book ₹${n(r.bookValue, nf2)}/share` : ''))}${card('EV/EBITDA', x(r.evEbitda), tag(src, 'evEbitda'))}
      ${card('ROE', pct(r.roe), tag(src, 'roe'))}${r.roce !== null && r.roce !== undefined ? card('ROCE', pct(r.roce), r.roa ? `ROA ${pct(r.roa)}` : '') : ''}
      ${card('Net margin', pct(r.margin), tag(src, 'margin'))}${card('Revenue growth', pct(r.revenueGrowth), tag(src, 'revenueGrowth', 'latest quarter vs a year ago'))}
      ${card('Debt/equity', x(r.debtToEquity), tag(src, 'debtToEquity'))}${card('EPS (TTM)', r.eps === null ? '–' : `₹${n(r.eps, nf2)}`, tag(src, 'eps'))}
      ${r.dividendYield !== null ? card('Dividend yield', pct(r.dividendYield), tag(src, 'dividendYield')) : ''}${r.promoterHolding ? card('Promoter holding', pct(r.promoterHolding)) : ''}
    </div>
    ${p?.available ? `<p class="ins-note">${esc(verdict(r, p.median))}</p>` : ''}
    ${q.length ? `<div class="ins-sec"><h3>Quarterly revenue and profit (₹ Cr)</h3>${legend(qs)}${bars({ labels: q.map(p => qLabel(p.period)), series: qs, w: 1100, h: 180 })}</div>` : ''}
    ${statementTable(q, INCOME_LINES, `Quarterly results · ${f.quarterlySource === 'nse' ? 'NSE' : 'Yahoo'}`)}
    ${statementTable(f.annual, INCOME_LINES, 'Annual results (fiscal years) · Yahoo')}
    <div class="ins-grid2">${statementTable(f.balance, [['totalAssets', 'Total assets'], ['equity', 'Shareholders’ equity'], ['totalDebt', 'Total debt'], ['cash', 'Cash']], 'Balance sheet')}
      ${statementTable(f.cashflow, [['operatingCashFlow', 'Operating cash flow'], ['capex', 'Capex'], ['freeCashFlow', 'Free cash flow']], 'Cash flow')}</div>
    ${peersTable(p, sym.replace(/\.(NS|BO)$/, ''))}
    <p class="ins-note">Profile, ratios, quarters and peers come from NSE MarketLens; Yahoo fills what it lacks (annual statements, balance sheet and cash-flow history, EV/EBITDA) and any value tagged "Yahoo". NSE's quarterly revenue is total income, and NSE and Yahoo can differ on standalone versus consolidated figures.${f.reportedIn && f.reportedIn !== 'INR' ? ` This company reports to Yahoo in ${esc(f.reportedIn)}; amounts are converted at today's ₹${nf2.format(f.fxRate)}.` : ''}${f.profileComplete ? '' : ' Yahoo’s company profile didn’t answer; description and forward P/E will fill in on a later visit.'}</p>`;
}

registerTab('company', 'Company', render, { title: 'Fundamentals: profile, ratios, statements, peers' });
