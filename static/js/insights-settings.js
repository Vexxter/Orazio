// Insights › Settings: where alerts go, the morning brief, and how to use Orazio from Claude. Stored only on this machine in
// ~/.orazio/settings.json. Secrets are never sent back to this page; a blank secret field keeps what's stored.
import { esc } from './format.js';
import { redraw, registerTab } from './insights.js';
import { toast } from './ui.js';

const post = (url, body) => fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  .then(async r => { const d = await r.json().catch(() => ({})); if (!r.ok) throw new Error(d.error || `HTTP ${r.status}`); return d; });

const text = (k, label, s, ph = '', w = 260) => `<label class="set-row"><span>${esc(label)}</span><input class="ins-input" data-k="${k}" value="${esc(s[k])}" placeholder="${esc(ph)}" style="width:${w}px"></label>`;
const secret = (k, label, s) => `<label class="set-row"><span>${esc(label)}</span><input class="ins-input" type="password" autocomplete="off" data-k="${k}" placeholder="${s[k] ? 'Saved. Leave blank to keep' : 'Not set'}" style="width:260px">${s[k] ? ` <button type="button" class="btn" data-clear="${k}">Remove</button>` : ''}</label>`;
const check = (k, label, s) => `<label class="set-row"><input type="checkbox" data-k="${k}"${s[k] ? ' checked' : ''}> <span>${esc(label)}</span></label>`;

// Every deep-search model use since Orazio started, newest first (cache hits included, marked as no new call).
function llmLog(d) {
  const calls = d?.calls || [];
  if (!calls.length) return `<p class="ins-note">None yet${d?.provider === 'off' ? ': the model fallback is off' : ''}.</p>`;
  return `<table class="opt-table"><thead><tr><th>When</th><th>Model</th><th>Question</th><th>Call</th><th>Result</th></tr></thead><tbody>${calls.map(c => `<tr>
    <td>${esc(c.at.slice(11))}</td><td>${esc(c.source)}</td><td style="text-align:left">${esc(c.question)}</td>
    <td>${c.cached ? 'cached, no call' : `${c.seconds} s`}</td>
    <td class="${c.ok ? 'up' : 'down'}">${c.ok ? `${c.clauses} clause(s)${c.rejected ? `, ${c.rejected} thrown away` : ''}` : esc(c.error || 'nothing usable')}</td></tr>`).join('')}</tbody></table>`;
}

async function render(body, ctx) {
  const [s, log] = await Promise.all([fetch('/api/settings').then(r => r.json()), fetch('/api/deep/llm-log').then(r => r.json()).catch(() => null)]);
  if (ctx.stale()) return;
  ctx.pill('Stored on this machine', true);
  body.innerHTML = `<div class="ins-grid2">
    <div class="ins-sec"><h3>Where alerts go</h3>
      ${check('desktop', 'Desktop notification', s)}
      ${secret('telegramToken', 'Telegram bot token', s)}${text('telegramChat', 'Telegram chat ID', s, '123456789')}
      ${text('webhookUrl', 'Webhook URL (gets a JSON POST)', s, 'https://…')}
      ${text('smtpHost', 'Email: SMTP host', s, 'smtp.gmail.com')}${text('smtpPort', 'SMTP port', s, '587', 90)}${text('smtpUser', 'SMTP user', s)}${secret('smtpPassword', 'SMTP password', s)}${text('emailTo', 'Send to', s)}
      <p class="ins-note">Alerts run while Orazio runs, so start it at login to keep them on. Nothing is sent to a channel you leave blank.</p></div>
    <div><div class="ins-sec"><h3>Morning brief</h3>
      ${check('briefEnabled', 'Send a short brief on weekdays', s)}${text('briefTime', 'At (IST)', s, '09:00', 90)}</div>
    <div class="ins-sec"><h3>Use it from Claude, on your own plan</h3>
      <p class="ins-note">Ask Claude Code or Claude Desktop about live data and filings. Add Orazio once in a terminal, from this folder:</p>
      <pre class="set-code">claude mcp add --transport stdio orazio -- python ${esc('"$PWD/scripts/orazio_mcp.py"')}</pre>
      <p class="ins-note">Then ask, for example, <b>“Summarise TCS's latest filing, with page numbers.”</b> Orazio never sees your Claude login. What Claude reads through these tools is sent to Anthropic under your plan, and counts toward its limits.</p></div>
    <div class="ins-sec"><h3>Deep search: a model for the words the rules miss</h3>
      <label class="set-row"><span>Use</span><select class="select" data-k="llmProvider">${[['off', 'Off: rules only'], ['claude', 'Claude app (claude CLI, your plan)'], ['codex', 'Codex (codex CLI, your plan)'], ['openai', 'Local or OpenAI-compatible server']]
        .map(([k, l]) => `<option value="${k}"${s.llmProvider === k ? ' selected' : ''}>${esc(l)}</option>`).join('')}</select></label>
      ${text('llmBaseUrl', 'Server (for the last option)', s, 'ollama, lmstudio, llamacpp, openrouter or http://…/v1')}
      ${text('llmModel', 'Model (blank: the CLI default)', s, 'qwen2.5:7b, haiku, gpt-5-mini…')}
      ${secret('llmApiKey', 'API key (OpenRouter only)', s)}
      <div class="ins-bar"><button type="button" class="btn" id="llm-test">Save and test</button><span class="ins-note" id="llm-result"></span></div>
      <p class="ins-note">The rules read most questions instantly. Only words they can't place go to the model, which picks from Orazio's own fields and sectors; anything else it returns is thrown away. A CLI runs on your own login; a local server never leaves this machine. Every result says whether a model was used; Alt+Enter in Deep search skips the model for one search.</p>
      <h3>Model calls this session</h3><div id="llm-log">${llmLog(log)}</div></div></div></div>
    <div class="ins-bar"><button type="button" class="btn primary" id="set-save">Save</button><button type="button" class="btn" id="set-test">Save and send a test</button><span class="ins-note" id="set-result"></span></div>`;

  const save = async () => {
    const changes = {};
    body.querySelectorAll('[data-k]').forEach(i => { changes[i.dataset.k] = i.type === 'checkbox' ? i.checked : i.dataset.k === 'smtpPort' ? Number(i.value) : i.value.trim(); });
    await post('/api/settings', changes);
  };
  body.querySelector('#set-save').addEventListener('click', async () => {
    try { await save(); toast('Saved'); redraw(); } catch (e) { toast(e.message, 'error'); }
  });
  body.querySelector('#set-test').addEventListener('click', async () => {
    try {
      await save();
      const out = await post('/api/notify/test', {});
      const parts = Object.entries(out).map(([k, v]) => `${k}: ${v}`);
      body.querySelector('#set-result').textContent = parts.join(' · ') || 'No channel is turned on.';
    } catch (e) { toast(e.message, 'error'); }
  });
  body.querySelector('#llm-test').addEventListener('click', async () => {
    const out = body.querySelector('#llm-result');
    try {
      await save();
      out.textContent = 'Asking the model…';
      const d = await post('/api/deep/llm-test', {});
      out.textContent = d.ok ? `Works (${d.seconds} s): ${d.clauses.join('; ')}` : `Didn't work: ${d.error || 'no usable answer'}`;
    } catch (e) { toast(e.message, 'error'); }
  });
  body.querySelectorAll('[data-clear]').forEach(b => b.addEventListener('click', async (e) => {
    e.preventDefault();
    try { await post('/api/settings/clear', { key: b.dataset.clear }); redraw(); } catch (err) { toast(err.message, 'error'); }
  }));
}

registerTab('settings', 'Settings', render, { title: 'Notification channels, morning brief, using Orazio from Claude' });
