import { afterEach, describe, expect, it } from 'vitest';
import { applyAccentHue, getAccentHue, setAccentHue, accentLightness } from '../accentColor';

afterEach(() => { localStorage.clear(); applyAccentHue(null); });

describe('accent preferences', () => {
  it.each(['', 'null', 'NaN', '-1', '360', '15.5', '<script>'])('ignores invalid stored hue %s', (value) => {
    localStorage.setItem('accentHue', value);
    expect(getAccentHue()).toBeNull();
  });

  it('preserves the current preference when given an invalid change', () => {
    setAccentHue(210);
    setAccentHue(1000);
    expect(getAccentHue()).toBe(210);
    expect(document.documentElement.style.getPropertyValue('--theme-accent-hue')).toBe('210');
    setAccentHue(null);
    expect(document.documentElement.style.getPropertyValue('--theme-accent-lightness-light')).toBe('');
  });

  it('darkens bright hues for readable annotations on white', () => {
    expect(accentLightness(60)).toBeLessThan(35);
    expect(accentLightness(240)).toBeLessThanOrEqual(51);
  });
});
