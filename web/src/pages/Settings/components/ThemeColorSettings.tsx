import { useEffect, useId, useState } from 'react';
import { RotateCcw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { accentLightness, DEFAULT_ACCENT_HUE, getAccentHue, setAccentHue } from '@/lib/accentColor';

const presets = [
  { key: 'amber', hue: 28 },
  { key: 'rose', hue: 345 },
  { key: 'green', hue: 155 },
  { key: 'blue', hue: 210 },
  { key: 'violet', hue: 275 },
] as const;

export function ThemeColorSettings() {
  const { t } = useTranslation();
  const id = useId();
  const [hue, setHue] = useState(getAccentHue);
  const resolvedHue = hue ?? DEFAULT_ACCENT_HUE;
  useEffect(() => {
    const update = () => setHue(getAccentHue());
    window.addEventListener('theme-tokens-changed', update);
    return () => window.removeEventListener('theme-tokens-changed', update);
  }, []);

  return (
    <section className="theme-color-settings space-y-4 border-b pb-5" style={{ borderColor: 'var(--color-border-muted)' }} aria-labelledby={`${id}-title`}>
      <div className="flex items-center justify-between gap-3">
        <h3 id={`${id}-title`} className="text-sm font-medium">{t('settings.themeColor')}</h3>
        <button type="button" className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground disabled:opacity-40" disabled={hue === null} onClick={() => setAccentHue(null)}>
          <RotateCcw className="size-3.5" aria-hidden="true" />{t('settings.themeColorReset')}
        </button>
      </div>
      <div className="flex flex-wrap gap-3">
        {presets.map(({ key, hue: presetHue }) => (
          <button key={key} type="button" className="flex size-9 shrink-0 items-center justify-center rounded-full border-2 outline-none focus-visible:ring-2 focus-visible:ring-ring" style={{ borderColor: resolvedHue === presetHue ? 'var(--color-text-primary)' : 'transparent' }} aria-label={t(`settings.themeColorPresets.${key}`)} title={t(`settings.themeColorPresets.${key}`)} aria-pressed={resolvedHue === presetHue} onClick={() => setAccentHue(presetHue)}>
            <span className="size-6 rounded-full" style={{ backgroundColor: `hsl(${presetHue} 63% ${accentLightness(presetHue)}%)` }} />
          </button>
        ))}
      </div>
      <div className="flex items-center justify-between gap-3 text-xs">
        <label htmlFor={`${id}-hue`}>{t('settings.themeColorCustom')}</label>
        <output htmlFor={`${id}-hue`} className="tabular-nums text-muted-foreground">{resolvedHue}°</output>
      </div>
      <input id={`${id}-hue`} type="range" min={0} max={359} step={1} value={resolvedHue} onChange={(event) => setAccentHue(Number(event.target.value))} className="block h-6 w-full cursor-pointer" style={{ accentColor: 'var(--color-accent-primary)' }} />
    </section>
  );
}
