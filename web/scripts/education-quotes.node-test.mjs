import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { test } from 'node:test';
import { prepareEducationQuotes } from './education-quotes.mjs';

test('builds deterministic, bounded, deduplicated static pools', () => {
  const target = mkdtempSync(path.join(tmpdir(), 'langalpha-quotes-'));
  try {
    const entries = Array.from({ length: 501 }, (_, index) => ({ contents: `quote ${index}`, source: 'author' }));
    const manifest = prepareEducationQuotes({ entries: [...entries, entries[0]], target });
    assert.equal(manifest.files.length, 3);
    const pools = manifest.files.map((file) => JSON.parse(readFileSync(path.join(target, file), 'utf8')));
    assert.deepEqual(pools.map((pool) => pool.length), [250, 250, 1]);
    assert.equal(pools.flat().length, 501);
    assert.deepEqual(prepareEducationQuotes({ entries: [...entries, entries[0]], target }), manifest);
    assert.match(manifest.files[0], /^[a-f0-9]{16}-0\.json$/);
    assert.deepEqual(JSON.parse(readFileSync(path.join(target, 'manifest.json'), 'utf8')), manifest);
  } finally {
    rmSync(target, { recursive: true, force: true });
  }
});

test('rejects malformed, empty, oversized and non-text entries before publishing', () => {
  for (const entries of [[], {}, [null], [{ contents: 'x', source: '' }], [{ contents: 'x'.repeat(81), source: 'a' }], [{ contents: 1, source: 'a' }]]) {
    assert.throws(() => prepareEducationQuotes({ entries, target: 'unused' }), /quote/i);
  }
});
