// Command line: what counts as a command, and what stays an ordinary search.
import test from 'node:test';
import assert from 'node:assert/strict';
import { FUNCTIONS, parseCommand } from '../../static/js/command-parse.js';

test('SYMBOL FUNCTION and aliases', () => {
  assert.deepEqual(parseCommand('nifty opt'), { fn: 'OPT', symbol: 'NIFTY', arg: null, interval: null });
  assert.deepEqual(parseCommand('RELIANCE.NS gex'), { fn: 'OPT', symbol: 'RELIANCE.NS', arg: null, interval: null });
  assert.equal(parseCommand('NIFTY ?').fn, 'HELP');
});

test('compare takes an argument, with or without a symbol first', () => {
  assert.deepEqual(parseCommand('NIFTY CMP SPX'), { fn: 'CMP', symbol: 'NIFTY', arg: 'SPX', interval: null });
  assert.deepEqual(parseCommand('cmp nifty / banknifty'), { fn: 'CMP', symbol: null, arg: 'NIFTY / BANKNIFTY', interval: null });
});

test('SYMBOL INTERVAL charts at that bar size', () => {
  assert.deepEqual(parseCommand('banknifty 5m'), { fn: 'GP', symbol: 'BANKNIFTY', arg: null, interval: '5m' });
  assert.equal(parseCommand('NIFTY 1W').interval, '1wk');
});

test('single words need a colon, so ticker searches are left alone', () => {
  assert.equal(parseCommand('ROLL'), null);
  assert.equal(parseCommand('tata motors'), null);
  assert.equal(parseCommand('RELIANCE'), null);
  assert.deepEqual(parseCommand(':flow'), { fn: 'FLOW', symbol: null, arg: null, interval: null });
  assert.equal(parseCommand(':nope'), null);
});

test('every function has an action and a description', () => {
  for (const [k, [action, desc]] of Object.entries(FUNCTIONS)) assert.ok(/^(tab|btn|chart|compare):/.test(action) && desc, k);
});
