import { ArrowLeft, ArrowUpRight, StopCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import type {
  BookActivityEvent,
  BookJob,
  BookSourceStatus,
  FrozenBookSource,
  KnowledgePointProjection,
} from '../types';
import {
  formatBookDuration,
  type BookTimingProjection,
} from './bookTimingProjection';
import {
  isTerminalBookJobStatus,
  projectBookActivity,
  type BookActivityProjection,
} from './bookActivityProjection';
import { BookLiveActivity, BookLiveActivityView } from './BookLiveActivity';
import type { BookLiveActivityProjection } from './useBookLiveActivity';
import { BookServiceMilestones } from './BookServiceMilestones';
import { BookMaterialDeliveryList } from './BookMaterialDeliveryList';
import { BookProcessingCompletion } from './BookProcessingCompletion';
import { bookItemTitle, bookSourceInfo } from './bookProcessingText';

interface Props {
  job: BookJob;
  events: readonly BookActivityEvent[];
  connected: boolean;
  reconnecting?: boolean;
  liveAfterSeq?: number | null;
  timing: BookTimingProjection;
  liveActivity?: BookLiveActivityProjection;
  projection?: BookActivityProjection;
  sourceStatus?: BookSourceStatus;
  knowledgePoints?: readonly KnowledgePointProjection[];
  bookTitle?: string;
  source?: FrozenBookSource | null;
  onReturnToReading: () => void;
  onOpenMaterial?: (skillKpId: string) => void;
  onCancel?: () => void;
  cancelPending?: boolean;
}

export function BookProcessingView({
  job,
  events,
  connected,
  reconnecting,
  liveAfterSeq,
  timing,
  liveActivity,
  projection,
  sourceStatus,
  knowledgePoints,
  bookTitle,
  source,
  onReturnToReading,
  onOpenMaterial,
  onCancel,
  cancelPending = false,
}: Props) {
  const { t } = useTranslation();
  const activity = projection ?? projectBookActivity(job, events);
  const terminal = isTerminalBookJobStatus(job.status);
  return (
    <section
      className="book-processing-view"
      aria-label={t('bookProcessing.timeline')}
      data-processing-kind={job.kind}
    >
      <div
        className="book-processing-scroll"
        data-testid="book-processing-scroll"
      >
        <div className="book-processing-content">
          <div className="book-processing-frame">
          <header className="book-processing-header">
            <div className="min-w-0 flex-1">
              <div className="book-processing-title-row">
              <h1 className="book-processing-title font-bold" title={bookTitle}>
                {bookTitle ||
                  t(
                    job.kind === 'structure'
                      ? 'bookProcessing.structure'
                      : 'bookProcessing.materials',
                  )}
              </h1>
              {terminal && (
                <span className="book-processing-status" data-status={job.status}>
                  {t(`bookProcessing.status.${job.status}`)}
                </span>
              )}
              </div>
              {bookSourceInfo(source) && (
                <p className="mt-1 text-xs text-muted-foreground">
                  {bookSourceInfo(source)}
                </p>
              )}
            </div>
          </header>
          <div className="book-processing-actions">
            <h2 className="min-w-0 text-sm font-semibold">
                {t(
                  job.kind === 'structure'
                    ? 'bookProcessing.structure'
                    : 'bookProcessing.materials',
                )}
            </h2>
            {!terminal && (
              <div className="book-processing-commands">
              {onCancel && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="min-h-11 px-2 text-muted-foreground"
                  disabled={cancelPending}
                  onClick={onCancel}
                  aria-label={t('bookProcessing.cancelRequest')}
                >
                  <StopCircle className="mr-1.5 size-3.5" aria-hidden="true" />
                  {t('common.cancel')}
                </Button>
              )}
              <Button
                variant="ghost"
                size="sm"
                className="min-h-11 shrink-0 px-2"
                onClick={onReturnToReading}
              >
                <ArrowLeft className="mr-1.5 size-3.5" aria-hidden="true" />
                {t('bookProcessing.reading')}
              </Button>
              </div>
            )}
          </div>
          {!terminal && (
            <p className="book-processing-tip text-xs text-muted-foreground">
              <ArrowUpRight className="size-3.5 shrink-0" aria-hidden="true" />
              {t('bookProcessing.backgroundTip')}
            </p>
          )}
          <div className="book-processing-body">
          <div className="book-processing-meta text-xs text-muted-foreground">
            {activity.currentItem && job.kind === 'materials' && (
              <p
                className="truncate"
                title={bookItemTitle(activity.currentItem)}
              >
                {bookItemTitle(activity.currentItem)}
              </p>
            )}
            {activity.materialProgress && (
              <p className="tabular-nums">
                {t(
                  'bookProcessing.materialProgress',
                  activity.materialProgress,
                )}
              </p>
            )}
            {!terminal && (
              <p
                className="tabular-nums"
                aria-label={t('bookProcessing.timing')}
              >
                {t('bookProcessing.elapsed')} ·{' '}
                <span data-testid="book-processing-elapsed">
                  {formatBookDuration(timing.roundMs)}
                </span>
              </p>
            )}
            {!connected && !terminal && (
              <p>
                {reconnecting && `${t('bookProcessing.reconnecting')} · `}
                {t('bookProcessing.confirmed')}
              </p>
            )}
            {activity.activityUnavailable && (
              <p role="status">{t('bookProcessing.unavailable')}</p>
            )}
          </div>
          <BookServiceMilestones
            job={job}
            timing={timing}
            sourceStatus={sourceStatus}
            agentActions={activity.agentActions}
            events={events}
            connected={connected}
            activityUnavailable={activity.activityUnavailable}
          />
          <BookMaterialDeliveryList
            job={job}
            knowledgePoints={knowledgePoints}
            onOpenMaterial={onOpenMaterial}
          />
          </div>
          {terminal && (
            <BookProcessingCompletion
              job={job}
              totalMs={timing.roundMs}
              onEnterLearning={onReturnToReading}
            />
          )}
          </div>
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
                connected={connected}
                liveAfterSeq={liveAfterSeq}
              />
            ))}
        </div>
      </div>
    </section>
  );
}
