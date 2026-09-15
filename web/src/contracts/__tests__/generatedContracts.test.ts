import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
// @ts-expect-error — a build script, plain ESM, no types to import.
import { CONTRACTS, buildContracts } from '../../../scripts/generate-contracts.mjs';

/**
 * The zod module is generated from the committed JSON Schema, which is itself
 * guarded against Pydantic by
 * `tests/unit/contracts/test_generated_schemas_are_current.py`. Together the
 * two make the chain Pydantic → JSON → zod unbroken: this test fails the
 * moment the committed TypeScript falls behind the schema.
 *
 * Regenerate with:
 *     cd web && node scripts/generate-contracts.mjs
 */
const WEB_ROOT = join(process.cwd());

describe('generated contract modules', () => {
  it('are exactly what the generator produces', () => {
    for (const [relativePath, expected] of Object.entries(buildContracts())) {
      const onDisk = readFileSync(join(WEB_ROOT, relativePath), 'utf8');
      expect(
        onDisk,
        `${relativePath} is stale — re-run \`node scripts/generate-contracts.mjs\``,
      ).toBe(expected);
    }
  });

  it('cover every declared contract', () => {
    expect(Object.keys(buildContracts())).toEqual(
      CONTRACTS.map((contract: { output: string }) => contract.output),
    );
  });
});
