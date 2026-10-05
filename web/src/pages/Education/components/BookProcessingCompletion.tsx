import { ArrowRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { createFormatter } from '@/lib/format';
import type { BookJob } from '../types';
import { formatBookDuration } from './bookTimingProjection';

export function BookProcessingCompletion({
  job,
  totalMs,
  onEnterLearning,
}: {
  job: BookJob;
  totalMs: number | null;
  onEnterLearning?: () => void;
}) {
  const { t } = useTranslation();
  const ready =
    job.status === 'succeeded' || job.status === 'partially_succeeded';
  const formatNumber = createFormatter({ maximumFractionDigits: 0 });
  return (
    <footer className="book-processing-completion">
      <dl className="flex flex-wrap justify-center gap-x-8 gap-y-2 text-xs text-muted-foreground">
        <div aria-label={t('bookProcessing.timing')}>
          <dt>{t('bookProcessing.totalTime')}</dt>
          <dd
            className="mt-1 tabular-nums text-foreground"
            data-testid="book-processing-elapsed"
          >
            {formatBookDuration(totalMs)}
          </dd>
        </div>
        <div>
          <dt>
            {t(
              job.token_usage?.status === 'partial'
                ? 'bookProcessing.recordedTokens'
                : 'bookProcessing.tokens',
            )}
          </dt>
          <dd className="mt-1 tabular-nums text-foreground">
            {job.token_usage
              ? formatNumber(job.token_usage.total_tokens)
              : t('bookProcessing.missing')}
            {job.token_usage?.status === 'partial' && (
              <span className="ml-2 text-muted-foreground">
                {t('bookProcessing.partialUsage')}
              </span>
            )}
          </dd>
        </div>
      </dl>
      <p className="mt-3 text-sm" role="status">
        {job.safe_error ||
          (ready
            ? t(
                job.status === 'partially_succeeded'
                  ? 'bookProcessing.partialReady'
                  : 'bookProcessing.ready',
              )
            : t(`bookProcessing.status.${job.status}`))}
      </p>
      {onEnterLearning && (
        <Button
          variant={ready ? 'default' : 'outline'}
          className="mt-3 min-h-11"
          onClick={onEnterLearning}
        >
          {t(ready ? 'bookProcessing.learning' : 'bookProcessing.reading')}
          <ArrowRight className="ml-2 size-4" aria-hidden="true" />
        </Button>
      )}
    </footer>
  );
}
