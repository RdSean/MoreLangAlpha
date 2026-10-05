import { createFormatter } from '@/lib/format';
import i18n from '@/i18n';
import type {
  BookExecutionPhase,
  BookJob,
  BookJobItem,
  BookSourceStatus,
  BookTimingStatus,
} from '../types';
import { isTerminalBookJobStatus } from './bookActivityProjection';

export const BOOK_PHASE_LABELS: Record<BookExecutionPhase, string> = {
  initial_queue: '受理等待',
  source_freezing: '来源准备',
  runtime_queue: '执行等待',
  sandbox_preparation: '运行环境准备',
  input_staging: '输入文件准备',
  ptc_execution: 'PTC 执行',
  finalization: '验收提交',
};

function elapsed(
  start: string | null | undefined,
  end: number | null,
): number | null {
  const from = Date.parse(start ?? '');
  return Number.isFinite(from) &&
    end !== null &&
    Number.isFinite(end) &&
    end >= from
    ? end - from
    : null;
}

export interface BookTimingProjection {
  roundMs: number | null;
  attemptMs: number | null;
  attempt: number | null;
  status: BookTimingStatus;
  phases: { phase: BookExecutionPhase; ms: number | null; active: boolean }[];
}

export function hasMatchingBookTiming(
  job: BookJob,
  item: BookJobItem,
): boolean {
  return Boolean(
    item.timing_summary &&
      item.timing_summary.attempt === item.attempt &&
      item.timing_summary.request_round === (job.request_round ?? 1),
  );
}

function latestExecuted(
  items: readonly BookJobItem[],
): BookJobItem | undefined {
  return [...items]
    .filter((item) => item.attempt > 0 && item.status !== 'not_run')
    .sort((left, right) => {
      const leftStart = Date.parse(
        left.started_at ?? left.timing_summary?.claimed_at ?? '',
      );
      const rightStart = Date.parse(
        right.started_at ?? right.timing_summary?.claimed_at ?? '',
      );
      return (
        (Number.isFinite(rightStart) ? rightStart : 0) -
          (Number.isFinite(leftStart) ? leftStart : 0) ||
        right.position - left.position
      );
    })[0];
}

export function selectBookExecutionItem(job: BookJob): BookJobItem | null {
  if (isTerminalBookJobStatus(job.status))
    return latestExecuted(job.items) ?? null;
  return (
    job.items.find((item) => item.status === 'running') ??
    [...job.items]
      .sort((left, right) => left.position - right.position)
      .find((item) => item.status === 'queued') ??
    null
  );
}

export function selectBookTimingItem(job: BookJob): BookJobItem | null {
  const item = selectBookExecutionItem(job);
  return item && hasMatchingBookTiming(job, item) ? item : null;
}

export type BookMilestoneStatus =
  | 'waiting'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'not_run';
export const BOOK_MILESTONE_STATUS_LABELS: Record<BookMilestoneStatus, string> =
  {
    waiting: '等待',
    running: '进行中',
    completed: '已完成',
    failed: '处理失败',
    cancelled: '已取消',
    not_run: '未执行',
  };

export function projectBookServiceMilestones(
  job: BookJob,
  sourceStatus?: BookSourceStatus,
) {
  const item = selectBookExecutionItem(job);
  const phases = (
    Object.keys(BOOK_PHASE_LABELS) as BookExecutionPhase[]
  ).filter((phase) => job.kind === 'structure' || phase !== 'source_freezing');
  const currentPhase =
    item?.execution_phase ??
    (job.status === 'queued' ? 'initial_queue' : undefined);
  const currentIndex = currentPhase ? phases.indexOf(currentPhase) : -1;
  const terminal = isTerminalBookJobStatus(job.status);
  return phases.map(
    (
      phase,
      index,
    ): { phase: BookExecutionPhase; status: BookMilestoneStatus } => {
      let status: BookMilestoneStatus = terminal ? 'not_run' : 'waiting';
      if (
        item?.status === 'succeeded' ||
        (currentIndex >= 0 && index < currentIndex)
      )
        status = 'completed';
      else if (index === currentIndex) {
        status =
          item?.status === 'failed'
            ? 'failed'
            : item?.status === 'cancelled'
              ? 'cancelled'
              : terminal
                ? job.status === 'cancelled'
                  ? 'cancelled'
                  : 'failed'
                : phase === 'initial_queue' || phase === 'runtime_queue'
                  ? 'waiting'
                  : 'running';
      }
      if (phase === 'source_freezing' && sourceStatus) {
        status =
          sourceStatus === 'ready'
            ? 'completed'
            : sourceStatus === 'failed'
              ? 'failed'
              : sourceStatus === 'cancelled'
                ? 'cancelled'
                : sourceStatus === 'preparing'
                  ? 'running'
                  : 'waiting';
      }
      return { phase, status };
    },
  );
}

export function projectBookTiming(
  job: BookJob | undefined,
  now: number | null,
): BookTimingProjection {
  const terminal = job ? isTerminalBookJobStatus(job.status) : false;
  const item = job ? selectBookTimingItem(job) : null;
  const timing =
    item?.timing_summary?.attempt === item?.attempt &&
    item?.timing_summary?.request_round === (job?.request_round ?? 1)
      ? item?.timing_summary
      : null;
  return {
    roundMs: elapsed(
      job?.round_accepted_at,
      terminal ? Date.parse(job?.finished_at ?? '') : now,
    ),
    attemptMs: timing
      ? timing.terminal_at
        ? timing.total_ms
        : elapsed(timing.queued_at, now)
      : null,
    attempt: timing?.attempt ?? null,
    status: timing?.status ?? 'unavailable',
    phases: (Object.keys(BOOK_PHASE_LABELS) as BookExecutionPhase[]).map(
      (phase) => {
        const segment = timing?.phases.find((entry) => entry.phase === phase);
        const active =
          !terminal &&
          item?.status === 'running' &&
          item.execution_phase === phase &&
          Boolean(segment?.started_at) &&
          segment?.ended_at === null &&
          segment.status !== 'unavailable';
        const liveMs = active ? elapsed(segment?.started_at, now) : null;
        return {
          phase,
          active,
          ms: active
            ? segment?.status === 'partial' || liveMs === null
              ? null
              : (segment?.measured_ms ?? 0) + liveMs
            : (segment?.measured_ms ?? null),
        };
      },
    ),
  };
}

const integer = createFormatter({ maximumFractionDigits: 0 });
export function formatBookDuration(ms: number | null): string {
  if (ms === null || !Number.isFinite(ms) || ms < 0) return i18n.t('bookProcessing.missing');
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return i18n.t('bookProcessing.seconds', { count: seconds });
  if (seconds < 3600)
    return i18n.t('bookProcessing.minutes', { minutes: integer(Math.floor(seconds / 60)), seconds: integer(seconds % 60) });
  return i18n.t('bookProcessing.hours', { hours: integer(Math.floor(seconds / 3600)), minutes: integer(Math.floor((seconds % 3600) / 60)) });
}
