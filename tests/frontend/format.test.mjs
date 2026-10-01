// Formatting helpers: what a trader reads on screen (lakh/crore volumes, "6m ago", "+1.55").
import test from 'node:test';
import assert from 'node:assert/strict';
import { ago, compactIN, esc, formatSpan, formatVolume, signed } from '../../static/js/format.js';

test('esc neutralises HTML so headlines/company names can never inject markup', () => {
  assert.equal(esc('<img src=x onerror="alert(1)">'), '&lt;img src=x onerror=&quot;alert(1)&quot;&gt;');
  assert.equal(esc("Tom & Jerry's"), 'Tom &amp; Jerry&#39;s');
  assert.equal(esc(null), '');
  assert.equal(esc(undefined), '');
  assert.equal(esc(42), '42');
});

test('compactIN uses Indian units: crore at 1e7, lakh at 1e5, plain below', () => {
  assert.equal(compactIN(46_880_000), '4.69 Cr');
  assert.equal(compactIN(10_000_000), '1.00 Cr');
  assert.equal(compactIN(4_000_000), '40.00 L');
  assert.equal(compactIN(100_000), '1.00 L');
  assert.equal(compactIN(99_999), '99,999');
  assert.equal(compactIN(0), '0');
});

test('formatVolume uses K/M/B for global indices', () => {
  assert.equal(formatVolume(2_850_000_000), '2.85B');
  assert.equal(formatVolume(404_300_000), '404.3M');
  assert.equal(formatVolume(12_500), '13K');
  assert.equal(formatVolume(999), '999');
});

test('formatSpan reads like a duration, largest unit first', () => {
  assert.equal(formatSpan(0), '0m');
  assert.equal(formatSpan(540), '9m');
  assert.equal(formatSpan(8100), '2h 15m');
  assert.equal(formatSpan(3 * 86400 + 4 * 3600), '3d 4h');
});

test('ago buckets into just now / minutes / hours / days and never goes negative', () => {
  const now = 1_000_000;
  assert.equal(ago(now - 5, now), 'just now');
  assert.equal(ago(now - 360, now), '6m ago');
  assert.equal(ago(now - 3 * 3600, now), '3h ago');
  assert.equal(ago(now - 2 * 86400, now), '2d ago');
  assert.equal(ago(now + 500, now), 'just now', 'a timestamp slightly in the future must not print a negative age');
});

test('signed always shows the sign, including for zero', () => {
  assert.equal(signed(1.554), '+1.55');
  assert.equal(signed(-0.2), '-0.20');
  assert.equal(signed(0), '+0.00');
  assert.equal(signed(12, 0), '+12');
});
