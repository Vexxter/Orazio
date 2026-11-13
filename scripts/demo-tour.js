// Recorded product demo (docs/demo.mp4, 7:20; docs/demo.webp is its first 80 s at 2x). A directed tour of every feature: a cold open, seven chapters with title
// cards, lower-third captions, a keystroke pill, and a progress bar. To re-record: open the app at 1440x900 with a
// watchlist of F&O stocks and a sample portfolio in localStorage (back yours up first), inject this file, run
// window.__orazioWarm() off camera so every view is cached, start a screen recording, then run window.__orazioDemo().
// About 7 minutes. It drives the UI only; each scene is isolated, so a slow feed skips one beat instead of derailing the take. window.__demoState tracks progress.
(() => {
  const $ = (id) => document.getElementById(id);
  const q = (sel, root = document) => root.querySelector(sel);
  const wait = (ms) => new Promise(r => setTimeout(r, ms));
  window.__demoState = 'loaded';

  // ---------- overlay layer ----------
  const css = document.createElement('style');
  css.textContent = `
  #demo-layer { position: fixed; inset: 0; z-index: 9999; pointer-events: none; font-family: Geist, Inter, system-ui, sans-serif; }
  #demo-card { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 18px;
    background: radial-gradient(1200px 640px at 50% 38%, #18233f 0%, #0b0d13 56%, #06070a 100%); opacity: 0; transition: opacity .7s ease; color: #ecedef; text-align: center; }
  #demo-card.on { opacity: 1; }
  #demo-card .logo { display: flex; align-items: center; gap: 16px; font-size: 76px; font-weight: 700; letter-spacing: -2.5px; }
  #demo-card .logo svg { width: 74px; height: 74px; stroke: #6e9cff; }
  #demo-card .tag { font-size: 34px; font-weight: 600; letter-spacing: -.8px; max-width: 980px; line-height: 1.2; }
  #demo-card .sub { font-size: 18px; color: #a2a6af; letter-spacing: .3px; max-width: 860px; line-height: 1.5; }
  #demo-card .num { font: 600 15px 'Geist Mono', ui-monospace, monospace; letter-spacing: 6px; color: #6e9cff; }
  #demo-card .chap { font-size: 58px; font-weight: 700; letter-spacing: -2px; }
  #demo-card .cmd { margin-top: 10px; font: 500 17px 'Geist Mono', ui-monospace, monospace; color: #6e9cff; background: rgba(110,156,255,.1); border: 1px solid rgba(110,156,255,.35); padding: 10px 18px; border-radius: 10px; }
  #demo-card .pills { display: flex; gap: 10px; flex-wrap: wrap; justify-content: center; max-width: 1080px; }
  #demo-card .pills span { font-size: 14px; color: #ecedef; border: 1px solid #2a2f3a; background: #12151c; padding: 6px 12px; border-radius: 999px; }
  #demo-card .rise { animation: demo-rise .9s cubic-bezier(.2,.8,.2,1) both; }
  #demo-card .rise.d1 { animation-delay: .15s; } #demo-card .rise.d2 { animation-delay: .3s; } #demo-card .rise.d3 { animation-delay: .45s; }
  @keyframes demo-rise { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: none; } }
  #demo-cap { position: absolute; left: 50%; bottom: 46px; transform: translate(-50%, 16px); opacity: 0; transition: opacity .45s ease, transform .45s ease;
    background: rgba(10,12,17,.9); backdrop-filter: blur(10px); border: 1px solid #2a2f3a; border-left: 4px solid #6e9cff; border-radius: 12px;
    padding: 14px 24px 16px; box-shadow: 0 20px 60px rgba(0,0,0,.55); max-width: 1000px; }
  #demo-cap.on { opacity: 1; transform: translate(-50%, 0); }
  #demo-cap .k { font: 600 12px 'Geist Mono', ui-monospace, monospace; letter-spacing: 2px; color: #6e9cff; text-transform: uppercase; }
  #demo-cap .h { font-size: 25px; font-weight: 600; color: #fff; letter-spacing: -.4px; margin-top: 4px; white-space: nowrap; }
  #demo-key { position: absolute; right: 40px; bottom: 50px; opacity: 0; transform: translateY(8px); transition: all .3s ease;
    font: 600 18px 'Geist Mono', ui-monospace, monospace; color: #fff; background: rgba(10,12,17,.9); border: 1px solid #3a4150; border-bottom-width: 3px; border-radius: 10px; padding: 8px 14px; }
  #demo-key.on { opacity: 1; transform: none; }
  .demo-ring { position: fixed; z-index: 9998; pointer-events: none; border: 2px solid #6e9cff; border-radius: 10px; box-shadow: 0 0 0 6px rgba(110,156,255,.18);
    animation: demo-pulse 1s ease-out forwards; }
  @keyframes demo-pulse { 0% { opacity: 0; transform: scale(1.2); } 30% { opacity: 1; transform: scale(1); } 100% { opacity: 0; transform: scale(1); } }
  #demo-chapter { position: absolute; left: 16px; bottom: 14px; padding: 6px 12px; border-radius: 999px; background: #0b0d13; border: 1px solid #2a2f3a; font: 600 11px 'Geist Mono', ui-monospace, monospace; letter-spacing: 2.5px; color: #a2a6af; text-transform: uppercase; opacity: 0; transition: opacity .5s; }
  #demo-chapter.on { opacity: 1; }
  #demo-progress { position: absolute; left: 0; bottom: 0; height: 3px; background: linear-gradient(90deg, #6e9cff, #9db8ff); width: 0; transition: width .6s linear; }`;
  document.head.appendChild(css);
  const layer = document.createElement('div');
  layer.id = 'demo-layer';
  layer.innerHTML = '<div id="demo-card"></div><div id="demo-cap"><div class="k"></div><div class="h"></div></div><div id="demo-key"></div><div id="demo-chapter"></div><div id="demo-progress"></div>';
  document.body.appendChild(layer);
  const logoSvg = q('.brand svg')?.outerHTML || '';

  async function card(html, ms, hold = false) {
    const c = $('demo-card');
    c.innerHTML = html;
    c.classList.add('on');
    await wait(ms);
    if (hold) return;
    c.classList.remove('on');
    await wait(700);
  }
  function caption(kicker, headline) {
    const c = $('demo-cap');
    c.classList.remove('on');
    setTimeout(() => {
      c.querySelector('.k').textContent = kicker;
      c.querySelector('.h').textContent = headline;
      c.classList.add('on');
    }, 260);
  }
  const hideCaption = () => $('demo-cap').classList.remove('on');
  async function key(label, ms = 900) { const k = $('demo-key'); k.textContent = label; k.classList.add('on'); await wait(ms); k.classList.remove('on'); }
  function ring(el) {
    if (!el) return;
    const r = el.getBoundingClientRect();
    const d = document.createElement('div');
    d.className = 'demo-ring';
    Object.assign(d.style, { left: `${r.left - 6}px`, top: `${r.top - 6}px`, width: `${r.width + 12}px`, height: `${r.height + 12}px` });
    document.body.appendChild(d);
    setTimeout(() => d.remove(), 1100);
  }
  async function click(el, pause = 450) { if (!el) return; ring(el); await wait(pause); el.click(); }
  async function type(input, text, perChar = 70, enter = true) {
    if (!input) return;
    ring(input);
    input.focus();
    input.value = '';
    for (const ch of text) { input.value += ch; input.dispatchEvent(new Event('input')); await wait(perChar); }
    await wait(450);
    if (enter) input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
  }
  const box = () => $('symbol-input');
  const cmd = async (text, perChar = 75) => { await type(box(), text, perChar); await wait(300); };
  const body = () => $('insights-body');
  async function ready(max = 12000) {
    const t0 = Date.now();
    while (Date.now() - t0 < max) {
      const t = body().innerText;
      if (t.length > 80 && !t.includes('Loading…')) return;
      await wait(150);
    }
  }
  async function until(fn, max = 12000) { const t0 = Date.now(); while (Date.now() - t0 < max) { try { if (fn()) return true; } catch (e) { /* not yet */ } await wait(150); } return false; }
  const view = async (code, max) => { await cmd(code); await ready(max); };
  const group = async (g) => { await click(q(`#insights-tabs [data-group="${g}"]`), 300); await wait(250); await ready(); };
  async function smoothScroll(el, to, ms) {
    if (!el) return;
    const from = el.scrollTop, t0 = performance.now();
    while (true) {
      const p = Math.min(1, (performance.now() - t0) / ms);
      el.scrollTop = from + (to - from) * (0.5 - Math.cos(Math.PI * p) / 2);
      if (p >= 1) break;
      await new Promise(r => requestAnimationFrame(r));
    }
  }
  const scrollBody = (to, ms = 1800) => smoothScroll(body(), to === 'end' ? body().scrollHeight : to, ms);
  function closeAll() {
    if ($('insights-modal').classList.contains('open')) $('insights-close').click();
    for (const id of ['fno-close', 'screener-close', 'bonds-close', 'movers-close', 'grid-close', 'export-close', 'feed-close', 'move-close']) {
      const b = $(id);
      if (b && b.offsetParent !== null) b.click();
    }
    q('#cheat-modal')?.remove();
    if (!$('compare-wrap')?.hidden) $('compare-close')?.click();
  }
  // Click on the price pane at fractions of its width/height (Lightweight Charts listens on its top canvas).
  function chartPoint(fx, fy) {
    const all = [...document.querySelectorAll('#chart canvas')];
    const area = (c) => { const r = c.getBoundingClientRect(); return r.width * r.height; };
    const big = Math.max(...all.map(area));
    const cv = all.filter(c => area(c) === big).at(-1);
    if (!cv) return;
    const r = cv.getBoundingClientRect();
    const opt = { bubbles: true, clientX: r.left + r.width * fx, clientY: r.top + r.height * fy, button: 0, view: window };
    for (const t of ['pointerdown', 'mousedown']) cv.dispatchEvent(new MouseEvent(t, opt));
    for (const t of ['pointerup', 'mouseup', 'click']) cv.dispatchEvent(new MouseEvent(t, opt));
    document.dispatchEvent(new MouseEvent('mouseup', opt));
  }
  function setStudy(name, on = true) {
    const el = q(`#ind-panel [name=${name}]`);
    if (el && el.checked !== on) { el.checked = on; el.dispatchEvent(new Event('change', { bubbles: true })); }
  }

  // ---------- the script ----------
  const chapter = (n, title, sub) => async () => {
    closeAll();
    hideCaption();
    $('demo-chapter').classList.remove('on');
    await card(`<div class="num rise">${n}</div><div class="chap rise d1">${title}</div><div class="sub rise d2">${sub}</div>`, 2600);
    $('demo-chapter').textContent = `${n} · ${title}`;
    $('demo-chapter').classList.add('on');
  };

  const SCENES = [
    // ---- cold open ----
    ['open', async () => {
      await card(`<div class="logo rise">${logoSvg}Orazio</div><div class="tag rise d1">The market terminal that reads the market for you.</div>
        <div class="sub rise d2">Indian and global markets · live · free · runs on your machine · no login, no keys</div>`, 4600);
      await card(`<div class="tag rise">Bloomberg-grade depth.</div><div class="tag rise d1" style="color:#6e9cff">Without the hunting.</div>
        <div class="sub rise d2">Built for PMs, quants and prop desks who want the answer, then the evidence.</div>`, 3800);
    }],

    // ---- 01 ask ----
    ['ch1', chapter('01', 'Ask, don’t hunt', 'The Lens, one box for everything, plain-English screens, and an inbox of what changed.')],
    ['live', async () => {
      await cmd('NIFTY 5M');
      await wait(1500);
      caption('Live', 'Every market, pushed live. NIFTY on 5-minute bars.');
      await wait(3600);
    }],
    ['lens-index', async () => {
      ring($('lens'));
      caption('The Lens', 'It reads what you chart: dealer gamma, VIX, FII cash, put/call.');
      await until(() => $('lens-list').querySelectorAll('.lens-line').length >= 3, 9000);
      await wait(5200);
    }],
    ['lens-edge', async () => {
      await cmd('ASHOKLEY.NS');
      caption('Results edge', 'Results tomorrow. Options price more than it usually moves.');
      await until(() => /options price/.test($('lens-list').innerText), 14000);
      ring(q('#lens-list .lens-line'));
      await wait(5600);
      caption('The Lens', 'Valuation against NSE’s own peers, insider money, trend. One line each.');
      await wait(4200);
    }],
    ['box-view', async () => {
      caption('One box', 'A ticker, a view on it, or a question. It shows the command.');
      await type(box(), 'tcs peers', 95, false);
      await wait(2400);
      box().dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
      await ready(15000);
      caption('Company', 'Ratios, statements and peers, NSE first. Typed: tcs peers.');
      await wait(3200);
    }],
    ['box-screen', async () => {
      closeAll();
      caption('Plain-English screens', 'Ask for stocks the way you’d ask an analyst.');
      await type(box(), 'debt free companies with ROCE above 20', 55, false);
      await wait(1800);
      box().dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
      await until(() => /stocks match/.test(body().innerText), 20000);
      caption('Find', 'NSE reads the question. Orazio screens ~1,100 stocks. 1 second.');
      ring(q('.find-read'));
      await wait(4600);
      const add = [...body().querySelectorAll('.find-read .pick')].find(b => /P\/E/.test(b.textContent));
      if (add) {
        caption('Find', 'Refine in one click: add P/E below 15.');
        await click(add, 600);
        await until(() => /stocks match/.test(body().innerText), 15000);
        await wait(3800);
      }
      await scrollBody(700, 2200);
      await wait(1200);
    }],
    ['changes', async () => {
      await group('today');
      await click(q('#insights-tabs [data-tab="changes"]'), 300);
      await ready();
      caption('What changed', 'One inbox of surprises across your watchlist.');
      await wait(3600);
      caption('What changed', 'Ranked by how rare they are for that stock, in sigma.');
      await wait(4000);
    }],
    ['groups', async () => {
      caption('Insights', 'Thirty-plus views, organised by the job you’re doing.');
      for (const g of ['find', 'stock', 'deriv', 'rates', 'book', 'today']) {
        const b = q(`#insights-tabs [data-group="${g}"]`);
        ring(b);
        b?.click();
        await ready(3500);
        await wait(900);
      }
      await wait(800);
    }],
    ['cheat', async () => {
      closeAll();
      document.body.focus();
      caption('Learn by doing', 'Press ? and the whole product fits on one page.');
      await key('?');
      document.dispatchEvent(new KeyboardEvent('keydown', { key: '?', bubbles: true }));
      await wait(5200);
      q('#cheat-modal')?.remove();
      caption('Learn by doing', 'Every view has a command. Type : and go.');
      await key(':');
      await type(box(), ':FA', 160, false);
      await wait(1600);
      box().dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
      box().blur();
    }],

    // ---- 02 chart ----
    ['ch2', chapter('02', 'A chart that does the work', 'Volume profile, events on the candles, drawing tools, replay, grids and formulas.')],
    ['vp', async () => {
      await cmd('RELIANCE.NS');
      await wait(900);
      q('#range-bar button[data-range="1Y"]')?.click();   // range first: it picks an interval; then force daily bars
      await wait(1400);
      q('#interval-seg [data-interval="1d"]')?.click();   // daily bars: no intraday day-lines on a year of history
      await wait(1600);
      await click($('ind-btn'), 400);
      await wait(600);
      setStudy('vp');
      const ma = q('#ind-panel [data-ma="2"] [name=on]');
      if (ma && !ma.checked) { ma.checked = true; ma.dispatchEvent(new Event('change', { bubbles: true })); }
      await wait(700);
      $('ind-btn').click();
      caption('Volume profile', 'Volume by price, the point of control, the 70% value area.');
      await wait(5200);
    }],
    ['events', async () => {
      const ev = $('events-toggle');
      if (ev && !ev.checked) { ring(ev.closest('label')); await wait(400); ev.click(); }
      caption('Events', 'Results, dividends, block deals and insider trades on the candles.');
      await wait(5200);
    }],
    ['draw', async () => {
      caption('Drawing', 'Fibonacci, trendlines, channels. Saved per symbol.');
      await click($('fib-btn'), 400);
      chartPoint(0.25, 0.75);
      await wait(500);
      chartPoint(0.62, 0.25);
      await wait(1600);
      await click($('measure-btn'), 400);
      chartPoint(0.4, 0.6);
      await wait(400);
      chartPoint(0.8, 0.35);
      caption('Measure', 'Click, click: change, percent and bars between two points.');
      await wait(3600);
      $('measure-btn')?.click();
      await click($('draw-clear-btn'), 300);
      await wait(300);
      q('.confirm button.primary, [data-confirm="yes"]')?.click();
      setStudy('vp', false);
    }],
    ['replay', async () => {
      caption('Bar replay', 'Rewind the market. Trade it again, bar by bar.');
      await click($('replay-btn'), 400);
      await wait(500);
      chartPoint(0.35, 0.5);
      await wait(600);
      const speed = $('replay-speed');
      if (speed?.options.length) { speed.value = speed.options[speed.options.length - 1].value; speed.dispatchEvent(new Event('change')); }
      await click($('replay-play'), 300);
      await wait(5200);
      $('replay-exit')?.click();
      await wait(300);
    }],
    ['grid', async () => {
      await cmd('NIFTY');
      if (!$('compare-wrap').hidden) $('compare-close').click();
      await wait(300);
      await click($('grid-btn'), 400);
      await wait(400);
      if (!$('grid-modal').classList.contains('open')) $('grid-btn').click();
      await until(() => ![...document.querySelectorAll('.gp-px')].some(e => !e.textContent), 9000);
      caption('Multi-chart', 'One symbol, four timeframes, crosshairs linked.');
      await wait(4800);
      $('grid-close')?.click();
    }],
    ['formula', async () => {
      caption('Formulas', 'Chart any ratio or spread. NIFTY ÷ BANKNIFTY.');
      await wait(300);
      if ($('compare-wrap').hidden) await click($('compare-btn'), 400);
      await wait(800);
      await type($('compare-input'), 'NIFTY / BANKNIFTY', 70);
      await wait(7000);
      $('compare-close')?.click();
    }],
    ['commodities', async () => {
      await cmd('CRUDE');
      caption('Commodities', 'WTI, Brent, gold, silver, gas, copper. Ticking live.');
      await wait(3800);
      const fut = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Futures' && b.offsetParent !== null && b.closest('.seg, .feed-seg, [role=group]'));
      if (fut) { await click(fut, 400); caption('Commodities', 'Spot or perpetual futures, one click.'); await wait(3600); }
      const spot = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Spot' && b.offsetParent !== null);
      spot?.click();
    }],

    // ---- 03 company ----
    ['ch3', chapter('03', 'One company, in depth', 'Fundamentals, peers, results, holdings, filings, insiders, and the calendar.')],
    ['company', async () => {
      caption('Company', 'Market cap, P/E, ROE, ROCE, margins. NSE MarketLens first.');
      await view('TCS.NS FA', 15000);
      await wait(3800);
      await scrollBody(560, 2000);
      caption('Company', 'Five quarters, four years, balance sheet and cash flow.');
      await wait(2600);
      await scrollBody('end', 2400);
      caption('Peers', 'NSE’s own peer list, with the median. Cheap with quality?');
      await wait(4200);
    }],
    ['earnings', async () => {
      closeAll();
      caption('Earnings', 'How it moved after every result. And what options price now.');
      await cmd('ASHOKLEY.NS');
      await wait(1200);
      await view(':ERN', 15000);
      await wait(5200);
      await scrollBody(600, 1800);
      caption('Earnings', 'The results calendar, your watchlist first.');
      await wait(3000);
    }],
    ['holdings', async () => { await cmd('TCS.NS'); caption('Holdings', 'Promoter, public and trust ownership, quarter by quarter.'); await view(':HOLD'); await wait(4000); }],
    ['filings', async () => { caption('Filings', 'Every NSE announcement, filtered, with keyword alerts.'); await view(':FIL'); await wait(4000); }],
    ['insider', async () => { caption('Insiders', 'Promoter and director open-market buys, netted by company.'); await view(':INS'); await wait(4400); }],
    ['calendar', async () => {
      caption('Calendar', 'IPOs, recent listings against issue price, ex-dates ahead.');
      await view(':IPO');
      await wait(3000);
      await scrollBody(700, 2000);
      await wait(1800);
    }],
    ['eventstudy', async () => {
      await cmd('NIFTY');
      await view(':EVT');
      const kind = $('ev-kind');
      if (kind) { ring(kind); kind.value = 'cut'; kind.dispatchEvent(new Event('change')); await wait(300); await ready(); }
      caption('Event study', 'What does NIFTY do after an RBI rate cut? Measured.');
      await wait(4400);
    }],
    ['seasonality', async () => { caption('Seasonality', 'Nineteen years of NIFTY, by month and by weekday.'); await view(':SEAS'); await wait(4000); }],

    // ---- 04 derivatives ----
    ['ch4', chapter('04', 'Positioning and volatility', 'Dealer gamma, IV rank, the chain, payoffs and backtests.')],
    ['options', async () => {
      caption('Options', 'Dealer gamma, the flip level, call and put walls.');
      await view('NIFTY OPT', 15000);
      await wait(3600);
      ring(q('#insights-body .ins-sec'));
      caption('Volatility', 'IV30, IV rank, realised vol, India VIX rank. Cheap or dear?');
      await wait(4200);
      await scrollBody(900, 2200);
      caption('Options', 'Gamma by strike, OI build-up, the smile and term structure.');
      await scrollBody('end', 2000);
      await wait(1600);
    }],
    ['chain', async () => {
      closeAll();
      await cmd('NIFTY CHAIN');
      await wait(2500);
      caption('Option chain', 'Futures, the full chain, max pain and PCR.');
      await click(q('#fno-tabs [data-tab="chain"]'), 400);
      await wait(3600);
      await click(q('#fno-tabs [data-tab="smile"]'), 400);
      caption('Option chain', 'The IV smile across strikes.');
      await wait(3000);
      await click(q('#fno-tabs [data-tab="payoff"]'), 400);
      caption('Payoff builder', 'Build a strategy, see P&L at expiry and breakevens.');
      await wait(4200);
      $('fno-close')?.click();
    }],
    ['optbt', async () => { caption('Option backtest', 'Backtest a strategy on years of end-of-day NSE data.'); await view(':OBT'); await wait(4200); }],
    ['rollover', async () => { caption('Rollover', 'Who is rolling, and at what cost, into expiry.'); await view(':ROLL'); await wait(4000); }],

    // ---- 05 macro ----
    ['ch5', chapter('05', 'The whole market, before the open', 'Brief, flows, breadth, rotation, correlation, rates and the policy path.')],
    ['brief', async () => { caption('The brief', 'Your whole morning on one screen.'); await view(':BRIEF', 15000); await wait(4600); }],
    ['flows', async () => { caption('Flows', 'FII, DII, Pro and Client positioning, every day.'); await view(':FLOW'); await wait(2400); await scrollBody(520, 1800); await wait(1200); }],
    ['breadth', async () => { caption('Breadth', 'Advances, declines and new highs across the market.'); await view(':BRD'); await wait(3800); }],
    ['rotation', async () => { caption('Rotation', 'Which sectors lead NIFTY, week by week.'); await view(':RRG', 15000); await wait(4400); }],
    ['correlation', async () => { caption('Cross-asset', 'Correlation and beta across stocks, rates, FX, crude, crypto.'); await view(':CORR', 15000); await wait(4200); }],
    ['rates', async () => {
      caption('Rates', 'Scrub the yield curve back five years.');
      await view(':RATES', 15000);
      await wait(2400);
      await scrollBody(260, 700);
      const slider = $('rates-day');
      if (slider) {
        ring(slider);
        const max = +slider.max, target = Math.floor(max * 0.33);
        for (let i = 0; i <= 40; i++) { slider.value = String(Math.round(max - (max - target) * (i / 40))); slider.dispatchEvent(new Event('input')); await wait(60); }
      }
      await wait(2400);
    }],
    ['wirp', async () => { caption('Rate path', 'Basis points of RBI and Fed moves priced, read from bills.'); await view(':WIRP', 15000); await wait(5000); }],
    ['macro', async () => { caption('Macro', 'The week’s calendar in IST, and RBI liquidity.'); await view(':ECO'); await wait(4000); }],
    ['bonds', async () => {
      closeAll();
      await click($('bonds-btn'), 400);
      await click(q('#bond-tabs [data-tab="global"]'), 300);
      caption('Bonds', 'Government yields for 37 countries, live.');
      await wait(4200);
      await click(q('#bond-tabs [data-tab="india"]'), 400);
      caption('Bonds', 'Indian G-secs, SDLs and T-bills, trade by trade from CCIL.');
      await wait(4200);
      $('bonds-close')?.click();
    }],
    ['movers', async () => {
      caption('Movers', 'Top gainers and losers across markets.');
      await click($('movers-btn'), 400);
      await until(() => document.querySelectorAll('#movers-modal tbody tr').length > 4, 10000);
      await wait(3600);
      $('movers-close')?.click();
      caption('Screener', 'NIFTY 500 by RSI, moving averages, 52-week range.');
      await click($('screener-btn'), 400);
      await until(() => document.querySelectorAll('#screener tbody tr, .screener tbody tr').length > 4, 10000);
      await wait(3800);
      $('screener-close')?.click();
    }],
    ['cas', async () => {
      const b = $('cas-move-open');
      if (b && b.offsetParent !== null) {
        await click(b, 400);
        caption('Closing auction', 'NSE’s closing session, stock by stock, as it forms.');
        await wait(4400);
        $('move-close')?.click();
      }
    }],

    // ---- 06 your book ----
    ['ch6', chapter('06', 'Your book, your risk', 'Watchlist, portfolio, sizing, alerts with backtests, journal and layouts.')],
    ['watchlist', async () => { caption('Watchlist', 'RSI, 52-week range, volume and delivery, live.'); await view(':WL', 15000); await wait(4400); }],
    ['portfolio', async () => {
      caption('Portfolio', 'Import your broker CSV. Beta, volatility, drawdown, VaR.');
      await view(':PORT', 15000);
      await wait(3800);
      await scrollBody(380, 1800);
      caption('Portfolio', '2,000 simulated paths: the next 12 months, honestly.');
      await wait(4400);
    }],
    ['size', async () => { await cmd('TCS.NS'); caption('Position sizer', 'Capital, risk and stop give the size, in F&O lots.'); await view(':SIZE'); await wait(4400); }],
    ['alerts', async () => {
      caption('Alerts', 'Backtest an alert before you trust it.');
      await view(':ALRT');
      const b = body();
      const sym = q('#al-sym', b), type_ = q('#al-type', b), val = q('#al-val', b);
      if (sym && type_ && val) {
        sym.value = 'NIFTY';
        ring(type_);
        type_.value = 'chgDown';
        await wait(500);
        await type(val, '2', 120, false);
        await click(q('#al-test', b), 400);
      }
      await wait(6500);
      caption('Alerts', 'Fires with the page closed: desktop, Telegram, email.');
      await wait(2800);
    }],
    ['journal', async () => { caption('Journal', 'Every trade, with its setup, on your chart.'); await view(':JRNL'); await wait(3600); }],
    ['layouts', async () => { caption('Layouts', 'Expiry day, bond desk, pre-open. One click each.'); await view(':WS'); await wait(3600); }],

    // ---- 07 plumbing ----
    ['ch7', chapter('07', 'Yours, end to end', 'Excel, Claude, exports and the source of every number.')],
    ['excel', async () => { caption('Excel', '=WEBSERVICE pulls live prices and ratios into your sheet.'); await view(':XL'); await wait(4400); }],
    ['claude', async () => { caption('Claude', 'Ask Claude about your market data, on your own plan.'); await view(':SET'); await wait(2400); await scrollBody('end', 1800); await wait(1800); }],
    ['sources', async () => { caption('Provenance', 'Every number: its source, its delay, its health.'); await view(':SRC'); await wait(4400); }],
    ['export', async () => {
      closeAll();
      await click($('export-btn'), 400);
      caption('Export', 'OHLCV for any symbol or universe, or a nightly schedule.');
      await wait(3800);
      $('export-close')?.click();
    }],

    // ---- outro ----
    ['outro', async () => {
      closeAll();
      hideCaption();
      $('demo-chapter').classList.remove('on');
      await wait(400);
      await card(`<div class="logo rise">${logoSvg}Orazio</div><div class="tag rise d1">Ask. See why. Act.</div>
        <div class="pills rise d2"><span>Stock Lens</span><span>Results edge</span><span>Plain-English screens</span><span>What changed</span><span>Fundamentals + peers</span><span>Insider trades</span><span>Dealer gamma</span><span>IV rank</span><span>Rate path</span><span>Institutional flows</span><span>Sector rotation</span><span>Event studies</span><span>Yield curves</span><span>Volume profile</span><span>Bar replay</span><span>Alerts + backtests</span><span>Portfolio Monte Carlo</span><span>Excel links</span><span>Claude</span></div>
        <div class="cmd rise d3">pip install -r requirements.txt &nbsp;·&nbsp; python app.py</div>`, 7000, true);
    }],
  ];

  window.__demoScenes = Object.fromEntries(SCENES);   // run one beat on its own while rehearsing

  // Off camera, before recording: open every view once so caches are warm and no take shows a spinner.
  window.__orazioWarm = async function () {
    window.__demoState = 'warming';
    const codes = [':NEW', ':BRIEF', ':ERN', ':IPO', ':FLOW', ':BRD', ':INS', ':DLV', ':RRG', ':CORR', ':HOLD', ':FIL', ':EVT', ':SEAS',
      'NIFTY OPT', ':OBT', ':ROLL', ':RATES', ':WIRP', ':ECO', ':WL', ':PORT', ':SIZE', ':ALRT', ':JRNL', ':WS', ':XL', ':SET', ':SRC', 'TCS.NS FA', 'ASHOKLEY.NS ERN'];
    for (const c of codes) { try { await cmd(c, 5); await ready(15000); } catch (e) { /* warm what we can */ } }
    await fetch('/api/screen?q=' + encodeURIComponent('debt free companies with ROCE above 20')).catch(() => {});   // builds the screening universe
    closeAll();
    window.__demoState = 'warm';
  };

  window.__orazioDemo = async function () {
    window.__demoState = 'running';
    const failed = [];
    for (let i = 0; i < SCENES.length; i++) {
      const [name, fn] = SCENES[i];
      window.__demoState = `running: ${name}`;
      $('demo-progress').style.width = `${(i / (SCENES.length - 1)) * 100}%`;
      try { await fn(); } catch (e) { failed.push(`${name}: ${e.message}`); }
    }
    window.__demoFailed = failed;
    window.__demoState = 'done';
  };
})();
