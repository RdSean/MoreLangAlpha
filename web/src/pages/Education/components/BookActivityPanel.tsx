import { Maximize2, StopCircle, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import type { BookActivityEvent, BookJob, BookSourceStatus } from '../types';
import { BookLiveActivity, BookLiveActivityView } from './BookLiveActivity';
import type { BookLiveActivityProjection } from './useBookLiveActivity';
import {
  formatBookDuration,
  projectBookTiming,
  type BookTimingProjection,
} from './bookTimingProjection';
import {
  isTerminalBookJobStatus,
  projectBookActivity,
  type BookActivityProjection,
} from './bookActivityProjection';
import { BookServiceMilestones } from './BookServiceMilestones';
import { bookItemTitle } from './bookProcessingText';
import { BookProcessingCompletion } from './BookProcessingCompletion';

interface BookActivityPanelProps {
  job: BookJob;
  events: readonly BookActivityEvent[];
  reconnecting?: boolean;
  connected?: boolean;
  liveAfterSeq?: number | null;
  onClose?: () => void;
  onOpenProcessing?: () => void;
  timing?: BookTimingProjection;
  liveActivity?: BookLiveActivityProjection;
  projection?: BookActivityProjection;
  sourceStatus?: BookSourceStatus;
  onCancel?: () => void;
  cancelPending?: boolean;
}

export function BookActivityPanel({
  job,
  events,
  reconnecting = false,
  connected = true,
  liveAfterSeq,
  onClose,
  onOpenProcessing,
  timing,
  liveActivity,
  projection,
  sourceStatus,
  onCancel,
  cancelPending = false,
}: BookActivityPanelProps) {
  const { t } = useTranslation();
  const activity = projection ?? projectBookActivity(job, events);
  const terminal = isTerminalBookJobStatus(job.status);
  return (
    <aside
      className="flex min-h-0 flex-col border-l bg-[var(--color-bg-tool-card)]"
      aria-label={t('bookProcessing.activityPanel')}
    >
      <header className="flex items-center justify-between gap-2 border-b px-4 py-2">
        <h2 className="text-sm font-semibold">
          {t(
            job.kind === 'structure'
              ? 'bookProcessing.structure'
              : 'bookProcessing.materials',
          )}
        </h2>
        <div className="flex items-center">
          {!terminal && onCancel && (
            <button
              type="button"
              className="inline-flex size-11 items-center justify-center text-muted-foreground disabled:opacity-50"
              onClick={onCancel}
              disabled={cancelPending}
              aria-label={t('bookProcessing.cancelRequest')}
              title={t('bookProcessing.cancelRequest')}
            >
              <StopCircle className="size-4" aria-hidden="true" />
            </button>
          )}
          {onOpenProcessing && (
            <button
              type="button"
              className="inline-flex size-11 items-center justify-center text-muted-foreground"
              onClick={onOpenProcessing}
              aria-label={t('bookProcessing.openTimeline')}
              title={t('bookProcessing.openTimeline')}
            >
              <Maximize2 className="size-4" aria-hidden="true" />
            </button>
          )}
          {onClose && (
            <button
              type="button"
              className="inline-flex size-11 items-center justify-center text-muted-foreground"
              onClick={onClose}
              aria-label={t('bookProcessing.closeActivity')}
              title={t('bookProcessing.closeActivity')}
            >
              <X className="size-4" aria-hidden="true" />
            </button>
          )}
        </div>
      </header>
      <div className="book-activity-content flex min-h-0 flex-1 flex-col overflow-y-auto px-4 py-3">
        <div className="mb-3 text-xs text-muted-foreground">
          <p>
            {t(`bookProcessing.status.${job.status}`)}
            {timing && ` · ${formatBookDuration(timing.roundMs)}`}
          </p>
          {activity.currentItem && job.kind === 'materials' && (
            <p
              className="mt-1 truncate"
              title={bookItemTitle(activity.currentItem)}
            >
              {bookItemTitle(activity.currentItem)}
            </p>
          )}
          {activity.materialProgress && (
            <p className="mt-1 tabular-nums">
              {t('bookProcessing.materialProgress', activity.materialProgress)}
            </p>
          )}
          {reconnecting && (
            <p className="mt-1">{t('bookProcessing.reconnecting')}</p>
          )}
          {activity.activityUnavailable && (
            <p className="mt-1" role="status">
              {t('bookProcessing.unavailable')}
            </p>
          )}
        </div>
        <BookServiceMilestones
          job={job}
          events={events}
          timing={timing ?? projectBookTiming(job, null)}
          sourceStatus={sourceStatus}
          agentActions={activity.agentActions}
          connected={connected && !reconnecting}
          activityUnavailable={activity.activityUnavailable}
        />
        {!terminal &&
          activity.currentItem &&
          !activity.activityUnavailable &&
          (liveActivity ? (
            <BookLiveActivityView activity={liveActivity} />
          ) : (
            <BookLiveActivity
              key={`${job.job_id}:${activity.currentItem.item_id}:${activity.currentItem.attempt}`}
              job={job}
              item={activity.currentItem}
              events={events}
              connected={connected && !reconnecting}
              liveAfterSeq={liveAfterSeq}
            />
          ))}
        {terminal && (
          <BookProcessingCompletion
            job={job}
            totalMs={timing?.roundMs ?? projectBookTiming(job, null).roundMs}
            onEnterLearning={onClose}
          />
        )}
      </div>
    </aside>
  );
}

export function RoutedBookActivityPanel(
  props: Omit<BookActivityPanelProps, 'onClose'>,
) {
  const [searchParams, setSearchParams] = useSearchParams();
  if (searchParams.get('activity') !== props.job.job_id) return null;
  const close = () => {
    const next = new URLSearchParams(searchParams);
    next.delete('activity');
    setSearchParams(next, { replace: true });
  };
  return <BookActivityPanel {...props} onClose={close} />;
}
