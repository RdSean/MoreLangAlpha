import { useTranslation } from 'react-i18next';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { createDateFormatter } from '@/lib/format';
import type { BookActivityEvent, BookJob, BookJobItem } from '../types';
import {
  useBookLiveActivity,
  type BookLiveActivityProjection,
} from './useBookLiveActivity';

interface Props {
  job: BookJob;
  item: BookJobItem;
  events: readonly BookActivityEvent[];
  connected: boolean;
  liveAfterSeq?: number | null;
}

export function BookLiveActivity({
  job,
  item,
  events,
  connected,
  liveAfterSeq = job.high_water_seq,
}: Props) {
  const activity = useBookLiveActivity(
    job,
    item,
    events,
    connected,
    liveAfterSeq,
  );
  return <BookLiveActivityView activity={activity} />;
}

export function BookLiveActivityView({
  activity,
}: {
  activity: BookLiveActivityProjection;
}) {
  const { t } = useTranslation();
  const reduceMotion = useReducedMotion();
  const { active, recentAt, recentKind, quote } = activity;
  const formatTime = createDateFormatter({
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
  return (
    <div className="book-waiting-quote text-xs text-muted-foreground" aria-live="off">
      <p className="sr-only">
        {active && recentAt !== null && (
          <>
            <span>{t('bookProcessing.recent')}</span>
            <span>{t(recentKind === '存储确认' ? 'bookProcessing.storage' : 'bookProcessing.tools')}</span>
            <time
              dateTime={new Date(recentAt).toISOString()}
              className="tabular-nums"
            >
              {formatTime(recentAt)}
            </time>
          </>
        )}
      </p>
      <figure
        className="m-0 h-12 text-center"
        aria-label={t('bookProcessing.quote')}
        aria-live="off"
      >
        <AnimatePresence mode="wait" initial={false}>
        {active && quote && (
          <motion.div key={`${quote.contents}:${quote.source}`} initial={{ opacity: reduceMotion ? 1 : 0 }} animate={{ opacity: 1 }} exit={{ opacity: reduceMotion ? 1 : 0 }} transition={{ duration: reduceMotion ? 0 : 0.25 }}>
            <blockquote className="m-0 truncate text-sm leading-6" title={quote.contents}>
              {quote.contents}
            </blockquote>
            <figcaption className="truncate leading-5" title={quote.source}>
              --{quote.source.split('《')[0]}
            </figcaption>
          </motion.div>
        )}
        </AnimatePresence>
      </figure>
    </div>
  );
}
