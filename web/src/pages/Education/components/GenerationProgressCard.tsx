import { useEffect, useRef, useState } from 'react';
import { AlertTriangle, Check, ChevronDown, Loader2, Timer } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useStructureGenerationProgress } from '../queries';
import './GenerationProgressCard.css';

export type GenerationJobStatus =
  | 'queued'
  | 'preparing'
  | 'running'
  | 'validating'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface GenerationJobView {
  generation_job_id: string;
  status: GenerationJobStatus;
  attempt_count?: number;
  created_at?: string | null;
  updated_at?: string | null;
  started_at?: string | null;
  heartbeat_at?: string | null;
  error_message?: string | null;
}

const timelineStages: Array<{ id: string; label: string }> = [
  { id: 'queued', label: '任务已排队' },
  { id: 'preparing', label: '准备解析输入' },
  { id: 'running', label: '分析教材结构' },
  { id: 'validating', label: '校验并归档结果' },
  { id: 'done', label: '进入人工审阅' },
];

function timelineStageIndex(status: GenerationJobStatus | undefined) {
  switch (status) {
    case 'queued': return 0;
    case 'preparing': return 1;
    case 'running': return 2;
    case 'validating': return 3;
    case 'completed': return 4;
    default: return -1;
  }
}

function formatElapsed(from: string | null | undefined, to: string | null | undefined) {
  if (!from) return undefined;
  const start = new Date(from).getTime();
  const end = to ? new Date(to).getTime() : Date.now();
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) return undefined;
  const totalSeconds = Math.floor((end - start) / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return minutes > 0 ? `${minutes} 分 ${seconds} 秒` : `${seconds} 秒`;
}

function useNow(active: boolean) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) {
      setNow(Date.now());
      return;
    }
    const handle = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => window.clearInterval(handle);
  }, [active]);
  return now;
}

const progressStatusIcon: Record<string, React.ReactNode> = {
  completed: <Check className="size-3" />,
  failed: <AlertTriangle className="size-3" />,
  running: <Loader2 className="size-3 animate-spin" />,
  skipped: <span className="size-1.5 rounded-full bg-current opacity-60" />,
};

export default function GenerationProgressCard({
  jobId,
  job,
  heading = '处理进度',
  note,
  className,
  'data-testid': testId,
}: {
  jobId: string | undefined;
  job: GenerationJobView;
  heading?: string;
  note?: string;
  className?: string;
  'data-testid'?: string;
}) {
  const running = ['queued', 'preparing', 'running', 'validating'].includes(job.status);
  const now = useNow(running);
  const progress = useStructureGenerationProgress(jobId, Boolean(jobId));
  const [expanded, setExpanded] = useState(true);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const activeIndex = timelineStageIndex(job.status);
  const failed = job.status === 'failed' || job.status === 'cancelled';
  const elapsed = formatElapsed(
    job.started_at ?? job.created_at,
    running ? new Date(now).toISOString() : job.updated_at,
  );
  const events = progress.data?.events ?? [];
  const visibleEvents = !showAll && events.length > 12 ? events.slice(-8) : events;
  const hiddenCount = events.length - visibleEvents.length;

  useEffect(() => {
    setExpanded(running);
  }, [running]);

  useEffect(() => {
    const node = listRef.current;
    if (!node || !running) return;
    node.scrollTop = node.scrollHeight;
  }, [running, events.length]);

  return (
    <div
      className={cn('generation-progress grid gap-4', className)}
      data-testid={testId ?? 'generation-progress'}
    >
      <div className="min-w-0">
        <p className="text-sm font-medium">{heading}</p>
        {note && <p className="text-xs text-muted-foreground">{note}</p>}
        <div className="generation-progress-head mt-3">
          <span className="textbook-timeline-dot shrink-0" style={{ width: 24, height: 24 }}>
            {failed
              ? <AlertTriangle className="size-3.5" />
              : job.status === 'completed'
                ? <Check className="size-3.5" />
                : <Loader2 className="size-3.5 animate-spin" />}
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">
              {running ? '正在生成' : job.status === 'completed' ? '已生成' : '已停止'} ·{' '}
              {timelineStages[Math.max(activeIndex, job.status === 'completed' ? 4 : 0)]?.label}
            </p>
            <p className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] text-muted-foreground">
              <span className="inline-flex items-center gap-1">
                <Timer className="size-3" />
                {elapsed ?? '—'}
              </span>
              {job.attempt_count ? <span>第 {job.attempt_count} 次尝试</span> : null}
              <span>阶段 {Math.max(activeIndex, 0) + 1}/5</span>
            </p>
          </div>
          <button
            type="button"
            className="textbook-activity-toggle"
            aria-expanded={detailsOpen}
            onClick={() => setDetailsOpen((value) => !value)}
          >
            {detailsOpen ? '收起' : '展开'}
            <ChevronDown className={cn('size-3.5 transition-transform', detailsOpen && 'rotate-180')} />
          </button>
        </div>
        {detailsOpen && (
          <div className="textbook-timeline mt-3 pl-1" data-testid="structure-generation-timeline">
            {timelineStages.map((stage, index) => {
              const done = !failed && activeIndex > index;
              const active = !failed && activeIndex === index;
              const stageFailed = failed && index === Math.max(activeIndex, 0);
              return (
                <div
                  key={stage.id}
                  className={cn(
                    'textbook-timeline-row',
                    done && 'is-done',
                    active && 'is-active',
                    stageFailed && 'is-failed',
                  )}
                >
                  <span className="textbook-timeline-dot">
                    {done
                      ? <Check className="size-3" />
                      : active
                        ? <Loader2 className="size-3 animate-spin" />
                        : stageFailed
                          ? <AlertTriangle className="size-3" />
                          : <span className="size-1.5 rounded-full bg-current" />}
                  </span>
                  <span className="min-w-0 truncate">{stage.label}</span>
                  {active && <span className="textbook-timeline-time">进行中</span>}
                </div>
              );
            })}
          </div>
        )}
        {job.heartbeat_at && (
          <p className="mt-2 font-mono text-[11px] text-muted-foreground">
            最近心跳 {new Date(job.heartbeat_at).toLocaleTimeString()}
          </p>
        )}
        {job.error_message && (
          <p className="mt-1 text-xs" style={{ color: 'var(--color-loss)' }}>{job.error_message}</p>
        )}
      </div>

      <div className="textbook-activity-panel" data-testid="structure-activity-panel">
        <div className="textbook-activity-header">
          <div className="min-w-0">
            <p className="text-sm font-medium">处理活动</p>
            <p className="text-xs text-muted-foreground">
              {running
                ? '正在同步服务端处理事件，可关闭页面，任务会继续。'
                : events.length > 0
                  ? `已完成 ${events.length} 个可读处理步骤。`
                  : '暂无可读处理事件。'}
            </p>
          </div>
          <button
            type="button"
            className="textbook-activity-toggle"
            aria-expanded={expanded}
            onClick={() => setExpanded((value) => !value)}
          >
            {expanded ? '收起' : '展开'}
            <ChevronDown className={cn('size-3.5 transition-transform', expanded && 'rotate-180')} />
          </button>
        </div>
        {expanded && (
          <>
            <div className="textbook-activity-list" ref={listRef} data-testid="structure-activity-list">
              {progress.isPending ? (
                <p className="textbook-activity-empty">
                  <Loader2 className="mr-2 inline size-3 animate-spin" />
                  正在读取处理活动…
                </p>
              ) : progress.isError ? (
                <p className="textbook-activity-empty">暂时无法读取处理活动。</p>
              ) : events.length === 0 ? (
                <p className="textbook-activity-empty">
                  {running ? '任务已启动，等待首个处理事件…' : '没有记录到可读处理事件。'}
                </p>
              ) : (
                <>
                  {hiddenCount > 0 && (
                    <button
                      type="button"
                      className="textbook-activity-more"
                      onClick={() => setShowAll(true)}
                    >
                      还有 {hiddenCount} 条较早记录，展开查看
                    </button>
                  )}
                  {visibleEvents.map((event) => (
                    <div
                      key={`${event.sequence}-${event.label}`}
                      className={cn(
                        'textbook-activity-row',
                        event.status === 'running' && 'is-running',
                        event.status === 'failed' && 'is-failed',
                      )}
                    >
                      <span className="textbook-activity-dot">
                        {progressStatusIcon[event.status] ?? <span className="size-1.5 rounded-full bg-current" />}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="truncate" title={event.label}>
                          {event.label}
                          {event.count > 1 && (
                            <span className="ml-1.5 font-mono text-[11px] text-muted-foreground">×{event.count}</span>
                          )}
                        </p>
                        {event.detail && (
                          <p className="truncate font-mono text-[11px] text-muted-foreground" title={event.detail}>
                            {event.detail}
                          </p>
                        )}
                      </div>
                      {event.timestamp && (
                        <span className="textbook-timeline-time shrink-0">
                          {new Date(event.timestamp).toLocaleTimeString()}
                        </span>
                      )}
                    </div>
                  ))}
                </>
              )}
            </div>
            {progress.data?.truncated && (
              <p className="mt-2 text-[11px] text-muted-foreground">只展示最近的处理记录。</p>
            )}
          </>
        )}
      </div>
    </div>
  );
}
