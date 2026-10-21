// Option strategy payoff at expiry — pure, unit-tested in Node (tests/frontend/options-math.test.mjs).
// A leg: { side: 'buy'|'sell', kind: 'CE'|'PE'|'FUT', strike, premium, qty } where qty is in units
// (lots x lot size) and premium is the price paid/received per unit (for FUT: the entry price).

export function legPayoff(leg, spot) {
  const sign = leg.side === 'sell' ? -1 : 1;
  let value;
  if (leg.kind === 'CE') value = Math.max(spot - leg.strike, 0) - leg.premium;
  else if (leg.kind === 'PE') value = Math.max(leg.strike - spot, 0) - leg.premium;
  else value = spot - leg.premium;
  return sign * value * leg.qty;
}

export const payoff = (legs, spot) => legs.reduce((sum, l) => sum + legPayoff(l, spot), 0);

// Sample the curve on a spot grid that always includes every strike (where the kinks are).
export function payoffCurve(legs, lo, hi, steps = 200) {
  const xs = new Set();
  for (let i = 0; i <= steps; i++) xs.add(lo + ((hi - lo) * i) / steps);
  for (const l of legs) if (l.kind !== 'FUT' && l.strike > lo && l.strike < hi) xs.add(l.strike);
  return [...xs].sort((a, b) => a - b).map(x => ({ x, y: payoff(legs, x) }));
}

// Spots where the P&L crosses zero (linear interpolation between grid points).
export function breakevens(curve) {
  const out = [];
  for (let i = 1; i < curve.length; i++) {
    const a = curve[i - 1], b = curve[i];
    if (a.y === 0) out.push(a.x);
    else if ((a.y < 0) !== (b.y < 0) && b.y !== 0) out.push(a.x + ((0 - a.y) * (b.x - a.x)) / (b.y - a.y));
  }
  if (curve.length && curve.at(-1).y === 0) out.push(curve.at(-1).x);
  return out.map(x => Math.round(x * 100) / 100);
}

// Max profit / loss. Above the highest strike the P&L is a straight line whose slope is the net long
// calls + futures: nonzero means unlimited that way. The downside is bounded (spot can't go below 0),
// so it's checked by evaluating the payoff at 0 directly.
export function extremes(legs, curve) {
  const upSlope = legs.reduce((s, l) => s + (l.kind === 'PE' ? 0 : (l.side === 'sell' ? -1 : 1) * l.qty), 0);
  const ys = [...curve.map(p => p.y), payoff(legs, 0)];
  return {
    maxProfit: upSlope > 0 ? Infinity : Math.max(...ys),
    maxLoss: upSlope < 0 ? -Infinity : Math.min(...ys),
  };
}

// Net premium: positive = you pay (debit), negative = you receive (credit). Futures carry none.
export const netPremium = (legs) => legs.reduce((s, l) => s + (l.kind === 'FUT' ? 0 : (l.side === 'sell' ? -1 : 1) * l.premium * l.qty), 0);
