import { api } from '@/api/client';
import type {
  CreateEducationTaskInput,
  EducationAsset,
  EducationHomeworkDictionaries,
  EducationMember,
  EducationTask,
  EducationTaskCalendar,
  EducationTaskCalendarRequest,
  EducationTaskDetail,
  EducationTaskReview,
  EducationTaskSubmission,
  LearningAssignment,
  LearningChatSpace,
  LearningItem,
  LearningItemKind,
  ParentLearningTranscript,
  StudentKnowledgePointLesson,
  StudentTextbookStructure,
  SubmitEducationTaskInput,
} from './types';
import type {
  BookActivityEvent,
  BookActivityPage,
  BookAssignment,
  BookAssignmentRequest,
  BookJob,
  BookJobStatus,
  BookSourceSlice,
  BookSourceCandidate,
  BookStructure,
  CreateBookJobInput,
  CreateManagedTextbookInput,
  CreateManagedTextbookResponse,
  KnowledgePointMaterial,
  ManagedTextbookSummary,
  TextbookWorkbench,
} from './types';

const TERMINAL_BOOK_JOB_STATUSES = new Set<BookJobStatus>([
  'succeeded',
  'partially_succeeded',
  'failed',
  'cancelled',
]);

const BOOK_JOB_STATUSES = new Set<BookJobStatus>([
  'queued',
  'running',
  ...TERMINAL_BOOK_JOB_STATUSES,
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isActivityEvent(value: unknown, jobId: string): value is BookActivityEvent {
  if (!isRecord(value) || !isRecord(value.metadata)) return false;
  return Number.isInteger(value.seq)
    && Number(value.seq) >= 1
    && value.job_id === jobId
    && (value.item_id === null || typeof value.item_id === 'string')
    && typeof value.kind === 'string'
    && typeof value.status === 'string'
    && typeof value.message === 'string'
    && value.message.length <= 512
    && typeof value.created_at === 'string';
}

function parseBookActivityPage(value: unknown, jobId: string): BookActivityPage {
  if (!isRecord(value)
    || value.job_id !== jobId
    || typeof value.status !== 'string'
    || !BOOK_JOB_STATUSES.has(value.status as BookJobStatus)
    || !Array.isArray(value.events)
    || !Number.isInteger(value.high_water_seq)
    || Number(value.high_water_seq) < 0
    || (value.activity_status !== 'available' && value.activity_status !== 'unavailable')
    || typeof value.cursor_expired !== 'boolean'
    || typeof value.has_more !== 'boolean') {
    throw new Error('Invalid textbook activity page');
  }
  if (!value.events.every((entry) => isActivityEvent(entry, jobId))) {
    throw new Error('Invalid textbook activity event');
  }
  const events = value.events as BookActivityEvent[];
  if (events.some((entry, index) => index > 0 && entry.seq <= events[index - 1].seq)) {
    throw new Error('Textbook activity events are not strictly increasing');
  }
  return value as unknown as BookActivityPage;
}

function abortableDelay(milliseconds: number, signal?: AbortSignal): Promise<void> {
  if (milliseconds <= 0 || signal?.aborted) return Promise.resolve();
  return new Promise((resolve) => {
    const timeout = window.setTimeout(done, milliseconds);
    function done() {
      window.clearTimeout(timeout);
      signal?.removeEventListener('abort', done);
      resolve();
    }
    signal?.addEventListener('abort', done, { once: true });
  });
}

function isAbortError(error: unknown, signal?: AbortSignal) {
  return signal?.aborted
    || (error instanceof DOMException && error.name === 'AbortError');
}

class TerminalBookActivityStreamError extends Error {}

interface ConsumeBookActivityStreamOptions {
  jobId: string;
  body: ReadableStream<Uint8Array>;
  signal?: AbortSignal;
  lastProcessedSeq: number;
  seenSequences: Set<number>;
  onPage: (page: BookActivityPage) => void | Promise<void>;
  onCursorExpired?: () => void | Promise<void>;
}

async function consumeBookActivityStream(options: ConsumeBookActivityStreamOptions) {
  const reader = options.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let lastProcessedSeq = options.lastProcessedSeq;
  let cursorExpired = false;
  let terminal = false;
  const cancelReader = () => { void reader.cancel(); };
  options.signal?.addEventListener('abort', cancelReader, { once: true });

  async function consumeFrame(frame: string) {
    const lines = frame.split(/\r?\n/);
    const eventName = lines.find((line) => line.startsWith('event:'))?.slice(6).trim();
    if (eventName && eventName !== 'snapshot') return;
    const data = lines
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).trimStart())
      .join('\n');
    if (!data) return;
    const page = parseBookActivityPage(JSON.parse(data), options.jobId);
    if (page.cursor_expired) {
      await options.onCursorExpired?.();
      options.seenSequences.clear();
      lastProcessedSeq = 0;
      cursorExpired = true;
      return;
    }
    const freshEvents = page.events.filter(
      (entry) => entry.seq > lastProcessedSeq && !options.seenSequences.has(entry.seq),
    );
    const mergedPage = { ...page, events: freshEvents };
    await options.onPage(mergedPage);
    for (const entry of freshEvents) options.seenSequences.add(entry.seq);
    if (freshEvents.length > 0) {
      lastProcessedSeq = Math.max(...freshEvents.map((entry) => entry.seq));
    }
    terminal = TERMINAL_BOOK_JOB_STATUSES.has(page.status);
  }

  try {
    while (!options.signal?.aborted && !cursorExpired && !terminal) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let boundary = buffer.match(/\r?\n\r?\n/);
      while (boundary && !cursorExpired && !terminal) {
        const index = boundary.index ?? 0;
        const frame = buffer.slice(0, index);
        buffer = buffer.slice(index + boundary[0].length);
        await consumeFrame(frame);
        boundary = buffer.match(/\r?\n\r?\n/);
      }
    }
  } finally {
    options.signal?.removeEventListener('abort', cancelReader);
    if (options.signal?.aborted) await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
  return { cursorExpired, lastProcessedSeq, terminal };
}

export type BookActivityConnectionState = 'connecting' | 'connected' | 'reconnecting';

export interface WatchBookActivityOptions {
  afterSeq?: number;
  signal?: AbortSignal;
  reconnectDelayMs?: number;
  onPage: (page: BookActivityPage) => void | Promise<void>;
  onCursorExpired?: () => void | Promise<void>;
  onConnectionChange?: (state: BookActivityConnectionState) => void;
  onError?: (error: unknown) => void;
}

export async function getBookJob(jobId: string): Promise<BookJob> {
  const { data } = await api.get<BookJob>(
    `/api/v1/education/book-jobs/${encodeURIComponent(jobId)}`,
  );
  return data;
}

export async function listManagedTextbooks(): Promise<ManagedTextbookSummary[]> {
  const { data } = await api.get<ManagedTextbookSummary[]>('/api/v1/education/textbooks');
  return data;
}

export async function listManagedBookSources(): Promise<BookSourceCandidate[]> {
  const { data } = await api.get<{ items: BookSourceCandidate[] }>(
    '/api/v1/education/textbook-sources',
  );
  return data.items;
}

export async function createManagedTextbook(
  input: CreateManagedTextbookInput,
): Promise<CreateManagedTextbookResponse> {
  const { data } = await api.post<CreateManagedTextbookResponse>(
    '/api/v1/education/textbooks',
    input,
  );
  return data;
}

export async function getTextbookWorkbench(textbookId: string): Promise<TextbookWorkbench> {
  const { data } = await api.get<TextbookWorkbench>(
    `/api/v1/education/textbooks/${encodeURIComponent(textbookId)}`,
  );
  return data;
}

export async function getManagedBookStructure(textbookId: string): Promise<BookStructure> {
  const { data } = await api.get<BookStructure>(
    `/api/v1/education/textbooks/${encodeURIComponent(textbookId)}/structure`,
  );
  return data;
}

export async function getManagedBookSourceSlice(
  textbookId: string,
  startLine: number,
  endLine: number,
): Promise<BookSourceSlice> {
  const { data } = await api.get<BookSourceSlice>(
    `/api/v1/education/textbooks/${encodeURIComponent(textbookId)}/source`,
    { params: { start_line: startLine, end_line: endLine } },
  );
  return data;
}

export async function getManagedKnowledgePointMaterial(
  textbookId: string,
  knowledgePointId: string,
): Promise<KnowledgePointMaterial> {
  const { data } = await api.get<KnowledgePointMaterial>(
    `/api/v1/education/textbooks/${encodeURIComponent(textbookId)}/knowledge-points/${encodeURIComponent(knowledgePointId)}/material`,
  );
  return data;
}

export async function listManagedBookAssignments(
  textbookId: string,
): Promise<BookAssignment[]> {
  const { data } = await api.get<BookAssignment[]>(
    `/api/v1/education/textbooks/${encodeURIComponent(textbookId)}/assignments`,
  );
  return data;
}

export async function assignManagedBookStudents(
  textbookId: string,
  input: BookAssignmentRequest,
): Promise<BookAssignment[]> {
  const { data } = await api.post<BookAssignment[]>(
    `/api/v1/education/textbooks/${encodeURIComponent(textbookId)}/assignments`,
    input,
  );
  return data;
}

export async function revokeManagedBookStudents(
  textbookId: string,
  input: BookAssignmentRequest,
): Promise<void> {
  await api.delete(
    `/api/v1/education/textbooks/${encodeURIComponent(textbookId)}/assignments`,
    { data: input },
  );
}

export async function createManagedBookJob(
  textbookId: string,
  input: CreateBookJobInput,
): Promise<BookJob> {
  const { data } = await api.post<BookJob>(
    `/api/v1/education/textbooks/${encodeURIComponent(textbookId)}/jobs`,
    input,
  );
  return data;
}

export async function cancelManagedBookJob(jobId: string): Promise<BookJob> {
  const { data } = await api.post<BookJob>(
    `/api/v1/education/book-jobs/${encodeURIComponent(jobId)}/cancel`,
  );
  return data;
}

export async function retryManagedBookJob(jobId: string): Promise<BookJob> {
  const { data } = await api.post<BookJob>(
    `/api/v1/education/book-jobs/${encodeURIComponent(jobId)}/retry`,
  );
  return data;
}

export async function watchBookActivity(
  jobId: string,
  options: WatchBookActivityOptions,
): Promise<void> {
  let lastProcessedSeq = options.afterSeq ?? 0;
  const seenSequences = new Set<number>();
  let connecting: BookActivityConnectionState = 'connecting';
  const reconnectDelayMs = options.reconnectDelayMs ?? 1_000;

  while (!options.signal?.aborted) {
    options.onConnectionChange?.(connecting);
    try {
      const params = new URLSearchParams({ after_seq: String(lastProcessedSeq) });
      const response = await fetch(
        `${api.defaults.baseURL ?? ''}/api/v1/education/book-jobs/${encodeURIComponent(jobId)}/events?${params}`,
        {
          headers: { Accept: 'text/event-stream' },
          credentials: 'include',
          signal: options.signal,
        },
      );
      if (response.status === 403 || response.status === 404) {
        throw new TerminalBookActivityStreamError('Textbook activity is no longer available');
      }
      if (!response.ok
        || !response.body
        || !response.headers.get('Content-Type')?.includes('text/event-stream')) {
        throw new Error('Textbook activity stream is unavailable');
      }
      options.onConnectionChange?.('connected');
      const consumed = await consumeBookActivityStream({
        jobId,
        body: response.body,
        signal: options.signal,
        lastProcessedSeq,
        seenSequences,
        onPage: options.onPage,
        onCursorExpired: options.onCursorExpired,
      });
      lastProcessedSeq = consumed.lastProcessedSeq;
      if (consumed.terminal || options.signal?.aborted) return;
      connecting = 'reconnecting';
    } catch (error) {
      if (isAbortError(error, options.signal)) return;
      options.onError?.(error);
      if (error instanceof TerminalBookActivityStreamError) return;
      connecting = 'reconnecting';
      options.onConnectionChange?.('reconnecting');
    }
    await abortableDelay(reconnectDelayMs, options.signal);
  }
}

export async function listEducationTasks(): Promise<EducationTask[]> {
  const { data } = await api.get<EducationTask[]>('/api/v1/education/tasks');
  return data;
}

export async function getEducationTaskDetail(taskId: string): Promise<EducationTaskDetail> {
  const { data } = await api.get<EducationTaskDetail>(`/api/v1/education/tasks/${taskId}`);
  return data;
}

export async function getEducationTaskCalendar(params: EducationTaskCalendarRequest): Promise<EducationTaskCalendar> {
  const { data } = await api.get<EducationTaskCalendar>('/api/v1/education/tasks/calendar', { params });
  return data;
}

export async function getEducationHomeworkDictionaries(): Promise<EducationHomeworkDictionaries> {
  const { data } = await api.get<EducationHomeworkDictionaries>('/api/v1/education/dictionaries');
  return data;
}

export async function listEducationMembers(): Promise<EducationMember[]> {
  const { data } = await api.get<EducationMember[]>('/api/v1/auth/members');
  return data;
}

export async function ensureStudentFlashWorkspace(): Promise<{ workspace_id: string }> {
  const { data } = await api.post<{ workspace_id: string }>('/api/v1/workspaces/flash');
  return data;
}

export async function createEducationTask(input: CreateEducationTaskInput): Promise<EducationTask> {
  const { data } = await api.post<EducationTask>('/api/v1/education/tasks', input);
  return data;
}

export async function checkInEducationTask(taskId: string, input: SubmitEducationTaskInput): Promise<EducationTaskSubmission> {
  const { data } = await api.post<EducationTaskSubmission>(`/api/v1/education/tasks/${taskId}/check-in`, input);
  return data;
}

export async function appendEducationTaskRevision(taskId: string, input: SubmitEducationTaskInput): Promise<EducationTaskSubmission> {
  const { data } = await api.post<EducationTaskSubmission>(`/api/v1/education/tasks/${taskId}/revisions`, input);
  return data;
}

export async function reviewEducationTask(taskId: string, decision: 'feedback' | 'revision_requested', feedbackText: string): Promise<EducationTaskReview> {
  const { data } = await api.post<EducationTaskReview>(`/api/v1/education/tasks/${taskId}/reviews`, {
    decision,
    feedback_text: feedbackText,
  });
  return data;
}

export async function cancelEducationTask(taskId: string): Promise<EducationTask> {
  const { data } = await api.post<EducationTask>(`/api/v1/education/tasks/${taskId}/cancel`);
  return data;
}

export async function uploadEducationAsset(file: File, options?: { stagingKey?: string; stagingSlot?: number }): Promise<EducationAsset> {
  const body = new FormData();
  body.append('file', file);
  const params = options?.stagingKey && options.stagingSlot !== undefined ? { staging_key: options.stagingKey, staging_slot: options.stagingSlot } : undefined;
  const { data } = await api.post<EducationAsset>('/api/v1/education/assets', body, {
    headers: { 'Content-Type': 'multipart/form-data' },
    params,
  });
  return data;
}

export async function deleteEducationAsset(assetId: string): Promise<void> {
  await api.delete(`/api/v1/education/assets/${assetId}`);
}

export async function listEducationAssets(): Promise<EducationAsset[]> {
  const { data } = await api.get<EducationAsset[]>('/api/v1/education/assets');
  return data;
}

export async function getEducationAssetDownloadUrl(assetId: string): Promise<string> {
  const { data } = await api.get<{ url: string }>(`/api/v1/education/assets/${assetId}/download`);
  return data.url;
}

export async function listLearningAssignments(): Promise<LearningAssignment[]> {
  const { data } = await api.get<LearningAssignment[]>('/api/v1/education/learning');
  return data;
}

export async function getStudentTextbookStructure(assignmentId: string): Promise<StudentTextbookStructure> {
  const { data } = await api.get<StudentTextbookStructure>(`/api/v1/education/learning/${assignmentId}/structure`);
  return data;
}

export async function getStudentKnowledgePointLesson(assignmentId: string, knowledgePointId: string): Promise<StudentKnowledgePointLesson> {
  const { data } = await api.get<StudentKnowledgePointLesson>(`/api/v1/education/learning/${assignmentId}/knowledge-points/${knowledgePointId}`);
  return data;
}

export async function listStudentLearningItems(
  assignmentId: string,
  filters: { unitId?: string; knowledgePointId?: string } = {},
): Promise<LearningItem[]> {
  const { data } = await api.get<LearningItem[]>(`/api/v1/education/learning/${assignmentId}/items`, {
    params: {
      unit_id: filters.unitId,
      knowledge_point_id: filters.knowledgePointId,
    },
  });
  return data;
}

export async function createStudentLearningItem(
  assignmentId: string,
  knowledgePointId: string,
  input: {
    unitId?: string;
    kind: Exclude<LearningItemKind, 'summary'>;
    content: string;
    sourceAnchor?: Record<string, unknown> | null;
  },
): Promise<LearningItem> {
  const { data } = await api.post<LearningItem>(`/api/v1/education/learning/${assignmentId}/knowledge-points/${knowledgePointId}/items`, {
    unit_id: input.unitId,
    kind: input.kind,
    content: input.content,
    source_anchor: input.sourceAnchor,
  });
  return data;
}

export async function updateStudentLearningItem(
  assignmentId: string,
  itemId: string,
  input: { content: string; sourceAnchor?: Record<string, unknown> | null },
): Promise<LearningItem> {
  const { data } = await api.patch<LearningItem>(`/api/v1/education/learning/${assignmentId}/items/${itemId}`, {
    content: input.content,
    source_anchor: input.sourceAnchor,
  });
  return data;
}

export async function deleteStudentLearningItem(assignmentId: string, itemId: string): Promise<void> {
  await api.delete(`/api/v1/education/learning/${assignmentId}/items/${itemId}`);
}

export async function generateStudentUnitSummary(assignmentId: string, unitId: string): Promise<LearningItem> {
  const { data } = await api.post<LearningItem>(`/api/v1/education/learning/${assignmentId}/units/${unitId}/summaries`);
  return data;
}

export async function updateStudentKpProgress(assignmentId: string, knowledgePointId: string, status: 'learning' | 'read' | 'review_recommended'): Promise<void> {
  await api.post(`/api/v1/education/learning/${assignmentId}/knowledge-points/${knowledgePointId}/progress`, { status });
}

export async function getLearningChatSpace(assignmentId: string): Promise<LearningChatSpace> {
  const { data } = await api.get<LearningChatSpace>(`/api/v1/education/learning/${assignmentId}/chat-space`);
  return data;
}

export async function getParentLearningTranscript(assignmentId: string): Promise<ParentLearningTranscript> {
  const { data } = await api.get<ParentLearningTranscript>(`/api/v1/education/learning/${assignmentId}/chat-transcript`);
  return data;
}
