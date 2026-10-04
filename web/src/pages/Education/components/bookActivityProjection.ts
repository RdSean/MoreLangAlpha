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

export const BOOK_JOB_STATUS_LABELS: Record<BookJobStatus, string> = {
  queued: '等待开始',
  running: '处理中',
  succeeded: '已完成',
  partially_succeeded: '部分完成',
  failed: '处理失败',
  cancelled: '已取消',
};

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

function acceptsProgress(entry: BookActivityEvent, kind?: BookJobItemKind) {
  const stage = entry.metadata.stage;
  if (typeof stage !== 'string') return false;
  if (
    stage === 'service_preparing' ||
    stage === 'service_finalizing' ||
    stage === 'service_source_preparing'
  )
    return entry.metadata.origin === 'service';
  return kind
    ? PROGRESS_STAGES[kind].has(stage)
    : Object.values(PROGRESS_STAGES).some((stages) => stages.has(stage));
}

export interface BookActivityProjection {
  jobStatus: BookJobStatus;
  activityUnavailable: boolean;
  materialProgress: { completed: number; total: number } | null;
  currentItem: BookJobItem | null;
  currentStage: BookActivityEvent | null;
  currentDescription: string;
  currentObjectLabel: string | null;
  milestones: BookActivityEvent[];
  groups: {
    key: number;
    itemId: string | null;
    label: string | null;
    events: BookActivityEvent[];
  }[];
  toolDetails: BookActivityEvent[];
  agentActions: BookActivityEvent[];
}

export function isAgentBookActivity(entry: BookActivityEvent): boolean {
  return (
    entry.kind === 'progress' &&
    entry.metadata.origin !== 'service' &&
    typeof entry.metadata.stage === 'string' &&
    Object.values(PROGRESS_STAGES).some((stages) =>
      stages.has(entry.metadata.stage as string),
    )
  );
}

function itemLabel(item: BookJobItem | undefined) {
  if (!item) return '教材处理项';
  if (item.kind === 'structure') return '教材结构分析';
  if (item.kind === 'supplementary') return '全书附加材料';
  const title = item.knowledge_point_title?.trim();
  return title ? `知识点：${title}` : `讲义任务（本次第 ${item.position} 项）`;
}

function fallbackDescription(item: BookJobItem | null, kind: BookJob['kind']) {
  if (item?.execution_phase === 'source_freezing') return '正在准备教材来源';
  if (item?.execution_phase === 'initial_queue') return '等待准备教材来源';
  if (item?.execution_phase === 'runtime_queue') return '等待执行容量';
  if (item?.execution_phase === 'sandbox_preparation')
    return '正在准备运行环境';
  if (item?.execution_phase === 'input_staging') return '正在准备输入文件';
  if (item?.execution_phase === 'finalization') return '正在验收并提交产物';
  if (item?.kind === 'supplementary') return '正在生成附加材料';
  if (item?.kind === 'material') return '正在生成讲义';
  if (item?.kind === 'structure' || kind === 'structure')
    return '正在分析教材结构';
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
  const itemsById = new Map(job.items.map((item) => [item.item_id, item]));
  const milestones: BookActivityEvent[] = [];
  for (const entry of [...events].sort((left, right) => left.seq - right.seq)) {
    if (entry.kind === 'tool') continue;
    if (entry.kind === 'progress') {
      const item = entry.item_id ? itemsById.get(entry.item_id) : undefined;
      const stage = entry.metadata.stage;
      if (!acceptsProgress(entry, item?.kind)) continue;
      const previous = milestones.at(-1);
      if (
        previous?.kind === 'progress' &&
        previous.item_id === entry.item_id &&
        previous.metadata.stage === stage &&
        previous.metadata.action === entry.metadata.action
      ) {
        milestones[milestones.length - 1] = entry;
        continue;
      }
    }
    milestones.push(entry);
  }
  const groups: BookActivityProjection['groups'] = [];
  for (const entry of milestones) {
    const itemId =
      entry.kind === 'summary' || entry.kind === 'job' ? null : entry.item_id;
    const previous = groups.at(-1);
    if (itemId && previous?.itemId === itemId) previous.events.push(entry);
    else
      groups.push({
        key: entry.seq,
        itemId,
        label: itemId ? itemLabel(itemsById.get(itemId)) : null,
        events: [entry],
      });
  }
  const currentItem = isTerminal
    ? null
    : ([...job.items]
        .sort((left, right) => left.position - right.position)
        .find((entry) => entry.status === 'running') ??
      job.items.find((entry) => entry.status === 'queued') ??
      null);
  const progressEvents = currentItem
    ? events.filter((entry) => {
        return (
          entry.kind === 'progress' &&
          entry.item_id === currentItem.item_id &&
          (!currentItem.started_at ||
            Date.parse(entry.created_at) >=
              Date.parse(currentItem.started_at)) &&
          acceptsProgress(entry, currentItem.kind)
        );
      })
    : [];
  const currentStage = progressEvents.reduce<BookActivityEvent | null>(
    (latest, entry) => (!latest || entry.seq > latest.seq ? entry : latest),
    null,
  );
  const materialItems = job.items.filter((entry) => entry.kind === 'material');
  const activityUnavailable = job.activity_status === 'unavailable';
  const currentDescription =
    activityUnavailable && !isTerminal
      ? `${job.kind === 'structure' ? '结构分析' : '讲义生成'}仍在继续`
      : (currentStage?.message ?? fallbackDescription(currentItem, job.kind));

  return {
    jobStatus: job.status,
    activityUnavailable,
    materialProgress:
      job.kind === 'materials'
        ? (job.material_progress ?? {
            completed: materialItems.filter(
              (entry) => entry.status === 'succeeded',
            ).length,
            total: materialItems.length,
          })
        : null,
    currentItem,
    currentStage,
    currentDescription:
      activityUnavailable && !isTerminal
        ? `活动暂不可用，${currentDescription}`
        : currentDescription,
    currentObjectLabel: currentItem ? itemLabel(currentItem) : null,
    milestones,
    groups,
    toolDetails: events.filter((entry) => entry.kind === 'tool'),
    agentActions: milestones.filter(isAgentBookActivity),
  };
}
