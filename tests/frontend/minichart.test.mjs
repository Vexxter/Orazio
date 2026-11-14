// Insights mini charts: axis labels, extents and bar geometry.
import test from 'node:test';
import assert from 'node:assert/strict';
import { bars, extent, fmtTick, lines, scale } from '../../static/js/minichart.js';

test('fmtTick uses short Indian units', () => {
  assert.equal(fmtTick(257518), '2.58L');
  assert.equal(fmtTick(-23000000), '-2.3Cr');
  assert.equal(fmtTick(12500), '12.5k');
  assert.equal(fmtTick(3.984), '3.98');
  assert.equal(fmtTick(-9135.21), '-9135');
});

test('extent includes zero for bars and skips nulls', () => {
  assert.deepEqual(extent([{ values: [5, null, 9] }]), [0, 9]);
  assert.deepEqual(extent([{ values: [5, 9] }], false), [5, 9]);
});

test('scale maps the domain ends onto the range ends', () => {
  const y = scale(0, 10, 100, 0);
  assert.equal(y(0), 100);
  assert.equal(y(10), 0);
});

test('bars draw one rect per finite value, capped in width', () => {
  const svg = bars({ labels: ['a', 'b'], series: [{ name: 'x', values: [1, null], color: () => 'red' }] });
  assert.equal((svg.match(/<rect/g) || []).length, 1);
  assert.ok(+svg.match(/width="([\d.]+)"/)[1] <= 36);
});

test('lines break at nulls', () => {
  const svg = lines({ labels: ['a', 'b', 'c'], series: [{ name: 'x', values: [1, null, 3], color: 'red' }] });
  assert.equal((svg.match(/M/g) || []).length, 2);
});
