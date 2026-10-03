import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';

export function prepareEducationQuotes({ entries, target }) {
  if (!Array.isArray(entries) || !entries.length) throw new Error('Quote collection must be a nonempty array');
  const unique = new Map();
  for (const entry of entries) {
    if (!entry || typeof entry.contents !== 'string' || typeof entry.source !== 'string') throw new Error('Quote fields must be text');
    const contents = entry.contents.trim();
    const source = entry.source.trim();
    if (!contents || !source || [...contents].length > 80 || [...source].length > 80) throw new Error('Quote fields are empty or too long');
    unique.set(`${contents}\n${source}`, { contents, source });
  }
  const quotes = [...unique.values()];
  const version = createHash('sha256').update(JSON.stringify(quotes)).digest('hex').slice(0, 16);
  const files = [];
  mkdirSync(target, { recursive: true });
  for (let offset = 0; offset < quotes.length; offset += 250) {
    const file = `${version}-${files.length}.json`;
    writeFileSync(path.join(target, file), JSON.stringify(quotes.slice(offset, offset + 250)));
    files.push(file);
  }
  const manifest = { files };
  writeFileSync(path.join(target, 'manifest.json'), JSON.stringify(manifest));
  return manifest;
}

export function prepareEducationQuotesForWeb(webRoot) {
  return prepareEducationQuotes({
    entries: JSON.parse(readFileSync(path.resolve(webRoot, '../mingju.json'), 'utf8')),
    target: path.join(webRoot, 'public/education-quotes'),
  });
}
