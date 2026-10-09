import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const tokens = readFileSync(resolve(__dirname, '../tokens.css'), 'utf8');

describe('NASA Mission tokens', () => {
  it('defines the paper, accent, identity, and texture contract', () => {
    expect(tokens).toContain('[data-theme="nasa"]');
    expect(tokens).toContain('--color-bg-page: #ECE5D6');
    expect(tokens).toContain('--color-accent-primary: #D63A2C');
    expect(tokens).toContain('--warning-stripe:');
    expect(tokens).toContain('--identity-stripe:');
    expect(tokens).toContain('--font-label: var(--font-mono)');
  });

  it('keeps Quiet Workspace as a separate light theme', () => {
    expect(tokens).toContain('[data-theme="quiet"]');
    expect(tokens).toContain('--color-bg-canvas: #F5F4F1');
  });
});
