import { LayoutGrid } from 'lucide-react';
import { useTranslation } from 'react-i18next';

export interface LayoutToggle {
  mode: 'classic' | 'custom';
  onModeChange: (mode: 'classic' | 'custom') => void;
}

/**
 * Switches the dashboard between the classic workspace overview and the widget
 * canvas. Upstream inlined this markup in its dashboard header; both surfaces
 * need it here, so it lives in one place.
 */
export default function LayoutModeToggle({ mode, onModeChange }: LayoutToggle) {
  const { t } = useTranslation();
  const options = [
    { value: 'classic' as const, label: t('dashboard.layoutToggle.classic'), icon: null },
    { value: 'custom' as const, label: t('dashboard.layoutToggle.custom'), icon: LayoutGrid },
  ];

  return (
    <div
      role="tablist"
      aria-label={t('dashboard.layoutToggle.groupAria')}
      className="flex items-center rounded-lg border p-0.5"
      style={{
        backgroundColor: 'var(--color-bg-input)',
        borderColor: 'var(--color-border-muted)',
      }}
    >
      {options.map(({ value, label, icon: Icon }) => {
        const active = mode === value;
        return (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={active}
            data-testid={`layout-mode-${value}`}
            onClick={() => onModeChange(value)}
            className="flex items-center gap-1 rounded-md px-2.5 py-1 text-xs transition-colors"
            style={{
              backgroundColor: active ? 'var(--color-bg-elevated)' : 'transparent',
              color: active ? 'var(--color-text-primary)' : 'var(--color-text-secondary)',
              fontWeight: active ? 600 : 400,
            }}
          >
            {Icon ? <Icon size={12} aria-hidden="true" /> : null}
            {label}
          </button>
        );
      })}
    </div>
  );
}
