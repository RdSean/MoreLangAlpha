import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Loader } from '@/components/ui/loader';
import { getDocumentUsage } from '@/pages/Documents/api';
import type { UsageRange } from '@/pages/Documents/types';
import { queryKeys } from '@/lib/queryKeys';

const RANGES: UsageRange[] = ['7d', '14d', '30d'];

/** Cents to a display string. Money stays integer cents until it is shown. */
function formatCost(cents: number, locale: string): string {
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
  }).format(cents / 100);
}

/**
 * What document conversion has cost this account.
 *
 * Worth being explicit about what this is *not*: it is not the provider's
 * remaining balance. Datalab's hosted API publishes no balance or credits
 * endpoint — the on-premises `/api/v1/usage` route needs a licence we do not
 * have — so the only honest number is the one we can derive from what we
 * actually ran, which is what the endpoint aggregates.
 *
 * Layout follows the reviewed reference (plan card, two stat cards, a bar chart
 * with a range switch), with our own units: pages processed and money spent,
 * not credits.
 */
export default function UsageTab() {
  const { t, i18n } = useTranslation();
  const [range, setRange] = useState<UsageRange>('7d');

  const { data, isLoading } = useQuery({
    queryKey: queryKeys.settings.documents.usage(range),
    queryFn: () => getDocumentUsage(range),
    staleTime: 30_000,
  });

  const totals = data?.totals ?? { pages: 0, cost_cents: 0, conversions: 0 };
  const days = data?.days ?? [];
  const hasActivity = days.length > 0;

  return (
    <section className="settings-usage" data-testid="usage-tab">
      <header className="settings-usage__header">
        <h3 className="text-lg font-semibold" style={{ color: 'var(--color-text-primary)' }}>
          {t('settings.usage.title')}
        </h3>
        <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
          {t('settings.usage.subtitle')}
        </p>
      </header>

      <div className="settings-usage__stats" data-testid="usage-totals">
        <article className="settings-usage__card">
          <span className="settings-usage__label">{t('settings.usage.pages')}</span>
          <strong className="settings-usage__value" data-stat="pages">
            {totals.pages}
          </strong>
          <span className="settings-usage__hint">
            {t('settings.usage.conversions', { count: totals.conversions })}
          </span>
        </article>
        <article className="settings-usage__card">
          <span className="settings-usage__label">{t('settings.usage.cost')}</span>
          <strong className="settings-usage__value" data-stat="cost">
            {formatCost(totals.cost_cents, i18n.language)}
          </strong>
          <span className="settings-usage__hint">{t('settings.usage.costHint')}</span>
        </article>
      </div>

      <div className="settings-usage__chart">
        <div className="settings-usage__chart-head">
          <span className="settings-usage__label">{t('settings.usage.breakdown')}</span>
          <div role="group" aria-label={t('settings.usage.rangeLabel')}>
            {RANGES.map((option) => (
              <button
                key={option}
                type="button"
                data-testid={`usage-range-${option}`}
                aria-pressed={range === option}
                onClick={() => setRange(option)}
                className="settings-usage__range"
                style={{
                  backgroundColor:
                    range === option ? 'var(--color-bg-subtle)' : 'transparent',
                  color:
                    range === option
                      ? 'var(--color-text-primary)'
                      : 'var(--color-text-tertiary)',
                  fontWeight: range === option ? 600 : 400,
                }}
              >
                {t(`settings.usage.range_${option}`)}
              </button>
            ))}
          </div>
        </div>

        {isLoading ? (
          <div className="settings-usage__empty">
            <Loader size={16} />
            {t('common.loading')}
          </div>
        ) : hasActivity ? (
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={days} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border-muted)" vertical={false} />
              <XAxis
                dataKey="day"
                tick={{ fontSize: 11 }}
                stroke="var(--color-text-tertiary)"
                tickLine={false}
              />
              <YAxis
                tick={{ fontSize: 11 }}
                stroke="var(--color-text-tertiary)"
                tickLine={false}
                axisLine={false}
                allowDecimals={false}
              />
              <Tooltip
                formatter={(value, name) => [
                  String(value),
                  name === 'pages' ? t('settings.usage.pages') : t('settings.usage.cost'),
                ]}
              />
              <Bar dataKey="pages" fill="var(--color-accent-primary)" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          // An empty chart frame reads as "the chart failed"; say what is
          // actually true, which is that nothing has been converted yet.
          <div className="settings-usage__empty" data-testid="usage-empty">
            {t('settings.usage.empty')}
          </div>
        )}
      </div>
    </section>
  );
}
