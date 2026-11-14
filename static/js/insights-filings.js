// Insights › Filings: NSE corporate announcements for your watchlist or the whole market, filtered by phrase, with
// each filing's PDF one click away. Saved phrases notify through your channels even with this page closed.
import { esc } from './format.js';
import { redraw, registerTab } from './insights.js';
import { toast } from './ui.js';
import { watchlistSymbols } from './insights-watchlist.js';

const KEY = 'orazio.filings.v1';
let cfg = { scope: 'watchlist', q: '' };
try { cfg = { ...cfg, ...JSON.parse(localStorage.getItem(KEY) || '{}') }; } catch (e) { /* defaults */ }
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(cfg)); } catch (e) { /* not persisted */ } };

const stocks = () => watchlistSymbols().filter(s => s.endsWith('.NS'));
const post = (url, body) => fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  .then(async r => { const d = await r.json().catch(() => ({})); if (!r.ok) throw new Error(d.error || `HTTP ${r.status}`); return d; });

function rowHtml(r) {
  return `<tr><td style="white-space:nowrap">${esc((r.time || '').slice(5, 16))}</td>
    <td style="text-align:left" data-symbol="${esc(r.chartSymbol)}" tabindex="0" role="button"><strong>${esc(r.symbol)}</strong></td>
    <td style="text-align:left"><b>${esc(r.category)}</b> <span class="ins-note">${esc(r.text.slice(0, 220))}</span></td>
    <td style="white-space:nowrap">${r.pdf ? `<a href="${esc(r.pdf)}" target="_blank" rel="noopener noreferrer">PDF</a>` : '–'}</td></tr>`;
}

async function render(body, ctx) {
  const symbols = cfg.scope === 'watchlist' ? stocks() : [];
  const nothingToAsk = cfg.scope === 'watchlist' && !symbols.length;   // an empty symbol filter would mean the whole market
  const [d, a] = await Promise.all([
    nothingToAsk ? { available: true, rows: [] } : fetch(`/api/filings?symbols=${encodeURIComponent(symbols.join(','))}&q=${encodeURIComponent(cfg.q)}`).then(r => r.json()),
    fetch('/api/alerts').then(r => r.json()).catch(() => ({ filingWatch: { keywords: [] } })),
  ]);
  if (ctx.stale()) return;
  ctx.pill(d.available ? `${d.rows.length} filings · last 3 days` : 'NSE unavailable', d.available);
  const kw = a.filingWatch?.keywords || [];
  const empty = !d.available ? "NSE didn't answer. It will retry." : cfg.scope === 'watchlist' && !symbols.length ? 'No NSE stocks on your watchlist. Switch to All NSE or add some.' : 'No filings match.';
  body.innerHTML = `<div class="ins-bar">
      <select class="select" id="fil-scope" aria-label="Which stocks"><option value="watchlist"${cfg.scope === 'watchlist' ? ' selected' : ''}>My watchlist</option><option value="all"${cfg.scope === 'all' ? ' selected' : ''}>All NSE</option></select>
      <input class="ins-input" id="fil-q" value="${esc(cfg.q)}" placeholder="Filter: transcript, results, pledge" style="width:260px" aria-label="Filter by phrases, separated by commas">
      <input class="ins-input" id="fil-watch" value="${esc(kw.join(', '))}" placeholder="Alert me on: order win, resignation" style="width:280px" aria-label="Alert phrases, separated by commas">
      <button type="button" class="btn primary" id="fil-save">Save alerts</button></div>
    <p class="ins-note">Alert phrases are checked every 5 minutes while Orazio runs${symbols.length ? ', for your watchlist stocks' : ', for every NSE stock'}. Filing text comes from the companies, not from Orazio.</p>
    ${d.rows.length ? `<table class="opt-table"><tbody>${d.rows.map(rowHtml).join('')}</tbody></table>` : `<div class="empty-note">${esc(empty)}</div>`}`;
  body.querySelector('#fil-scope').addEventListener('change', (e) => { cfg.scope = e.target.value; save(); redraw(); });
  body.querySelector('#fil-q').addEventListener('change', (e) => { cfg.q = e.target.value; save(); redraw(); });
  body.querySelector('#fil-save').addEventListener('click', async () => {
    const keywords = body.querySelector('#fil-watch').value.split(',').map(s => s.trim()).filter(Boolean);
    try {
      await post('/api/filings/watch', { keywords, symbols: symbols.map(s => s.split('.')[0]) });
      toast(keywords.length ? `Watching ${keywords.length} phrase${keywords.length > 1 ? 's' : ''}` : 'Filing alerts off');
    } catch (e) { toast(e.message, 'error'); }
  });
}

registerTab('filings', 'Filings', render, { pollMs: 60000, title: 'Corporate filings with keyword alerts' });
