import { AlertCircle, Check, ChevronDown, LoaderCircle, X } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import type { BookActivityEvent, BookJob, BookJobStatus } from '../types';
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
  onClose?: () => void;
}

export function BookActivityPanel({
  job,
  events,
  reconnecting = false,
  onClose,
}: BookActivityPanelProps) {
  const activity = projectBookActivity(job, events);
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

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4" aria-live="polite">
        {activity.activityUnavailable && (
          <div className="mb-4 flex gap-2 border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-100">
            <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            <span className="min-w-0 break-words">活动暂不可用，任务状态仍会继续更新。</span>
          </div>
        )}

        {!isTerminalBookJobStatus(job.status) && (
          <div className="flex min-h-12 items-start gap-3">
            <LoaderCircle className="mt-0.5 size-4 shrink-0 animate-spin text-primary motion-reduce:animate-none" aria-hidden="true" />
            <div className="min-w-0">
              <p className="break-words text-sm font-medium text-foreground">
                {activity.currentDescription}
              </p>
              {reconnecting && <p className="mt-1 text-xs text-muted-foreground">正在重新连接活动流</p>}
            </div>
          </div>
        )}

        <ol className="mt-4 space-y-3">
          {activity.milestones.map((entry) => (
            <li key={entry.seq} className="flex min-h-10 items-start gap-3 text-sm">
              {entry.status === 'failed'
                ? <AlertCircle className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden="true" />
                : <Check className="mt-0.5 size-4 shrink-0 text-emerald-600" aria-hidden="true" />}
              <span className="min-w-0 break-words text-muted-foreground">{entry.message}</span>
            </li>
          ))}
        </ol>

        {activity.toolDetails.length > 0 && (
          <details className="mt-5 border-t pt-3">
            <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 text-sm text-muted-foreground">
              <ChevronDown className="size-4" aria-hidden="true" />
              运行明细（{activity.toolDetails.length}）
            </summary>
            <ol className="space-y-2 pb-2 pl-6 text-xs text-muted-foreground">
              {activity.toolDetails.map((entry) => (
                <li key={entry.seq} className="break-words">{entry.message}</li>
              ))}
            </ol>
          </details>
        )}

        {isTerminalBookJobStatus(job.status) && (
          <div className={`mt-4 flex min-h-11 items-start gap-3 text-sm ${terminalError ? 'text-destructive' : 'text-foreground'}`}>
            {terminalError
              ? <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              : <Check className="mt-0.5 size-4 shrink-0 text-emerald-600" aria-hidden="true" />}
            <span className="min-w-0 break-words">{job.safe_error || STATUS_LABELS[job.status]}</span>
          </div>
        )}
      </div>
    </aside>
  );
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
