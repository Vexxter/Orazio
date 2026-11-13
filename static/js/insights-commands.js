// Insights › Commands: every command-line function (command-parse.js), with its aliases. Click a row to run it
// on the symbol now on the chart.
import { FUNCTIONS } from './command-parse.js';
import { runCommand } from './command.js';
import { esc } from './format.js';
import { registerTab } from './insights.js';
import { state } from './state.js';

async function render(body, ctx) {
  ctx.pill('');
  body.innerHTML = `<p class="ins-note">Type in the symbol search and press Enter: <b>NIFTY OPT</b>, <b>RELIANCE SEAS</b>, <b>BANKNIFTY 5M</b>, <b>NIFTY CMP SPX</b>, <b>NIFTY CMP IN10Y-IN - US10Y</b>. A function on its own needs a colon: <b>:FLOW</b>. Press <b>:</b> anywhere to start one.</p>
    <table class="opt-table"><thead><tr><th>Function</th><th>Also</th><th style="text-align:left">What it opens</th><th>Example</th></tr></thead><tbody>${
      Object.entries(FUNCTIONS).map(([k, [, desc, aliases]]) => `<tr class="cmd-row" data-fn="${esc(k)}" tabindex="0" role="button"><td>${esc(k)}</td><td>${esc(aliases.join(', ') || '–')}</td><td style="text-align:left">${esc(desc)}</td><td>${esc(k === 'CMP' ? 'NIFTY CMP SPX' : `${state.currentSymbol} ${k}`)}</td></tr>`).join('')
    }</tbody></table>`;
  body.querySelectorAll('.cmd-row').forEach(tr => tr.addEventListener('click', () => {
    if (tr.dataset.fn !== 'HELP') runCommand({ fn: tr.dataset.fn, symbol: null, arg: tr.dataset.fn === 'CMP' ? 'SPX' : null, interval: null });
  }));
}

registerTab('commands', 'Commands', render, { title: 'Command-line functions' });
