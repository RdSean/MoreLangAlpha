/**
 * Turn the exported JSON Schemas into real zod source.
 *
 * Pipeline: Pydantic → (scripts/contracts/export_schemas.py) → committed JSON
 * Schema → this script → committed zod module.
 *
 * Two things this step is doing, both learned by measurement rather than
 * assumed (see the design doc for the full table):
 *
 * 1. **Why not zod's own `z.fromJSONSchema`.** It resolves `$ref`s correctly
 *    and validates correctly, but its declaration returns a bare `ZodType` —
 *    no generic, no inference — so `z.infer` yields `unknown` and `.shape` does
 *    not exist. It gives validation without types, and zod's own comment calls
 *    it "semi-experimental". Half a contract.
 * 2. **Why the `$ref`s are inlined first.** `json-schema-to-zod` emits
 *    `z.any()` for every `$ref` it cannot resolve — which for this schema meant
 *    `z.array(z.any())` for `days` and `z.any()` for `stats`, i.e. it silently
 *    validated nothing in the nested models. Inlining first turns those into
 *    real nested `z.object`s. Our model graph is a DAG, so inlining terminates;
 *    `assertNoRefsRemain` keeps that assumption honest if a recursive model is
 *    ever added.
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { jsonSchemaToZod } from 'json-schema-to-zod';

const WEB_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

/** Registry: input schema (web-relative) → generated module. */
export const CONTRACTS = [
  {
    input: 'src/contracts/education-calendar.schema.json',
    output: 'src/contracts/generated/educationCalendar.generated.ts',
    exportName: 'educationTaskCalendarSchema',
  },
];

const BANNER = `/**
 * GENERATED FILE — do not edit.
 *
 * Source: {{INPUT}}
 * Produced by: web/scripts/generate-contracts.mjs
 * Which is fed by: scripts/contracts/export_schemas.py (from Pydantic)
 *
 * web/src/contracts/__tests__/generatedContracts.test.ts regenerates this and
 * fails if it is stale.
 */

`;

function inlineRefs(document) {
  const definitions = document.$defs ?? {};

  const inline = (node) => {
    if (Array.isArray(node)) return node.map(inline);
    if (node && typeof node === 'object') {
      if (typeof node.$ref === 'string') {
        const name = node.$ref.replace('#/$defs/', '');
        const target = definitions[name];
        if (!target) throw new Error(`Unresolved $ref: ${node.$ref}`);
        // Copy-then-delete rather than rest destructuring: the dropped key is
        // still a binding that the linter rightly flags as unused.
        const rest = { ...node };
        delete rest.$ref;
        return { ...inline(target), ...inline(rest) };
      }
      const out = {};
      for (const [key, value] of Object.entries(node)) {
        if (key === '$defs') continue;
        out[key] = inline(value);
      }
      return out;
    }
    return node;
  };

  return inline(document);
}

/**
 * Guard the DAG assumption inlining depends on: after inlining, no `$ref` may
 * survive, and no `z.any()` may have been emitted in its place.
 */
function assertFullyResolved(source) {
  const anys = (source.match(/z\.any\(\)/g) ?? []).length;
  if (anys > 0) {
    throw new Error(
      `Generated schema contains ${anys} \`z.any()\` — a $ref was not inlined, ` +
        'so the nested model would validate nothing.',
    );
  }
}

/** @returns {Record<string, string>} web-relative output path → file contents */
export function buildContracts() {
  const built = {};
  for (const contract of CONTRACTS) {
    const schema = JSON.parse(fs.readFileSync(path.join(WEB_ROOT, contract.input), 'utf8'));
    const source = jsonSchemaToZod(inlineRefs(schema), {
      module: 'esm',
      name: contract.exportName,
    });
    assertFullyResolved(source);
    built[contract.output] = BANNER.replace('{{INPUT}}', contract.input) + source;
  }
  return built;
}

function main() {
  for (const [relativePath, contents] of Object.entries(buildContracts())) {
    const target = path.join(WEB_ROOT, relativePath);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.writeFileSync(target, contents, 'utf8');
    console.log(`wrote ${relativePath}`);
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main();
}
