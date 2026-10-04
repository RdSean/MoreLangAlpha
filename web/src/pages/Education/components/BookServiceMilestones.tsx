import { AlertCircle, Check, Circle, Minus } from 'lucide-react';
import { Loader } from '@/components/ui/loader';
import type { BookActivityEvent, BookJob, BookSourceStatus } from '../types';
import { useTranslation } from 'react-i18next';
import { BookAgentActions } from './BookAgentActions';
import {
  BOOK_PHASE_LABELS,
  BOOK_MILESTONE_STATUS_LABELS,
  formatBookDuration,
  projectBookServiceMilestones,
  selectBookExecutionItem,
  type BookTimingProjection,
} from './bookTimingProjection';

export function BookServiceMilestones({
  job,
  sourceStatus,
  timing,
  agentActions,
}: {
  job: BookJob;
  sourceStatus?: BookSourceStatus;
  timing: BookTimingProjection;
  agentActions: readonly BookActivityEvent[];
}) {
  useTranslation();
  const item = selectBookExecutionItem(job);
  const actions = agentActions.filter(
    (entry) =>
      entry.item_id === item?.item_id &&
      (!item?.started_at ||
        Date.parse(entry.created_at) >= Date.parse(item.started_at)),
  );
  return (
    <ol className="book-service-timeline space-y-4" aria-label="服务里程碑">
      {projectBookServiceMilestones(job, sourceStatus).map((milestone) => (
        <li
          key={milestone.phase}
          aria-label={BOOK_PHASE_LABELS[milestone.phase]}
          className="min-h-11 py-2 text-sm"
        >
          <div className="flex items-start gap-3">
            <span className="mt-0.5 shrink-0" aria-hidden="true">
              {milestone.status === 'running' ? (
                <Loader size={16} />
              ) : milestone.status === 'completed' ? (
                <Check className="size-4 text-muted-foreground" />
              ) : milestone.status === 'failed' ? (
                <AlertCircle className="size-4 text-destructive" />
              ) : milestone.status === 'cancelled' ||
                milestone.status === 'not_run' ? (
                <Minus className="size-4 text-muted-foreground" />
              ) : (
                <Circle className="size-4 text-muted-foreground" />
              )}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap justify-between gap-x-4 gap-y-1">
                <span className="break-words">
                  {BOOK_PHASE_LABELS[milestone.phase]} ·{' '}
                  {BOOK_MILESTONE_STATUS_LABELS[milestone.status]}
                </span>
                <span className="tabular-nums text-muted-foreground">
                  {formatBookDuration(
                    timing.phases.find(
                      (phase) => phase.phase === milestone.phase,
                    )?.ms ?? null,
                  )}
                </span>
              </div>
              {milestone.phase === 'ptc_execution' && (
                <BookAgentActions
                  key={`${job.job_id}:${item?.item_id}:${item?.attempt}`}
                  actions={actions}
                />
              )}
            </div>
          </div>
        </li>
      ))}
    </ol>
  );
}
