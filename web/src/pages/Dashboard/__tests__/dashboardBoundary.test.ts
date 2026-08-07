import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';

const sourceRoot = join(process.cwd(), 'src');
const deferredFinancialSurfaces = ['/pages/MarketView/', '/pages/Onboarding/'];

function runtimeSourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) {
      return entry === '__tests__' ? [] : runtimeSourceFiles(path);
    }
    return /\.(?:ts|tsx)$/.test(entry) ? [path] : [];
  });
}

describe('dashboard ownership boundary', () => {
  it('keeps the generic application outside the retired Dashboard implementation', () => {
    const references = runtimeSourceFiles(sourceRoot)
      .filter((path) => !path.includes('/pages/Dashboard/'))
      .filter((path) => !deferredFinancialSurfaces.some((surface) => path.includes(surface)))
      .flatMap((path) => {
        const content = readFileSync(path, 'utf8');
        return /(?:from|import)\s*[('][^'"`]*Dashboard\//.test(content)
          ? [relative(sourceRoot, path)]
          : [];
      });

    expect(references).toEqual([]);
  });
});
