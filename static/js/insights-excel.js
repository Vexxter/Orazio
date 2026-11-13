// Insights › Excel (:XL): copy-paste formulas that pull live values, history and ratios from this app into Excel or
// LibreOffice, like Bloomberg's BDP / BDH. Served by /xl/* (orazio/routes/xl.py) while Orazio runs.
import { esc } from './format.js';
import { registerTab } from './insights.js';
import { state } from './state.js';
import { toast } from './ui.js';

function rows(sym) {
  const base = location.origin;
  const s = encodeURIComponent(sym);
  return [
    ['Live price (one cell)', `=WEBSERVICE("${base}/xl/quote?s=${s}&f=price")`],
    ['Day change %', `=WEBSERVICE("${base}/xl/quote?s=${s}&f=changePercent")`],
    ['P/E from the Company tab', `=WEBSERVICE("${base}/xl/fund?s=${s}&f=pe")`],
    ['Price that refreshes every minute', `=WEBSERVICE("${base}/xl/quote?s=${s}&f=price&t="&ROUND(NOW()*1440,0))`],
    ['Several symbols as a table (Data › From Web)', `${base}/xl/quote?s=${s},NIFTY,INR=X&f=symbol,price,change,changePercent`],
    ['Daily history as CSV (Data › From Web)', `${base}/xl/history?s=${s}&range=1Y&interval=1d`],
    ['Every ratio as a table', `${base}/xl/fund?s=${s}`],
  ];
}

async function render(body, ctx) {
  const sym = state.currentSymbol;
  ctx.pill(esc(sym), false);
  body.innerHTML = `<p class="ins-note">Paste a formula into a cell. Values come from this Orazio, so it has to be running. Excel recalculates =WEBSERVICE when the sheet does (F9); the "refreshes every minute" form forces it.</p>
    <table class="opt-table"><thead><tr><th style="text-align:left">What</th><th style="text-align:left">Formula or URL</th><th></th></tr></thead><tbody>${
      rows(sym).map(([what, f], i) => `<tr><td style="text-align:left">${esc(what)}</td><td style="text-align:left"><code class="num">${esc(f)}</code></td>
        <td><button type="button" class="btn" data-copy="${i}">Copy</button></td></tr>`).join('')}</tbody></table>
    <p class="ins-note">Fields for /xl/quote: symbol, price, change, changePercent, currency, marketTime, source. /xl/fund fields: marketCapCr, pe, pb, evEbitda, roe, roce, roa, margin, debtToEquity, revenueGrowth, eps, bookValue, dividendYield, promoterHolding (plus forwardPe and beta when Yahoo's profile answers). =WEBSERVICE is in Excel for Windows and LibreOffice (as WEBSERVICE). Google Sheets fetches from Google's servers, so it can't reach this computer.</p>`;
  const list = rows(sym);
  body.querySelectorAll('[data-copy]').forEach(b => b.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(list[+b.dataset.copy][1]); toast('Copied'); } catch (e) { toast("Couldn't copy: select the text instead", 'error'); }
  }));
}

registerTab('excel', 'Excel', render, { title: 'Live values in Excel: =WEBSERVICE formulas and CSV links' });
