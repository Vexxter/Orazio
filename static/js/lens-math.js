// Stock Lens: the handful of facts about the charted symbol that matter right now, each one line with a verdict and
// the command that shows the evidence. Pure — unit-tested in tests/frontend/lens-math.test.mjs; lens.js gathers the
// inputs and draws the card. Every input is optional: a line appears only when its facts are known.
//
// facts: { pe, peerPe, roe, peerRoe, nextResults: { date, days }, typicalMove, impliedMove, insiderNetCr, insiderTrades,
//          ivRank, ivDays, trend: { vs200, fromHigh, ret1m }, gex: { netCr, flip, spot }, pcr, vixRank, fiiNetCr, symbol }
// -> [{ tone: 'up'|'down'|'warn'|'flat', title, text, cmd }] most important first.

const f1 = (v) => (Math.abs(v) >= 10 ? v.toFixed(0) : v.toFixed(1));
const signed = (v) => `${v > 0 ? '+' : ''}${f1(v)}`;

export function lensLines(x) {
  const out = [];
  const sym = x.symbol || '';

  // Results ahead, and whether options price more or less than the stock usually moves: the results edge.
  if (x.nextResults && x.nextResults.days >= 0 && x.nextResults.days <= 45) {
    const when = x.nextResults.days === 0 ? 'today' : x.nextResults.days === 1 ? 'tomorrow' : `in ${x.nextResults.days} days`;
    let text = `Results ${when}`;
    let tone = 'warn';
    if (x.typicalMove) text += ` · usually moves ±${f1(x.typicalMove)}%`;
    if (x.impliedMove && x.typicalMove) {
      const ratio = x.impliedMove / x.typicalMove;
      text += ` · options price ±${f1(x.impliedMove)}%`;
      text += ratio > 1.25 ? ' (rich: premium sellers’ setup)' : ratio < 0.8 ? ' (cheap: premium buyers’ setup)' : ' (fair)';
      tone = ratio > 1.25 || ratio < 0.8 ? 'warn' : 'flat';
    }
    out.push({ rank: x.nextResults.days <= 7 ? 100 : 60, tone, title: 'Results', text, cmd: `${sym} ERN`.trim() });
  }

  if (x.insiderNetCr && Math.abs(x.insiderNetCr) >= 0.5) {
    const buy = x.insiderNetCr > 0;
    out.push({ rank: Math.min(95, 50 + Math.abs(x.insiderNetCr)), tone: buy ? 'up' : 'down', title: 'Insiders',
      text: `Promoters/directors net ${buy ? 'bought' : 'sold'} ₹${f1(Math.abs(x.insiderNetCr))} Cr${x.insiderTrades ? ` in ${x.insiderTrades} trades` : ''}`, cmd: ':INS' });
  }

  if (x.pe && x.peerPe) {
    const prem = (x.pe / x.peerPe - 1) * 100;
    const q = x.roe !== null && x.roe !== undefined && x.peerRoe ? (x.roe >= x.peerRoe ? 'higher' : 'lower') : null;
    const cheapGood = prem < -15 && q === 'higher', dearBad = prem > 25 && q === 'lower';
    out.push({ rank: Math.abs(prem) > 25 ? 70 : 40, tone: cheapGood ? 'up' : dearBad ? 'down' : 'flat', title: 'Valuation',
      text: `P/E ${f1(x.pe)}x, ${Math.abs(prem) < 5 ? 'in line with' : `${f1(Math.abs(prem))}% ${prem < 0 ? 'below' : 'above'}`} peers${q ? ` · ${q} ROE` : ''}`, cmd: `${sym} FA`.trim() });
  }

  if (x.ivRank !== null && x.ivRank !== undefined) {
    const t = x.ivRank >= 80 ? 'dear' : x.ivRank <= 20 ? 'cheap' : 'mid-range';
    out.push({ rank: x.ivRank >= 80 || x.ivRank <= 20 ? 75 : 30, tone: t === 'mid-range' ? 'flat' : 'warn', title: 'Volatility',
      text: `IV rank ${x.ivRank.toFixed(0)}: options ${t}`, cmd: `${sym} OPT`.trim() });
  } else if (x.ivDays !== undefined && x.ivDays !== null && x.ivDays < 20) {
    out.push({ rank: 5, tone: 'flat', title: 'Volatility', text: `IV rank builds in ${20 - x.ivDays} more trading days`, cmd: `${sym} OPT`.trim() });
  }

  if (x.vixRank !== null && x.vixRank !== undefined) {
    out.push({ rank: x.vixRank >= 80 || x.vixRank <= 20 ? 65 : 25, tone: x.vixRank >= 80 ? 'down' : 'flat', title: 'India VIX',
      text: `VIX rank ${x.vixRank.toFixed(0)} over a year${x.vixRank >= 80 ? ': fear is high' : x.vixRank <= 20 ? ': complacent' : ''}`, cmd: 'NIFTY OPT' });
  }

  if (x.gex && x.gex.flip && x.gex.spot) {
    const above = x.gex.spot >= x.gex.flip;
    out.push({ rank: 80, tone: above ? 'up' : 'down', title: 'Dealer gamma',
      text: `${above ? 'Above' : 'Below'} the ${Math.round(x.gex.flip)} flip: dealers ${above ? 'dampen' : 'amplify'} moves`, cmd: `${sym} OPT`.trim() });
  }

  if (x.pcr) {
    out.push({ rank: x.pcr > 1.3 || x.pcr < 0.7 ? 55 : 20, tone: 'flat', title: 'Put/call', text: `PCR ${x.pcr.toFixed(2)}${x.pcr > 1.3 ? ': heavy put writing' : x.pcr < 0.7 ? ': call-heavy' : ''}`, cmd: `${sym} CHAIN`.trim() });
  }

  if (x.fiiNetCr) {
    out.push({ rank: Math.abs(x.fiiNetCr) >= 3000 ? 60 : 20, tone: x.fiiNetCr > 0 ? 'up' : 'down', title: 'FII cash',
      text: `FIIs ${x.fiiNetCr > 0 ? 'bought' : 'sold'} ₹${Math.abs(x.fiiNetCr).toLocaleString('en-IN', { maximumFractionDigits: 0 })} Cr last session`, cmd: ':FLOW' });
  }

  if (x.trend) {
    const { vs200, fromHigh, ret1m } = x.trend;
    const parts = [];
    if (vs200 !== null && vs200 !== undefined) parts.push(`${signed(vs200)}% vs 200-day`);
    if (fromHigh !== null && fromHigh !== undefined) parts.push(fromHigh > -2 ? 'at a 52-week high' : `${f1(-fromHigh)}% off the high`);
    if (ret1m !== null && ret1m !== undefined) parts.push(`${signed(ret1m)}% in a month`);
    if (parts.length) {
      out.push({ rank: fromHigh > -2 ? 58 : 15, tone: vs200 > 0 ? 'up' : vs200 < 0 ? 'down' : 'flat', title: 'Trend', text: parts.join(' · '), cmd: `${sym} SEAS`.trim() });
    }
  }

  return out.sort((a, b) => b.rank - a.rank).map(({ rank, ...l }) => l);
}

// Trend facts from daily bars (oldest first): distance from the 200-day average and the 52-week high, one-month return.
export function trendFacts(bars) {
  const c = bars.map(b => b.close).filter(v => v > 0);
  if (c.length < 22) return null;
  const last = c.at(-1);
  const sma200 = c.length >= 200 ? c.slice(-200).reduce((s, v) => s + v, 0) / 200 : null;
  const high = Math.max(...c.slice(-252));
  return { vs200: sma200 ? (last / sma200 - 1) * 100 : null, fromHigh: (last / high - 1) * 100, ret1m: (last / c.at(-22) - 1) * 100 };
}
