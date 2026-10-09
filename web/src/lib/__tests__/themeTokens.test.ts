import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import {
  clearThemeTokenCache,
  createThemeResolver,
  readTokens,
  resolveTokenMap,
  useThemeTokens,
} from '../themeTokens';

/**
 * jsdom computes every custom property to `''`, so the literal-fallback merge
 * is the ONLY path these tests can exercise — which is exactly why it needs
 * covering: it is also the path production takes on a theme flip, before the
 * stamp lands.
 */

const SOURCES = {
  quiet: { bg: '--color-bg-tool-card', up: '#1A7F37', down: '--color-loss' },
  nasa: { bg: '--color-bg-tool-card', up: '--color-profit', down: '--color-loss' },
};
const FALLBACKS = {
  quiet: { bg: '#F5F4F1', up: '#1A7F37', down: '#CF222E' },
  nasa: { bg: '#FFFFFF', up: '#1A7F37', down: '#D63A2C' },
};

beforeEach(() => {
  clearThemeTokenCache();
  document.documentElement.setAttribute('data-theme', 'quiet');
});

afterEach(() => {
  clearThemeTokenCache();
  document.documentElement.removeAttribute('data-theme');
});

describe('readTokens', () => {
  it('refreshes mounted canvas consumers when theme tokens change', () => {
    let palette = { accent: '#123456' };
    const resolver = () => palette;
    const { result } = renderHook(() => useThemeTokens(resolver, 'quiet'));
    expect(result.current.accent).toBe('#123456');
    act(() => {
      palette = { accent: '#654321' };
      clearThemeTokenCache();
      window.dispatchEvent(new Event('theme-tokens-changed'));
    });
    expect(result.current.accent).toBe('#654321');
  });
  it('returns nothing when the DOM resolves no value (jsdom)', () => {
    expect(readTokens(['--color-loss'], 'quiet')).toEqual({});
  });

  it('refuses to read while the stamped theme is the other one', () => {
    document.documentElement.setAttribute('data-theme', 'quiet');
    expect(readTokens(['--color-loss'], 'nasa')).toEqual({});
  });
});

describe('resolveTokenMap', () => {
  it('falls back to the literal for every token-backed slot', () => {
    expect(resolveTokenMap(SOURCES.quiet, FALLBACKS.quiet, 'quiet')).toEqual({
      bg: '#F5F4F1',
      up: '#1A7F37',
      down: '#CF222E',
    });
  });

  it('passes one-off literals through instead of looking them up', () => {
    const resolved = resolveTokenMap(
      SOURCES.quiet,
      { ...FALLBACKS.quiet, up: 'SHOULD-NOT-BE-USED' },
      'quiet',
    );
    // `up` is a literal source, so the fallback entry is irrelevant to it.
    expect(resolved.up).toBe('#1A7F37');
  });

  it('keeps each theme on its own literals', () => {
    document.documentElement.setAttribute('data-theme', 'nasa');
    expect(resolveTokenMap(SOURCES.nasa, FALLBACKS.nasa, 'nasa')).toEqual(FALLBACKS.nasa);
  });
});

describe('createThemeResolver', () => {
  it('hands back a stable identity per theme so chart effects do not churn', () => {
    const resolve = createThemeResolver(SOURCES, FALLBACKS);
    expect(resolve('quiet')).toBe(resolve('quiet'));
  });

  it('returns the requested theme, not the stamped one', () => {
    const resolve = createThemeResolver(SOURCES, FALLBACKS);
    expect(resolve('quiet')).toEqual(FALLBACKS.quiet);
    expect(resolve('nasa')).toEqual(FALLBACKS.nasa);
  });
});
