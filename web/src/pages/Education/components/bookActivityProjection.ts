import type {
  BookActivityEvent,
  BookJob,
  BookJobItem,
  BookJobItemKind,
  BookJobStatus,
} from '../types';

const TERMINAL_JOB_STATUSES = new Set<BookJobStatus>([
  'succeeded',
  'partially_succeeded',
  'failed',
  'cancelled',
]);

const PROGRESS_STAGES: Record<BookJobItemKind, ReadonlySet<string>> = {
  structure: new Set([
    'structure_reading',
    'structure_organizing',
    'structure_splitting',
    'structure_validating',
  ]),
  material: new Set([
    'material_reading',
    'material_organizing',
    'material_writing',
    'material_validating',
  ]),
  supplementary: new Set([
    'supplementary_reading',
    'supplementary_organizing',
    'supplementary_validating',
  ]),
};

export interface BookActivityProjection {
  jobStatus: BookJobStatus;
  activityUnavailable: boolean;
  materialProgress: { completed: number; total: number } | null;
  currentItem: BookJobItem | null;
  currentStage: BookActivityEvent | null;
  currentDescription: string;
  milestones: BookActivityEvent[];
  toolDetails: BookActivityEvent[];
}

function fallbackDescription(item: BookJobItem | null, kind: BookJob['kind']) {
  if (item?.kind === 'supplementary') return '正在生成附加材料';
  if (item?.kind === 'material') return '正在生成讲义';
  if (item?.kind === 'structure' || kind === 'structure') return '正在分析教材结构';
  return '正在处理教材';
}

export function isTerminalBookJobStatus(status: BookJobStatus) {
  return TERMINAL_JOB_STATUSES.has(status);
}

export function projectBookActivity(
  job: BookJob,
  events: readonly BookActivityEvent[],
): BookActivityProjection {
  const isTerminal = isTerminalBookJobStatus(job.status);
  const currentItem = isTerminal
    ? null
    : [...job.items]
      .sort((left, right) => left.position - right.position)
      .find((entry) => entry.status === 'running') ?? null;
  const progressEvents = currentItem
    ? events.filter((entry) => {
      const stage = entry.metadata.stage;
      return entry.kind === 'progress'
        && entry.item_id === currentItem.item_id
        && typeof stage === 'string'
        && PROGRESS_STAGES[currentItem.kind].has(stage);
    })
    : [];
  const currentStage = progressEvents.reduce<BookActivityEvent | null>(
    (latest, entry) => (!latest || entry.seq > latest.seq ? entry : latest),
    null,
  );
  const materialItems = job.items.filter((entry) => entry.kind === 'material');
  const activityUnavailable = job.activity_status === 'unavailable';
  const currentDescription = activityUnavailable && !isTerminal
    ? `${job.kind === 'structure' ? '结构分析' : '讲义生成'}仍在继续`
    : currentStage?.message ?? fallbackDescription(currentItem, job.kind);

  return {
    jobStatus: job.status,
    activityUnavailable,
    materialProgress: job.kind === 'materials'
      ? {
        completed: materialItems.filter((entry) => entry.status === 'succeeded').length,
        total: materialItems.length,
      }
      : null,
    currentItem,
    currentStage,
    currentDescription: activityUnavailable && !isTerminal
      ? `活动暂不可用，${currentDescription}`
      : currentDescription,
    milestones: events.filter((entry) => entry.kind !== 'tool' && entry.kind !== 'progress'),
    toolDetails: events.filter((entry) => entry.kind === 'tool'),
  };
}
