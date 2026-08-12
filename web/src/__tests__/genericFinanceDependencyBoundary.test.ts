import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';

const sourceRoot = join(process.cwd(), 'src');
const retiredImplementations = [
  '/pages/MarketView/',
  '/lib/bars/',
  '/lib/marketUtils',
];

function runtimeSourceFiles(directory: string): string[] {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry);
    if (statSync(path).isDirectory()) {
      return entry === '__tests__' ? [] : runtimeSourceFiles(path);
    }
    return /\.(?:ts|tsx)$/.test(entry) ? [path] : [];
  });
}

describe('generic finance dependency boundary', () => {
  it('does not retain financial implementation imports outside retired source trees', () => {
    const references = runtimeSourceFiles(sourceRoot)
      .filter((path) => !retiredImplementations.some((implementation) => path.includes(implementation)))
      .flatMap((path) => {
        const content = readFileSync(path, 'utf8');
        const importsRetiredImplementation = retiredImplementations.some((implementation) => content.includes(implementation));
        return importsRetiredImplementation ? [relative(sourceRoot, path)] : [];
      });

    expect(references).toEqual([]);
  });
});
