import { z } from 'zod';
import { clearThemeTokenCache } from './themeTokens';

export const DEFAULT_ACCENT_HUE = 28;
const hueSchema = z.number().int().min(0).max(359);

export function accentLightness(hue: number): number {
  const saturation = 0.63;
  let lightness = 51;
  // HSL channels are converted to relative luminance to keep text at 4.5:1.
  const luminance = (value: number) => {
    const light = value / 100;
    const amplitude = saturation * Math.min(light, 1 - light);
    const channels = [0, 8, 4].map((offset) => {
      const sector = (offset + hue / 30) % 12;
      const channel = light - amplitude * Math.max(-1, Math.min(sector - 3, 9 - sector, 1));
      return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
    });
    return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
  };
  while (lightness > 1 && lightness < 99) {
    const level = luminance(lightness);
    const contrast = 1.05 / (level + 0.05);
    if (contrast >= 4.5) break;
    lightness -= 1;
  }
  return lightness;
}

export function getAccentHue(): number | null {
  try {
    const stored = localStorage.getItem('accentHue');
    if (!stored?.trim()) return null;
    const parsed = hueSchema.safeParse(Number(stored));
    return parsed.success ? parsed.data : null;
  } catch {
    return null;
  }
}

export function applyAccentHue(hue: number | null): void {
  const root = document.documentElement.style;
  if (hue === null) {
    root.removeProperty('--theme-accent-hue');
    root.removeProperty('--theme-accent-lightness-light');
    root.removeProperty('--theme-accent-lightness-dark');
  } else {
    root.setProperty('--theme-accent-hue', String(hue));
    root.setProperty('--theme-accent-lightness-light', `${accentLightness(hue)}%`);
  }
  clearThemeTokenCache();
  window.dispatchEvent(new Event('theme-tokens-changed'));
}

export function setAccentHue(hue: number | null): void {
  if (hue !== null && !hueSchema.safeParse(hue).success) return;
  // Persist derived lightness for the pre-paint bootstrap; hue remains the preference.
  if (hue === null) {
    localStorage.removeItem('accentLightnessLight');
    localStorage.removeItem('accentLightnessDark');
    localStorage.removeItem('accentHue');
  } else {
    localStorage.setItem('accentLightnessLight', String(accentLightness(hue)));
    localStorage.setItem('accentHue', String(hue));
  }
  applyAccentHue(hue);
}
