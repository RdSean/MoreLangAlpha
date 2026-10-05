import { useEffect, useState } from 'react';
import { AlertCircle, Check, ChevronRight, Circle, Minus } from 'lucide-react';
import { useReducedMotion } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import { Loader } from '@/components/ui/loader';
import { TextShimmer } from '@/components/ui/text-shimmer';
import { createDateFormatter } from '@/lib/format';
import type { BookActivityEvent, BookJob, BookSourceStatus } from '../types';
import { bookActivityText } from './bookProcessingText';
import { isTerminalBookJobStatus } from './bookActivityProjection';
import {
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
  events = [],
  connected = true,
  activityUnavailable = false,
}: {
  job: BookJob;
  sourceStatus?: BookSourceStatus;
  timing: BookTimingProjection;
  agentActions: readonly BookActivityEvent[];
  events?: readonly BookActivityEvent[];
  connected?: boolean;
  activityUnavailable?: boolean;
}) {
  const { t } = useTranslation();
  const reduceMotion = useReducedMotion();
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);
  const item = selectBookExecutionItem(job);
  useEffect(
    () => setDiagnosticsOpen(false),
    [job.job_id, item?.item_id, item?.attempt, item?.execution_phase],
  );
  const isCurrentAttempt = (entry: BookActivityEvent) =>
    entry.job_id === job.job_id &&
    entry.item_id === item?.item_id &&
    (!item?.started_at ||
      Date.parse(entry.created_at) >= Date.parse(item.started_at));
  const currentEvents = events.filter(isCurrentAttempt);
  const latest = (entries: readonly BookActivityEvent[]) =>
    entries.reduce<BookActivityEvent | undefined>(
      (selected, entry) =>
        !selected || entry.seq > selected.seq ? entry : selected,
      undefined,
    );
  const action = latest(agentActions.filter(isCurrentAttempt));
  const service = latest(
    currentEvents.filter(
      (entry) =>
        entry.kind === 'progress' && entry.metadata.origin === 'service',
    ),
  );
  const diagnostic = latest(
    currentEvents.filter((entry) => entry.kind === 'tool'),
  );
  const formatTime = createDateFormatter({
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
  const terminal = isTerminalBookJobStatus(job.status);
  const animatedText = (text: string, active: boolean) =>
    active && connected && !reduceMotion ? (
      <TextShimmer as="span" className="book-active-action" duration={2.5}>
        {text}
      </TextShimmer>
    ) : (
      <span>{text}</span>
    );

  return (
    <ol
      className="book-service-timeline"
      aria-label={t('bookProcessing.milestones')}
    >
      {projectBookServiceMilestones(job, sourceStatus).map((milestone) => {
        const current = item?.execution_phase === milestone.phase;
        const active = current && !terminal;
        const matchesService =
          service &&
          (service.metadata.stage === 'service_source_preparing'
            ? milestone.phase === 'source_freezing'
            : service.metadata.stage === 'service_finalizing'
              ? milestone.phase === 'finalization'
              : service.metadata.stage === 'service_preparing'
                ? ['sandbox_preparation', 'input_staging'].includes(
                    milestone.phase,
                  )
                : false);
        const report =
          !activityUnavailable &&
          (milestone.phase === 'ptc_execution' && (current || terminal)
            ? action
            : current && matchesService
              ? service
              : undefined);
        const progress =
          milestone.phase === 'source_freezing'
            ? item?.preparation_progress
            : null;
        const phase = t(`bookProcessing.phase.${milestone.phase}`);
        const status =
          milestone.status === 'running'
            ? t('bookProcessing.phaseRunning')
            : t(`bookProcessing.status.${milestone.status}`);
        return (
          <li
            key={milestone.phase}
            aria-label={phase}
            className="book-service-node"
          >
            <span className="book-service-glyph" aria-hidden="true">
              {milestone.status === 'running' ? (
                <Loader size={14} />
              ) : milestone.status === 'completed' ? (
                <Check className="size-3.5 text-muted-foreground" />
              ) : milestone.status === 'failed' ? (
                <AlertCircle className="size-3.5 text-destructive" />
              ) : milestone.status === 'cancelled' ||
                milestone.status === 'not_run' ? (
                <Minus className="size-3.5 text-muted-foreground" />
              ) : (
                <Circle className="size-3.5 text-muted-foreground" />
              )}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-start justify-between gap-3 text-sm">
                <span className="min-w-0 break-words">
                  {animatedText(`${phase} · ${status}`, active)}
                </span>
                <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                  {formatBookDuration(
                    timing.phases.find(
                      (entry) => entry.phase === milestone.phase,
                    )?.ms ?? null,
                  )}
                </span>
              </div>
              {report && (
                <div
                  className="book-service-detail text-xs text-muted-foreground"
                  title={bookActivityText(report)}
                >
                  <span className="truncate">
                    {animatedText(bookActivityText(report), active)}
                  </span>
                  <time
                    dateTime={report.created_at}
                    className="shrink-0 tabular-nums"
                  >
                    {formatTime(Date.parse(report.created_at))}
                  </time>
                </div>
              )}
              {progress && current && (
                <p className="mt-1 text-xs tabular-nums text-muted-foreground">
                  {t('bookProcessing.resources', {
                    verified: progress.verified_resources,
                    total:
                      progress.total_resources ?? t('bookProcessing.unknown'),
                  })}
                  {progress.total_resources !== null &&
                    progress.verified_resources ===
                      progress.total_resources && (
                      <span className="block">
                        {t('bookProcessing.manifest')}
                      </span>
                    )}
                </p>
              )}
              {diagnostic &&
                current &&
                milestone.phase === 'ptc_execution' &&
                !activityUnavailable && (
                  <div className="mt-1 text-xs text-muted-foreground">
                    <button
                      type="button"
                      className="book-diagnostic-toggle flex items-center gap-1"
                      aria-expanded={diagnosticsOpen}
                      onClick={() => setDiagnosticsOpen(!diagnosticsOpen)}
                    >
                      <ChevronRight
                        className={`size-3 ${diagnosticsOpen ? 'rotate-90' : ''}`}
                        aria-hidden="true"
                      />
                      {t('bookProcessing.diagnostics')}
                    </button>
                    {diagnosticsOpen && (
                      <p
                        className="book-service-detail"
                        title={bookActivityText(diagnostic)}
                      >
                        <span className="truncate">
                          {bookActivityText(diagnostic)}
                        </span>
                        <time
                          dateTime={diagnostic.created_at}
                          className="shrink-0 tabular-nums"
                        >
                          {formatTime(Date.parse(diagnostic.created_at))}
                        </time>
                      </p>
                    )}
                  </div>
                )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
