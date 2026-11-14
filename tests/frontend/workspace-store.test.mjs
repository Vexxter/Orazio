// Workspaces: snapshot only layout keys, restore them, and let presets merge into existing settings.
import test from 'node:test';
import assert from 'node:assert/strict';
import { apply, list, remove, saveAs, snapshot } from '../../static/js/workspace-store.js';

const fakeStorage = (init = {}) => {
  const m = new Map(Object.entries(init));
  return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), map: m };
};

test('snapshot keeps layout, leaves data out', () => {
  const s = fakeStorage({ 'orazio.prefs.v1': '{"symbol":"NIFTY"}', 'orazio.alerts.v1': '{"alerts":[]}', 'orazio.drawings.v1': '{}' });
  assert.deepEqual(snapshot(s), { 'orazio.prefs.v1': '{"symbol":"NIFTY"}' });
});

test('save, list, apply and remove a workspace', () => {
  const s = fakeStorage({ 'orazio.prefs.v1': '{"symbol":"NIFTY","style":"bar"}' });
  saveAs(s, 'mine');
  s.setItem('orazio.prefs.v1', '{"symbol":"SPX"}');
  apply(s, list(s).mine);
  assert.equal(JSON.parse(s.getItem('orazio.prefs.v1')).style, 'bar');
  remove(s, 'mine');
  assert.deepEqual(list(s), {});
});

test('preset objects merge into what is stored; unknown keys are ignored', () => {
  const s = fakeStorage({ 'orazio.prefs.v1': '{"symbol":"NIFTY","style":"bar","theme":"light"}' });
  apply(s, { 'orazio.prefs.v1': { symbol: 'GIFTNIFTY' }, 'orazio.alerts.v1': { alerts: [1] } });
  assert.deepEqual(JSON.parse(s.getItem('orazio.prefs.v1')), { symbol: 'GIFTNIFTY', style: 'bar', theme: 'light' });
  assert.equal(s.getItem('orazio.alerts.v1'), null);
});
