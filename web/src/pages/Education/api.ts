import { api } from '@/api/client';
import type { BookPipelineJob, BookPipelineProgress, CompletedParseJob, CreateBookPipelineJobInput, CreateEducationTaskInput, EducationAsset, EducationHomeworkDictionaries, EducationMember, EducationTask, EducationTaskCalendar, EducationTaskCalendarRequest, EducationTaskDetail, EducationTaskReview, EducationTaskSubmission, KnowledgePointCandidate, KnowledgePointCandidateReview, KnowledgePointLesson, KnowledgePointSourcePreview, LearningAssignment, LearningChatSpace, LearningItem, LearningItemKind, LessonGenerationStatus, MergeKnowledgePointCandidatesInput, ParentLearningTranscript, SplitKnowledgePointCandidateInput, StructureGenerationJob, StructureGenerationProgress, StudentKnowledgePointLesson, StudentTextbookStructure, SubmitEducationTaskInput, TextbookAssignment, TextbookDetail, TextbookLibraryItem, TextbookProcessingJob, TextbookStructure, TextbookStructureUnit, UpdateKnowledgePointCandidateInput } from './types';
import type { BookActivityEvent, BookActivityPage, BookJob, BookJobStatus } from './types';

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

export async function listTextbooks(): Promise<TextbookLibraryItem[]> {
  const { data } = await api.get<TextbookLibraryItem[]>('/api/v1/education/textbooks');
  return data;
}

export async function getTextbook(textbookId: string): Promise<TextbookDetail> {
  const { data } = await api.get<TextbookDetail>(`/api/v1/education/textbooks/${textbookId}`);
  return data;
}

export async function getLatestTextbookStructure(versionId: string): Promise<TextbookStructure | null> {
  const { data } = await api.get<TextbookStructure | null>(`/api/v1/education/textbook-versions/${versionId}/structure`);
  return data;
}

export async function getKnowledgePointCandidateReview(
  structureId: string,
): Promise<KnowledgePointCandidateReview> {
  const { data } = await api.get<KnowledgePointCandidateReview>(
    `/api/v1/education/structures/${structureId}/candidates`,
  );
  return data;
}

export async function updateKnowledgePointCandidate(
  candidateId: string,
  input: UpdateKnowledgePointCandidateInput,
): Promise<KnowledgePointCandidate> {
  const { data } = await api.patch<KnowledgePointCandidate>(
    `/api/v1/education/candidates/${candidateId}`,
    input,
  );
  return data;
}

export async function acceptKnowledgePointCandidates(
  candidateIds: string[],
): Promise<KnowledgePointCandidate[]> {
  const { data } = await api.post<KnowledgePointCandidate[]>(
    '/api/v1/education/candidates/accept',
    { candidate_ids: candidateIds },
  );
  return data;
}

export async function rejectKnowledgePointCandidates(
  candidateIds: string[],
): Promise<KnowledgePointCandidate[]> {
  const { data } = await api.post<KnowledgePointCandidate[]>(
    '/api/v1/education/candidates/reject',
    { candidate_ids: candidateIds },
  );
  return data;
}

export async function mergeKnowledgePointCandidates(
  input: MergeKnowledgePointCandidatesInput,
): Promise<KnowledgePointCandidate[]> {
  const { data } = await api.post<KnowledgePointCandidate[]>(
    '/api/v1/education/candidates/merge',
    input,
  );
  return data;
}

export async function splitKnowledgePointCandidate(
  input: SplitKnowledgePointCandidateInput,
): Promise<KnowledgePointCandidate[]> {
  const { data } = await api.post<KnowledgePointCandidate[]>(
    '/api/v1/education/candidates/split',
    input,
  );
  return data;
}

export async function createBookPipelineJob(
  versionId: string,
  input: CreateBookPipelineJobInput,
): Promise<BookPipelineJob> {
  const { data } = await api.post<BookPipelineJob>(
    `/api/v1/education/textbook-versions/${versionId}/book-pipeline-jobs`,
    input,
  );
  return data;
}

export async function cancelBookPipelineJob(
  jobId: string,
): Promise<BookPipelineJob> {
  const { data } = await api.post<BookPipelineJob>(
    `/api/v1/education/book-pipeline-jobs/${jobId}/cancel`,
  );
  return data;
}

export async function getBookPipelineJobProgress(
  jobId: string,
): Promise<BookPipelineProgress> {
  const { data } = await api.get<BookPipelineProgress>(
    `/api/v1/education/jobs/${jobId}/progress`,
  );
  return data;
}

export async function createTextbookStructure(versionId: string, profile?: Record<string, unknown>): Promise<StructureGenerationJob> {
  const { data } = await api.post<StructureGenerationJob>(`/api/v1/education/textbook-versions/${versionId}/structures`, profile ? { profile } : {});
  return data;
}

export async function getStructureGenerationJob(generationJobId: string): Promise<StructureGenerationJob> {
  const { data } = await api.get<StructureGenerationJob>(`/api/v1/education/structure-generation-jobs/${generationJobId}`);
  return data;
}

export async function getStructureGenerationProgress(generationJobId: string): Promise<StructureGenerationProgress> {
  const { data } = await api.get<StructureGenerationProgress>(`/api/v1/education/structure-generation-jobs/${generationJobId}/progress`);
  return data;
}

export async function resumeStructureGenerationJob(generationJobId: string): Promise<StructureGenerationJob> {
  const { data } = await api.post<StructureGenerationJob>(`/api/v1/education/structure-generation-jobs/${generationJobId}/resume`);
  return data;
}

export async function generateBookAssets(structureId: string): Promise<StructureGenerationJob> {
  const { data } = await api.post<StructureGenerationJob>(`/api/v1/education/textbook-structures/${structureId}/book-assets`);
  return data;
}

export async function updateTextbookStructure(structureId: string, units: TextbookStructureUnit[]): Promise<TextbookStructure> {
  const { data } = await api.put<TextbookStructure>(`/api/v1/education/textbook-structures/${structureId}`, { units });
  return data;
}

export async function acceptTextbookStructure(structureId: string): Promise<TextbookStructure> {
  const { data } = await api.post<TextbookStructure>(`/api/v1/education/textbook-structures/${structureId}/review`);
  return data;
}

export async function generateKnowledgePointLesson(knowledgePointId: string, autoGrading = false, prompt = ''): Promise<StructureGenerationJob> {
  const { data } = await api.post<StructureGenerationJob>(`/api/v1/education/knowledge-points/${knowledgePointId}/lessons`, { auto_grading: autoGrading, prompt });
  return data;
}

export async function getKnowledgePointLesson(lessonId: string): Promise<KnowledgePointLesson> {
  const { data } = await api.get<KnowledgePointLesson>(`/api/v1/education/knowledge-point-lessons/${lessonId}`);
  return data;
}

export async function getKnowledgePointLessonByPoint(knowledgePointId: string): Promise<KnowledgePointLesson | null> {
  const { data } = await api.get<KnowledgePointLesson | null>(`/api/v1/education/knowledge-points/${knowledgePointId}/lesson`);
  return data;
}

export async function getKnowledgePointSourcePreview(knowledgePointId: string): Promise<KnowledgePointSourcePreview> {
  const { data } = await api.get<KnowledgePointSourcePreview>(`/api/v1/education/knowledge-points/${knowledgePointId}/source-preview`);
  return data;
}

export async function getLessonGenerationStatus(knowledgePointId: string): Promise<LessonGenerationStatus> {
  const { data } = await api.get<LessonGenerationStatus>(`/api/v1/education/knowledge-points/${knowledgePointId}/lesson-generation`);
  return data;
}

export async function createKnowledgePointLessonRevision(lessonId: string, contentMarkdown: string): Promise<KnowledgePointLesson> {
  const { data } = await api.post<KnowledgePointLesson>(`/api/v1/education/knowledge-point-lessons/${lessonId}/revisions`, { content_markdown: contentMarkdown });
  return data;
}

export async function approveKnowledgePointLesson(lessonId: string, revisionId: string): Promise<KnowledgePointLesson> {
  const { data } = await api.post<KnowledgePointLesson>(`/api/v1/education/knowledge-point-lessons/${lessonId}/review`, { revision_id: revisionId });
  return data;
}

export async function publishTextbookStructure(versionId: string, structureId: string): Promise<{ publication_id: string; version_id: string; structure_id: string }> {
  const { data } = await api.post<{ publication_id: string; version_id: string; structure_id: string }>(`/api/v1/education/textbook-versions/${versionId}/structure-publications`, { structure_id: structureId });
  return data;
}

export async function createTextbook(input: { title: string }): Promise<TextbookLibraryItem> {
  const { data } = await api.post<TextbookLibraryItem>('/api/v1/education/textbooks', input);
  return data;
}

export async function startTextbookProcessing(textbookId: string, sourceAssetIds: string[]): Promise<TextbookProcessingJob> {
  const { data } = await api.post<TextbookProcessingJob>(`/api/v1/education/textbooks/${textbookId}/processing`, { source_asset_ids: sourceAssetIds });
  return data;
}

export async function listCompletedParseJobs(): Promise<CompletedParseJob[]> {
  const { data } = await api.get<CompletedParseJob[]>('/api/v1/education/textbook-parse-jobs/completed');
  return data;
}

export async function startTextbookProcessingFromParseJobs(textbookId: string, sourceParseJobIds: string[]): Promise<TextbookProcessingJob> {
  const { data } = await api.post<TextbookProcessingJob>(`/api/v1/education/textbooks/${textbookId}/processing`, { source_parse_job_ids: sourceParseJobIds });
  return data;
}

export async function runTextbookProcessing(jobId: string): Promise<TextbookProcessingJob> {
  const { data } = await api.post<TextbookProcessingJob>(`/api/v1/education/textbook-processing/${jobId}/run`);
  return data;
}

export async function retryTextbookProcessing(jobId: string): Promise<TextbookProcessingJob> {
  const { data } = await api.post<TextbookProcessingJob>(`/api/v1/education/textbook-processing/${jobId}/retry`);
  return data;
}

export async function assignTextbookPublication(publicationId: string, studentUserId: string): Promise<TextbookAssignment> {
  const { data } = await api.post<TextbookAssignment>(`/api/v1/education/textbook-publications/${publicationId}/assignments`, { student_user_id: studentUserId });
  return data;
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
