// Recorded product demo (docs/demo.mp4, docs/demo.webp). To re-record: open the app at 1440x900, paste this
// file into the devtools console (or inject it), warm each Insights tab once, start a screen recording, then run
// window.__orazioDemo() — about 1:50. It only drives the UI; nothing is written except the usual layout settings.
// Orazio product demo: a directed tour with title cards and lower-third captions. Loaded into the page, then
// window.__orazioDemo() runs the whole sequence; window.__demoState tracks progress.
(() => {
  const $ = (id) => document.getElementById(id);
  const wait = (ms) => new Promise(r => setTimeout(r, ms));
  window.__demoState = 'loaded';

  // ---------- overlay layer ----------
  const css = document.createElement('style');
  css.textContent = `
  #demo-layer { position: fixed; inset: 0; z-index: 9999; pointer-events: none; font-family: Geist, Inter, system-ui, sans-serif; }
  #demo-card { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 18px;
    background: radial-gradient(1200px 600px at 50% 40%, #1a2440 0%, #0b0d13 55%, #07080b 100%); opacity: 0; transition: opacity .6s ease; color: #ecedef; text-align: center; }
  #demo-card.on { opacity: 1; }
  #demo-card .logo { display: flex; align-items: center; gap: 16px; font-size: 72px; font-weight: 700; letter-spacing: -2px; }
  #demo-card .logo svg { width: 72px; height: 72px; stroke: #6e9cff; }
  #demo-card .tag { font-size: 30px; font-weight: 600; letter-spacing: -.5px; }
  #demo-card .sub { font-size: 18px; color: #a2a6af; letter-spacing: .3px; }
  #demo-card .cmd { margin-top: 10px; font: 500 17px 'Geist Mono', ui-monospace, monospace; color: #6e9cff; background: rgba(110,156,255,.1); border: 1px solid rgba(110,156,255,.35); padding: 10px 18px; border-radius: 10px; }
  #demo-card .pills { display: flex; gap: 10px; flex-wrap: wrap; justify-content: center; max-width: 900px; }
  #demo-card .pills span { font-size: 14px; color: #ecedef; border: 1px solid #2a2f3a; background: #12151c; padding: 6px 12px; border-radius: 999px; }
  #demo-cap { position: absolute; left: 50%; bottom: 46px; transform: translate(-50%, 16px); opacity: 0; transition: opacity .45s ease, transform .45s ease;
    background: rgba(10,12,17,.88); backdrop-filter: blur(10px); border: 1px solid #2a2f3a; border-left: 4px solid #6e9cff; border-radius: 12px;
    padding: 14px 24px 16px; box-shadow: 0 20px 60px rgba(0,0,0,.55); max-width: 900px; }
  #demo-cap.on { opacity: 1; transform: translate(-50%, 0); }
  #demo-cap .k { font: 600 12px 'Geist Mono', ui-monospace, monospace; letter-spacing: 2px; color: #6e9cff; text-transform: uppercase; }
  #demo-cap .h { font-size: 26px; font-weight: 600; color: #fff; letter-spacing: -.4px; margin-top: 4px; white-space: nowrap; }
  .demo-ring { position: fixed; z-index: 9998; pointer-events: none; border: 2px solid #6e9cff; border-radius: 10px; box-shadow: 0 0 0 6px rgba(110,156,255,.18);
    animation: demo-pulse .9s ease-out forwards; }
  @keyframes demo-pulse { 0% { opacity: 0; transform: scale(1.25); } 30% { opacity: 1; transform: scale(1); } 100% { opacity: 0; transform: scale(1); } }
  #demo-progress { position: absolute; left: 0; bottom: 0; height: 3px; background: #6e9cff; width: 0; transition: width .5s linear; }`;
  document.head.appendChild(css);
  const layer = document.createElement('div');
  layer.id = 'demo-layer';
  layer.innerHTML = '<div id="demo-card"></div><div id="demo-cap"><div class="k"></div><div class="h"></div></div><div id="demo-progress"></div>';
  document.body.appendChild(layer);
  const logoSvg = document.querySelector('.brand svg')?.outerHTML || '';

  async function card(html, ms, hold = false) {
    const c = $('demo-card');
    c.innerHTML = html;
    c.classList.add('on');
    await wait(ms);
    if (hold) return;
    c.classList.remove('on');
    await wait(600);
  }
  function caption(kicker, headline) {
    const c = $('demo-cap');
    c.classList.remove('on');
    setTimeout(() => {
      c.querySelector('.k').textContent = kicker;
      c.querySelector('.h').textContent = headline;
      c.classList.add('on');
    }, kicker ? 250 : 0);
  }
  const hideCaption = () => $('demo-cap').classList.remove('on');
  function ring(el) {
    if (!el) return;
    const r = el.getBoundingClientRect();
    const d = document.createElement('div');
    d.className = 'demo-ring';
    Object.assign(d.style, { left: `${r.left - 6}px`, top: `${r.top - 6}px`, width: `${r.width + 12}px`, height: `${r.height + 12}px` });
    document.body.appendChild(d);
    setTimeout(() => d.remove(), 1000);
  }
  async function click(el, pause = 450) { ring(el); await wait(pause); el?.click(); }
  async function type(input, text, perChar = 75) {
    ring(input);
    input.focus();
    input.value = '';
    for (const ch of text) { input.value += ch; input.dispatchEvent(new Event('input')); await wait(perChar); }
    await wait(350);
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
  }
  const body = () => $('insights-body');
  // Hold until the tab has drawn real content (not "Loading…"), at most `max` ms.
  async function ready(max = 9000) {
    const t0 = Date.now();
    while (Date.now() - t0 < max) {
      const t = body().innerText;
      if (t.length > 80 && !t.includes('Loading…')) return;
      await wait(150);
    }
  }
  const tab = async (id) => { await click(document.querySelector(`#insights-tabs [data-tab="${id}"]`), 350); await ready(); };
  async function smoothScroll(el, to, ms) {
    const from = el.scrollTop, t0 = performance.now();
    while (true) {
      const p = Math.min(1, (performance.now() - t0) / ms);
      el.scrollTop = from + (to - from) * (0.5 - Math.cos(Math.PI * p) / 2);
      if (p >= 1) break;
      await new Promise(r => requestAnimationFrame(r));
    }
  }
  const closeInsights = () => { if ($('insights-modal').classList.contains('open')) $('insights-close').click(); };
  let shot = 0;
  const TOTAL = 17;
  const progress = () => { $('demo-progress').style.width = `${(++shot / TOTAL) * 100}%`; };

  window.__orazioDemo = async function () {
    window.__demoState = 'running';
    try {
      // 0. Cold open
      await card(`<div class="logo">${logoSvg}Orazio</div><div class="tag">The market terminal you own.</div>
        <div class="sub">Indian and global markets · live · free · runs on your machine</div>`, 3600);

      // 1. Live chart
      progress();
      caption('Live charts', 'Every market, pushed live. No login. No API keys.');
      await wait(4200);

      // 2. Command line
      progress();
      caption('Command line', 'Type a function. Get the answer.');
      await wait(900);
      await type($('symbol-input'), 'NIFTY OPT', 110);
      await wait(400);
      await ready();
      await wait(1800);

      // 3. Options analytics
      progress();
      caption('Options analytics', 'Dealer gamma, the flip level, call and put walls.');
      await wait(2600);
      await smoothScroll(body(), 900, 2200);
      caption('Options analytics', 'IV smile and the full term structure, live from NSE.');
      await smoothScroll(body(), body().scrollHeight, 1600);
      await wait(1400);

      // 4. Brief
      progress();
      await tab('brief');
      caption('The brief', 'Your whole morning on one screen.');
      await wait(4200);

      // 5. Flows
      progress();
      await tab('flows');
      caption('Institutional flows', 'Who is long? FII, DII, Pro and Client positioning.');
      await wait(2200);
      await smoothScroll(body(), 520, 1800);
      await wait(1200);

      // 6. Rotation
      progress();
      await tab('rotation');
      caption('Sector rotation', 'Which sectors are leading NIFTY, week by week.');
      await wait(4400);

      // 7. Correlation
      progress();
      await tab('correlation');
      caption('Cross-asset', 'Correlation and beta across stocks, rates, FX, crude and crypto.');
      await wait(4000);

      // 8. Seasonality
      progress();
      await tab('seasonality');
      caption('Seasonality', 'Nineteen years of NIFTY, by month and by weekday.');
      await wait(3800);

      // 9. Event study
      progress();
      await tab('events');
      await wait(500);
      const kind = $('ev-kind');
      if (kind) { ring(kind); kind.value = 'cut'; kind.dispatchEvent(new Event('change')); await wait(300); await ready(); }
      caption('Event study', 'What does NIFTY do after an RBI rate cut? Measured.');
      await wait(4000);

      // 10. Rates
      progress();
      await tab('rates');
      caption('Rates', 'Scrub the yield curve back five years.');
      await wait(2600);
      await smoothScroll(body(), 260, 700);
      const slider = $('rates-day');
      if (slider) {
        ring(slider);
        const max = +slider.max, target = Math.floor(max * 0.33);
        for (let i = 0; i <= 40; i++) {
          slider.value = String(Math.round(max - (max - target) * (i / 40)));
          slider.dispatchEvent(new Event('input'));
          await wait(60);
        }
      }
      caption('Rates', '2023: the deepest US curve inversion in decades.');
      await wait(2600);

      // 11. Alerts with backtest
      progress();
      await tab('alerts');
      await wait(600);
      caption('Alerts', 'Backtest an alert before you trust it.');
      const b = body();
      b.querySelector('#al-sym').value = 'NIFTY';
      ring(b.querySelector('#al-type'));
      b.querySelector('#al-type').value = 'chgDown';
      await wait(500);
      await type(b.querySelector('#al-val'), '2', 120);
      await click(b.querySelector('#al-test'), 400);
      await wait(3600);

      // 12. Grid
      progress();
      closeInsights();
      hideCaption();
      await wait(300);
      await click($('grid-btn'), 400);
      for (let t0 = Date.now(); Date.now() - t0 < 9000 && [...document.querySelectorAll('.gp-px')].some(e => !e.textContent); ) await wait(150);
      caption('Multi-chart', 'One symbol, four timeframes, crosshairs linked.');
      await wait(4600);
      $('grid-close').click();

      // 13. Compare with a formula
      progress();
      await wait(300);
      if ($('compare-wrap').hidden) await click($('compare-btn'), 400);
      await wait(800);
      caption('Formulas', 'Chart any ratio or spread. NIFTY ÷ BANKNIFTY.');
      await type($('compare-input'), 'NIFTY / BANKNIFTY', 70);
      await wait(3600);
      $('compare-close').click();

      // 14. Events on the chart
      progress();
      caption('Events on the chart', 'Results, dividends and block deals, right on the candles.');
      await type($('symbol-input'), 'RELIANCE 1D', 80);
      await wait(1800);
      document.querySelector('#range-bar button[data-range="1Y"]')?.click();
      await wait(1200);
      const ev = $('events-toggle');
      if (ev && !ev.checked) { ring(ev.closest('label')); await wait(400); ev.click(); }
      await wait(3600);

      // 15. Bar replay
      progress();
      caption('Bar replay', 'Rewind the market. Trade it again, bar by bar.');
      await click($('replay-btn'), 400);
      await wait(500);
      // The price pane's top canvas (the largest canvas, last of its stacked pair) takes the click.
      const all = [...document.querySelectorAll('#chart canvas')];
      const area = (c) => { const r = c.getBoundingClientRect(); return r.width * r.height; };
      const big = Math.max(...all.map(area));
      const cv = all.filter(c => area(c) === big).at(-1);
      if (cv) {
        const r = cv.getBoundingClientRect();
        const x = r.left + r.width * 0.35, y = r.top + r.height * 0.5;
        const opt = { bubbles: true, clientX: x, clientY: y, button: 0, view: window };
        cv.dispatchEvent(new MouseEvent('mousedown', opt));
        document.dispatchEvent(new MouseEvent('mouseup', opt));
        cv.dispatchEvent(new MouseEvent('mouseup', opt));
      }
      await wait(600);
      const speed = $('replay-speed');
      if (speed?.options.length) { speed.value = speed.options[speed.options.length - 1].value; speed.dispatchEvent(new Event('change')); }
      await click($('replay-play'), 300);
      await wait(4200);
      $('replay-exit')?.click();
      await wait(300);

      // 16. Watchlist
      progress();
      caption('Watchlist', 'Your symbols with RSI, 52-week range, volume and delivery.');
      await type($('symbol-input'), ':WL', 120);
      await wait(400);
      await ready();
      await wait(4200);
      closeInsights();

      // 17. Outro
      progress();
      hideCaption();
      await wait(400);
      await card(`<div class="logo">${logoSvg}Orazio</div><div class="tag">Free. Open source. Yours.</div>
        <div class="pills"><span>Options analytics</span><span>Institutional flows</span><span>Sector rotation</span><span>Correlation</span><span>Seasonality</span><span>Event studies</span><span>Yield curves</span><span>RBI liquidity</span><span>Alerts + backtests</span><span>Command line</span><span>Closing auction</span><span>Bar replay</span></div>
        <div class="cmd">pip install -r requirements.txt &nbsp;·&nbsp; python app.py</div>`, 5200, true);
      window.__demoState = 'done';
    } catch (e) {
      window.__demoState = `error: ${e.message}`;
    }
  };
})();
