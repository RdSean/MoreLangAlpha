import { useEffect, useState } from 'react';
import { AlertCircle, Check, ChevronDown, Circle, Minus, X } from 'lucide-react';
import { Loader } from '@/components/ui/loader';
import { useSearchParams } from 'react-router-dom';
import type { BookActivityEvent, BookJob, BookJobStatus } from '../types';
import { BookLiveActivity } from './BookLiveActivity';
import {
  isTerminalBookJobStatus,
  projectBookActivity,
} from './bookActivityProjection';

const STATUS_LABELS: Record<BookJobStatus, string> = {
  queued: '等待开始',
  running: '处理中',
  succeeded: '已完成',
  partially_succeeded: '部分完成',
  failed: '处理失败',
  cancelled: '已取消',
};

interface BookActivityPanelProps {
  job: BookJob;
  events: readonly BookActivityEvent[];
  reconnecting?: boolean;
  connected?: boolean;
  liveAfterSeq?: number | null;
  onClose?: () => void;
}

export function BookActivityPanel({
  job,
  events,
  reconnecting = false,
  connected = true,
  liveAfterSeq,
  onClose,
}: BookActivityPanelProps) {
  const activity = projectBookActivity(job, events);
  const [diagnosticJobId, setDiagnosticJobId] = useState<string | null>(null);
  const diagnosticsOpen = diagnosticJobId === job.job_id;
  useEffect(() => setDiagnosticJobId(null), [job.job_id]);
  const terminalError = job.status === 'failed' || job.status === 'partially_succeeded';

  return (
    <aside className="flex min-h-0 flex-col border-l bg-background" aria-label="教材处理活动">
      <header className="border-b px-4 py-3">
        <div className="flex min-h-11 items-center justify-between gap-3">
          <h2 className="text-sm font-semibold text-foreground">处理活动</h2>
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">{STATUS_LABELS[job.status]}</span>
            {onClose && (
              <button
                type="button"
                className="inline-flex size-11 items-center justify-center rounded-md text-muted-foreground hover:bg-[var(--color-bg-hover)] hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                onClick={onClose}
                aria-label="关闭处理活动"
              >
                <X className="size-4" aria-hidden="true" />
              </button>
            )}
          </div>
        </div>
        {activity.materialProgress && (
          <p className="text-sm text-foreground">
            已完成 {activity.materialProgress.completed}/{activity.materialProgress.total} 份讲义
          </p>
        )}
      </header>

      {!isTerminalBookJobStatus(job.status) && (
        <div className="shrink-0 border-b px-4 py-3">
          <div className="flex min-h-12 items-start gap-3">
            <span className="mt-0.5 shrink-0" aria-hidden="true"><Loader size={16} /></span>
            <div className="min-w-0 flex-1">
              {activity.currentObjectLabel && <p className="break-words text-xs text-muted-foreground">{activity.currentObjectLabel}</p>}
              <p className="break-words text-sm font-medium text-foreground" aria-live="polite">{activity.currentDescription}</p>
              {reconnecting && <p className="mt-1 text-xs text-muted-foreground">正在重新连接活动流</p>}
              {activity.currentItem && !activity.activityUnavailable && (
                <BookLiveActivity key={`${job.job_id}:${activity.currentItem.item_id}:${activity.currentItem.attempt}`}
                  job={job} item={activity.currentItem} events={events} connected={connected && !reconnecting} liveAfterSeq={liveAfterSeq} />
              )}
            </div>
          </div>
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4" aria-live="polite">
        {activity.activityUnavailable && (
          <div className="mb-4 flex gap-2 border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-100">
            <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            <span className="min-w-0 break-words">活动暂不可用，任务状态仍会继续更新。</span>
          </div>
        )}

        <div className="mt-4 space-y-4">
          {activity.groups.map((group) => (
            <section key={group.key} className="min-w-0">
              {group.label && <h3 className="mb-2 break-words text-xs font-medium text-foreground">{group.label}</h3>}
              <ol className="space-y-2">
                {group.events.filter((entry) => activity.activityUnavailable || entry.seq !== activity.currentStage?.seq).map((entry) => (
                  <li key={entry.seq} className="flex min-h-8 items-start gap-3 text-sm">
                    <ActivityIcon entry={entry} />
                    <span className="min-w-0 break-words text-muted-foreground">{entry.message}</span>
                  </li>
                ))}
              </ol>
            </section>
          ))}
        </div>

        {activity.toolDetails.length > 0 && (
          <div className="mt-5 border-t pt-3">
            <button type="button" aria-expanded={diagnosticsOpen}
              className="flex min-h-11 w-full items-center gap-2 text-left text-sm text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              onClick={() => setDiagnosticJobId(diagnosticsOpen ? null : job.job_id)}>
              <ChevronDown className={`size-4 shrink-0 ${diagnosticsOpen ? '' : '-rotate-90'}`} aria-hidden="true" />
              诊断明细（{activity.toolDetails.length}）
            </button>
            {diagnosticsOpen && <ol className="space-y-2 pb-2 pl-6 text-xs text-muted-foreground">
              {activity.toolDetails.map((entry) => (
                <li key={entry.seq} className="break-words">{entry.message}</li>
              ))}
            </ol>}
          </div>
        )}

        {isTerminalBookJobStatus(job.status) && (
          <div className={`mt-4 flex min-h-11 items-start gap-3 text-sm ${terminalError ? 'text-destructive' : 'text-foreground'}`}>
            {terminalError
              ? <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              : job.status === 'succeeded'
                ? <Check className="mt-0.5 size-4 shrink-0 text-emerald-600" aria-hidden="true" />
                : <Minus className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />}
            <span className="min-w-0 break-words">{job.safe_error || STATUS_LABELS[job.status]}</span>
          </div>
        )}
      </div>
    </aside>
  );
}

function ActivityIcon({ entry }: { entry: BookActivityEvent }) {
  if (entry.status === 'failed') return <AlertCircle className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden="true" />;
  if (entry.status === 'cancelled' || entry.status === 'not_run') return <Minus className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />;
  if (entry.kind !== 'progress' && entry.kind !== 'summary' && entry.status === 'succeeded') return <Check className="mt-0.5 size-4 shrink-0 text-emerald-600" aria-hidden="true" />;
  return <Circle className="mt-1 size-3 shrink-0 text-muted-foreground" aria-hidden="true" />;
}

export function RoutedBookActivityPanel(props: Omit<BookActivityPanelProps, 'onClose'>) {
  const [searchParams, setSearchParams] = useSearchParams();
  if (searchParams.get('activity') !== props.job.job_id) return null;

  const close = () => {
    const next = new URLSearchParams(searchParams);
    next.delete('activity');
    setSearchParams(next, { replace: true });
  };

  return <BookActivityPanel {...props} onClose={close} />;
}
