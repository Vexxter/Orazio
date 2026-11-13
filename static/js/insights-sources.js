// Insights › Sources: every feed, where it comes from, how late it runs and whether it last worked. Health is what
// the app has already seen; "Check all feeds" calls each one in turn, so a dead feed shows as dead rather than as
// a broken page. Registry: orazio/provenance.py.
import { esc } from './format.js';
import { redraw, registerTab } from './insights.js';

let checking = false;
const failing = (f) => f.error && (!f.okAt || f.failAt > f.okAt);
const ago = (t) => { const s = Math.max(0, Math.round(Date.now() / 1000 - t)); return s < 90 ? `${s}s ago` : s < 5400 ? `${Math.round(s / 60)}m ago` : `${Math.round(s / 3600)}h ago`; };

function status(f) {
  if (failing(f)) return `<span class="down">Failing · ${esc(f.error)}</span>`;
  return f.okAt ? `<span class="up">OK · ${esc(ago(f.okAt))}</span>` : '<span class="dim">Not used yet</span>';
}

async function checkAll(feeds) {
  checking = true;
  redraw();
  for (const f of feeds.filter(x => x.probe)) await fetch(f.probe).catch(() => null);   // one at a time: go easy on the sources
  checking = false;
  redraw();
}

async function render(body, ctx) {
  const { feeds } = await fetch('/api/sources').then(r => r.json());
  if (ctx.stale()) return;
  const bad = feeds.filter(failing).length;
  ctx.pill(bad ? `${bad} failing` : `${feeds.filter(f => f.okAt).length} of ${feeds.length} seen working`, !bad);
  body.innerHTML = `<div class="ins-bar"><button type="button" class="btn primary" id="src-check"${checking ? ' disabled' : ''}>${checking ? 'Checking, about a minute…' : 'Check all feeds'}</button>
      <span class="ins-note">Every data response from this app also carries a <code>provenance</code> object with these fields.</span></div>
    <table class="opt-table"><thead><tr><th style="text-align:left">Data</th><th style="text-align:left">Source</th><th style="text-align:left">Delay</th><th style="text-align:left">Units</th><th style="text-align:left">Last result</th></tr></thead><tbody>${
      feeds.map(f => `<tr><td style="text-align:left">${esc(f.label)}</td><td style="text-align:left"><a href="${esc(f.url)}" target="_blank" rel="noopener noreferrer">${esc(f.source)}</a></td><td style="text-align:left">${esc(f.delay)}</td><td style="text-align:left">${esc(f.units)}</td><td style="text-align:left">${status(f)}</td></tr>`).join('')
    }</tbody></table>`;
  body.querySelector('#src-check').addEventListener('click', () => checkAll(feeds));
}

registerTab('sources', 'Sources', render, { pollMs: 15000, title: 'Where each number comes from, and feed health' });
