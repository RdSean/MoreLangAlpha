import { createFormatter } from '@/lib/format';
import type { BookExecutionPhase, BookJob, BookTimingStatus } from '../types';
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

export function projectBookTiming(
  job: BookJob | undefined,
  now: number | null,
): BookTimingProjection {
  const terminal = job ? isTerminalBookJobStatus(job.status) : false;
  const item =
    job?.items.find((entry) => entry.status === 'running') ?? job?.items.at(-1);
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
  if (ms === null || !Number.isFinite(ms) || ms < 0) return '未记录';
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return `${integer(seconds)} 秒`;
  if (seconds < 3600)
    return `${integer(Math.floor(seconds / 60))} 分 ${integer(seconds % 60)} 秒`;
  return `${integer(Math.floor(seconds / 3600))} 小时 ${integer(Math.floor((seconds % 3600) / 60))} 分`;
}
