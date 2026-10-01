// Pure formatting helpers — no DOM, no app state — so they can be unit-tested in Node
// (tests/frontend/format.test.mjs) and shared by every panel instead of being re-written in each.

export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// Indian grouping: shares and rupees read in lakh (L) and crore (Cr), not million/billion.
export function compactIN(n) {
  if (n >= 1e7) return `${(n / 1e7).toFixed(2)} Cr`;
  if (n >= 1e5) return `${(n / 1e5).toFixed(2)} L`;
  return Math.round(n).toLocaleString('en-IN');
}

// Western grouping, used for global indices' combined volume in the rail.
export function formatVolume(n) {
  if (n >= 1e9) return (n / 1e9).toFixed(2) + 'B';
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
  if (n >= 1e3) return (n / 1e3).toFixed(0) + 'K';
  return String(n);
}

// "3d 4h" / "2h 15m" / "9m" — the length of a measured span.
export function formatSpan(sec) {
  const d = Math.floor(sec / 86400);
  const h = Math.floor((sec % 86400) / 3600);
  const m = Math.floor((sec % 3600) / 60);
  if (d) return `${d}d ${h}h`;
  if (h) return `${h}h ${m}m`;
  return `${m}m`;
}

// "just now" / "6m ago" / "3h ago" / "2d ago" for a unix timestamp in seconds.
export function ago(sec, nowSec = Date.now() / 1000) {
  const s = Math.max(0, Math.floor(nowSec - sec));
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

// A signed fixed-decimal string: "+1.55", "-0.20", "+0.00".
export function signed(v, digits = 2) {
  return `${v >= 0 ? '+' : ''}${v.toFixed(digits)}`;
}
