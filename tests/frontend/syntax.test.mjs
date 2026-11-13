// Every frontend module must parse: one syntax error stops the whole page's module graph from loading, and most
// modules touch the DOM so no other Node test imports them.
import test from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readdirSync } from 'node:fs';
import { join } from 'node:path';

const dir = join(import.meta.dirname, '..', '..', 'static', 'js');
for (const f of readdirSync(dir).filter(n => n.endsWith('.js'))) {
  test(`${f} parses`, () => {
    assert.doesNotThrow(() => execFileSync(process.execPath, ['--check', join(dir, f)], { stdio: 'pipe' }));
  });
}
