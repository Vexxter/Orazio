// First visit only: pick how you trade and land on a layout built for it, with the matching view open. Opens links with
// ?cmd=NIFTY%20OPT too, which is how notifications and shared links reach a view directly.
import { runTyped } from './command.js';
import { $, esc } from './state.js';
import { loadWorkspace } from './insights-workspaces.js';
import { PRESETS } from './workspace-store.js';

const KEY = 'orazio.welcome.v1';
const CHOICES = [
  ['Expiry day', 'Options and index trading', 'NIFTY and BANKNIFTY on a 1m/5m grid, with gamma exposure and OI by strike.', 'NIFTY OPT'],
  ['Pre-open', 'Positioning for the open', 'GIFT Nifty against NIFTY, with the cross-asset brief.', ':BRIEF'],
  ['Bond desk', 'Rates and macro', 'India 10Y against US 10Y, with the yield curve.', ':RATES'],
];

function show() {
  const el = document.createElement('div');
  el.className = 'backdrop open';
  el.id = 'welcome-modal';
  el.innerHTML = `<div class="modal welcome-modal" role="dialog" aria-modal="true" aria-labelledby="welcome-title">
    <h2 id="welcome-title">What are you here to do?</h2>
    <p class="ins-note">No account, nothing to pay. It all runs on this machine from public exchange data. Pick a starting layout; you can change it any time.</p>
    <div class="welcome-choices">${CHOICES.map(([k, title, desc, cmd]) => `<button type="button" class="welcome-choice" data-ws="${esc(k)}"><b>${esc(title)}</b><span>${esc(desc)}</span><code>${esc(cmd)}</code></button>`).join('')}</div>
    <div class="welcome-foot"><button type="button" class="btn primary" id="welcome-tour">Take the 60-second tour</button><button type="button" class="btn" id="welcome-skip">Just show me the chart</button></div>
    <p class="ins-note">Type <b>:</b> anywhere for the command line, and press <b>?</b> for the one-page cheat sheet. Data can be delayed or wrong: <b>:SRC</b> shows each feed's source, delay and health. Not financial advice.</p>
  </div>`;
  document.body.appendChild(el);
  const done = () => { try { localStorage.setItem(KEY, '1'); } catch (e) { /* asks again next time */ } };
  el.querySelectorAll('[data-ws]').forEach(b => b.addEventListener('click', () => { done(); const p = PRESETS[b.dataset.ws]; loadWorkspace(p.snap, p.tab); }));
  const skip = () => { done(); el.remove(); $('symbol-input').focus(); };
  $('welcome-skip').addEventListener('click', skip);
  $('welcome-tour').addEventListener('click', () => { done(); el.remove(); document.dispatchEvent(new CustomEvent('tour')); });
  el.addEventListener('keydown', (e) => { if (e.key === 'Escape') skip(); });
  el.querySelector('[data-ws]').focus();
}

const cmd = new URLSearchParams(location.search).get('cmd');
if (cmd) {
  history.replaceState(null, '', location.pathname);   // a reload shouldn't run it again
  setTimeout(() => runTyped(cmd), 800);
} else {
  let seen = '1';
  try { seen = localStorage.getItem(KEY) || (localStorage.getItem('orazio.prefs.v1') ? '1' : null); } catch (e) { /* no storage: don't nag */ }
  if (!seen) show();   // existing users have saved prefs: they never see this
}
