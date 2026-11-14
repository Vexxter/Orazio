// Trade journal math — pure, unit-tested in Node (tests/frontend/journal-math.test.mjs). Trades are
// { id, date 'YYYY-MM-DD', symbol, side 'buy'|'sell', qty, price, setup, note }. Matching is FIFO per symbol;
// selling without a long position opens a short, which a later buy closes.

export function fifo(trades) {
  const sorted = [...trades].sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : (a.id || 0) - (b.id || 0)));
  const lots = new Map();   // symbol -> [{ qty (signed), price, setup, date }]
  const closed = [];
  for (const t of sorted) {
    const sign = t.side === 'buy' ? 1 : -1;
    let left = t.qty;
    const book = lots.get(t.symbol) || [];
    while (left > 0 && book.length && Math.sign(book[0].qty) === -sign) {
      const lot = book[0];
      const n = Math.min(left, Math.abs(lot.qty));
      const pnl = (lot.qty > 0 ? t.price - lot.price : lot.price - t.price) * n;
      closed.push({ symbol: t.symbol, setup: lot.setup || t.setup || '—', qty: n, entry: lot.price, exit: t.price, opened: lot.date, date: t.date, pnl, side: lot.qty > 0 ? 'long' : 'short' });
      lot.qty += sign * n;
      left -= n;
      if (lot.qty === 0) book.shift();
    }
    if (left > 0) book.push({ qty: sign * left, price: t.price, setup: t.setup, date: t.date });
    lots.set(t.symbol, book);
  }
  const open = [...lots].filter(([, b]) => b.length).map(([symbol, b]) => {
    const qty = b.reduce((s, l) => s + l.qty, 0);
    return { symbol, qty, avg: b.reduce((s, l) => s + l.qty * l.price, 0) / qty };
  });
  return { closed, open };
}

export function stats(closed) {
  const wins = closed.filter(c => c.pnl > 0), losses = closed.filter(c => c.pnl < 0);
  const sum = (a) => a.reduce((s, c) => s + c.pnl, 0);
  const by = new Map();
  for (const c of closed) { const k = c.setup || '—'; if (!by.has(k)) by.set(k, []); by.get(k).push(c); }
  let run = 0;
  const equity = [...closed].sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0)).map(c => ({ date: c.date, value: (run += c.pnl) }));
  return {
    total: sum(closed), trades: closed.length,
    winRate: closed.length ? (wins.length / closed.length) * 100 : null,
    avgWin: wins.length ? sum(wins) / wins.length : null,
    avgLoss: losses.length ? sum(losses) / losses.length : null,
    profitFactor: losses.length ? sum(wins) / Math.abs(sum(losses)) : null,
    bySetup: [...by].map(([setup, list]) => ({ setup, trades: list.length, pnl: sum(list), winRate: (list.filter(c => c.pnl > 0).length / list.length) * 100 }))
      .sort((a, b) => b.pnl - a.pnl),
    equity,
  };
}
