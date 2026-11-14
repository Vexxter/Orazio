// Insights › Find (:FIND): screen ~1,100 NSE stocks by asking in plain English ("debt free companies with ROCE above
// 20"), or start from one of NSE's ready-made screens. Shows how the question was read, so the screen is never a black
// box, and offers looser/stricter versions. Typing a screening sentence in the search box lands here too.
// Data: /api/deep (orazio/deep.py: the same reading as the toolbar's Deep search; falls back to MarketLens's builder) and
// /api/screens (NSE's ready-made screens, which are MarketLens expressions and still run as typed).
import { readBack, resultTable, summary } from './deep-search.js';
import { esc } from './format.js';
import { openInsights, redraw, registerTab } from './insights.js';

const KEY = 'orazio.find.v1';
const EXAMPLES = ['debt free companies with ROCE above 20', 'high dividend yield and low PE', 'stocks near 52 week high with market cap above 10000 crore',
  'promoter holding above 70 and debt to equity below 0.1', 'golden cross stocks with price above their 50 DMA'];
let q = '', presets = null, category = null;
try { q = localStorage.getItem(KEY) || ''; } catch (e) { /* none */ }
const nf = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 });
const nf0 = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 });
const v = (x, f = nf, suf = '') => (x === null || x === undefined ? '–' : `${f.format(x)}${suf}`);
const sign = (x) => (x > 0 ? 'up' : x < 0 ? 'down' : '');

function ask(text) {
  q = text.trim();
  try { localStorage.setItem(KEY, q); } catch (e) { /* not kept */ }
  redraw();
}

function results(d) {
  if (!d) return '';
  if (d.funnel || d.clauses?.length) return `${readBack(d, { counts: d.funnel })}${summary(d)}${resultTable(d)}`;   // deep search's reading
  if (!d.available) return `<div class="empty-note">${esc(d.reason || 'No answer.')}</div>`;
  const read = (d.readAs || []).map(r => `<li>${esc(r)}</li>`).join('');
  const sugg = (d.suggestions || []).slice(0, 4).map(s => `<button type="button" class="pick" data-q="${esc(s.query)}">${esc(s.label)}</button>`).join('');
  return `<div class="find-read"><code class="num">${esc(d.query)}</code>${read ? `<ul>${read}</ul>` : ''}${sugg ? `<div class="chips">${sugg}</div>` : ''}</div>
    <p class="ins-note"><b>${nf0.format(d.count)}</b> of ${nf0.format(d.universe)} stocks match${d.count > d.rows.length ? `; the ${d.rows.length} largest shown` : ''}. Click a row to chart it.</p>
    ${d.rows.length ? `<table class="opt-table"><thead><tr><th style="text-align:left">Company</th><th>Price</th><th>Day</th><th>Mkt cap ₹ Cr</th><th>P/E</th><th>P/B</th><th>ROCE</th><th>Div yield</th><th>Promoter</th><th>1Y</th></tr></thead><tbody>${
      d.rows.map(r => `<tr data-symbol="${esc(r.chartSymbol)}" tabindex="0" role="button"><td style="text-align:left"><strong>${esc(r.symbol)}</strong> <span class="ins-note">${esc(r.name || '')} · ${esc(r.sector || '')}</span></td>
        <td>${v(r.price)}</td><td class="${sign(r.change)}">${v(r.change, nf, '%')}</td><td>${v(r.marketCapCr, nf0)}</td><td>${v(r.pe)}</td><td>${v(r.pb)}</td>
        <td>${v(r.roce, nf, '%')}</td><td>${v(r.divYield, nf, '%')}</td><td>${v(r.promoter, nf, '%')}</td><td class="${sign(r.ret1y)}">${v(r.ret1y, nf, '%')}</td></tr>`).join('')}</tbody></table>` : ''}`;
}

async function render(body, ctx) {
  presets ||= fetch('/api/screens').then(r => r.json()).then(d => d.presets || []).catch(() => []);
  const [list, d] = await Promise.all([presets, q ? fetch(`/api/deep?q=${encodeURIComponent(q)}`).then(r => r.json()) : null]);
  if (ctx.stale()) return;
  ctx.pill(d?.available ? `${d.count} matches` : 'NSE MarketLens', !!d?.available);
  const cats = [...new Set(list.map(p => p.category).filter(Boolean))];
  category ||= cats[0];
  body.innerHTML = `<form class="find-ask" id="find-form"><input class="ins-input" id="find-q" value="${esc(q)}" placeholder="Ask in plain English: debt free companies with ROCE above 20" aria-label="Describe the stocks you want" autocomplete="off"><button type="submit" class="btn primary">Screen</button></form>
    ${q ? '' : `<div class="chips">${EXAMPLES.map(e => `<button type="button" class="pick" data-q="${esc(e)}">${esc(e)}</button>`).join('')}</div>`}
    ${results(d)}
    ${list.length ? `<div class="ins-sec"><h3>NSE's ready-made screens</h3><div class="chips">${cats.map(c => `<button type="button" class="pick${c === category ? ' on' : ''}" data-cat="${esc(c)}">${esc(c)}</button>`).join('')}</div>
      <div class="find-presets">${list.filter(p => p.category === category).map(p => `<button type="button" class="find-preset" data-q="${esc(p.query)}"><b>${esc(p.name)}</b><span>${esc(p.description || '')}</span></button>`).join('')}</div></div>` : ''}
    <p class="ins-note">Orazio reads the question itself (sectors, ratios, growth, earnings, insider trades, 52-week highs) and runs it over ~1,100 NSE stocks; anything it can't place goes to NSE MarketLens or, if you set one up in Settings, your own model. Ratios are NSE's; a P/E of 0 counts as "no value", not cheap.</p>`;
  const input = body.querySelector('#find-q');
  body.querySelector('#find-form').addEventListener('submit', (e) => { e.preventDefault(); if (input.value.trim()) ask(input.value); });
  body.querySelectorAll('[data-q]').forEach(b => b.addEventListener('click', () => ask(b.dataset.q)));
  body.querySelectorAll('[data-cat]').forEach(b => b.addEventListener('click', () => { category = b.dataset.cat; redraw(); }));
  if (!q) input.focus();
}

registerTab('find', 'Find', render, { title: 'Screen NSE stocks in plain English' });
document.addEventListener('intent:screen', (e) => { q = e.detail; openInsights('find'); });
