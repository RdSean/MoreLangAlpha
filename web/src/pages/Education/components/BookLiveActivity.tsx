import { useTranslation } from 'react-i18next';
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
  useTranslation();
  const { active, recentAt, recentKind, quote } = activity;
  const formatTime = createDateFormatter({
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
  return (
    <div className="mt-2 text-xs text-muted-foreground" aria-live="off">
      <p className="flex min-h-4 flex-wrap gap-x-2">
        {active && recentAt !== null && (
          <>
            <span>最近活动</span>
            <span>{recentKind}</span>
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
        className="m-0 mt-2 h-28 overflow-y-auto"
        aria-label="等待时的名句"
        aria-live="off"
      >
        {active && quote && (
          <>
            <blockquote className="m-0 break-words text-sm leading-6">
              {quote.contents}
            </blockquote>
            <figcaption className="mt-1 break-words leading-5">
              {quote.source}
            </figcaption>
          </>
        )}
      </figure>
    </div>
  );
}
