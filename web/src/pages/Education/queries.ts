import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { isAxiosError } from 'axios';
import { queryKeys } from '@/lib/queryKeys';
import * as educationApi from './api';
import type {
  BookActivityConnectionState,
} from './api';
import type {
  BookActivityEvent,
  BookJob,
  BookJobStatus,
  EducationTaskCalendarRequest,
} from './types';

const TERMINAL_MANAGED_BOOK_STATUSES = new Set<BookJobStatus>([
  'succeeded',
  'partially_succeeded',
  'failed',
  'cancelled',
]);

interface RefreshSchedulerOptions {
  minimumIntervalMs?: number;
  now?: () => number;
}

export function createCoalescedRefreshScheduler(
  refresh: () => unknown | Promise<unknown>,
  options: RefreshSchedulerOptions = {},
) {
  const minimumIntervalMs = options.minimumIntervalMs ?? 1_000;
  const now = options.now ?? Date.now;
  let lastStartedAt = Number.NEGATIVE_INFINITY;
  let running = false;
  let pending = false;
  let disposed = false;
  let timer: number | null = null;
  let idleWaiters: Array<() => void> = [];

  const resolveIdle = () => {
    if (running || pending || timer !== null) return;
    const waiters = idleWaiters;
    idleWaiters = [];
    for (const resolve of waiters) resolve();
  };

  const schedule = () => {
    if (disposed || running || !pending) {
      resolveIdle();
      return;
    }
    const remaining = minimumIntervalMs - (now() - lastStartedAt);
    if (remaining > 0) {
      if (timer === null) {
        timer = window.setTimeout(() => {
          timer = null;
          schedule();
        }, remaining);
      }
      return;
    }
    pending = false;
    running = true;
    lastStartedAt = now();
    void Promise.resolve(refresh()).finally(() => {
      running = false;
      schedule();
    });
  };

  return {
    notify() {
      if (disposed) return;
      pending = true;
      schedule();
    },
    flush() {
      if (disposed) return Promise.resolve();
      pending = true;
      lastStartedAt = Number.NEGATIVE_INFINITY;
      if (timer !== null) {
        window.clearTimeout(timer);
        timer = null;
      }
      schedule();
      if (!running && !pending && timer === null) return Promise.resolve();
      return new Promise<void>((resolve) => { idleWaiters.push(resolve); });
    },
    dispose() {
      disposed = true;
      pending = false;
      if (timer !== null) window.clearTimeout(timer);
      timer = null;
      resolveIdle();
    },
  };
}

export function useBookJob(jobId: string | undefined, enabled = true) {
  return useQuery({
    queryKey: queryKeys.education.bookJob(jobId ?? ''),
    queryFn: () => educationApi.getBookJob(jobId ?? ''),
    enabled: Boolean(jobId) && enabled,
    staleTime: 1_000,
  });
}

export function useBookJobStatistics(jobId: string | undefined, enabled = false) {
  return useInfiniteQuery({
    queryKey: queryKeys.education.bookStatistics(jobId ?? ''),
    queryFn: ({ pageParam }) => educationApi.getBookJobStatistics(jobId ?? '', pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    enabled: Boolean(jobId) && enabled,
    maxPages: 5,
    staleTime: 5000,
  });
}

export function useManagedTextbookLibrary() {
  return useQuery({
    queryKey: queryKeys.education.textbooks(),
    queryFn: educationApi.listManagedTextbooks,
    staleTime: 15_000,
  });
}

export function useDeleteManagedTextbook() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: educationApi.deleteManagedTextbook,
    onSuccess: async (_, textbookId) => {
      queryClient.removeQueries({ queryKey: queryKeys.education.textbook(textbookId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.education.all });
      await queryClient.invalidateQueries({ queryKey: queryKeys.documents.all });
    },
  });
}

export function useUploadTextbookCover() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ textbookId, file }: { textbookId: string; file: File }) => educationApi.uploadTextbookCover(textbookId, file),
    onSuccess: async (_, { textbookId }) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.education.textbooks() });
      await queryClient.invalidateQueries({ queryKey: queryKeys.education.textbookWorkbench(textbookId) });
    },
  });
}

export function useDeleteTextbookCover() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: educationApi.deleteTextbookCover,
    onSuccess: async (_, textbookId) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.education.textbooks() });
      await queryClient.invalidateQueries({ queryKey: queryKeys.education.textbookWorkbench(textbookId) });
    },
  });
}

export function useManagedBookSourceCandidates(enabled = true) {
  return useQuery({
    queryKey: queryKeys.education.bookSources(),
    queryFn: educationApi.listManagedBookSources,
    enabled,
    staleTime: 15_000,
  });
}

export function useTextbookWorkbench(textbookId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.education.textbookWorkbench(textbookId ?? ''),
    queryFn: () => educationApi.getTextbookWorkbench(textbookId ?? ''),
    enabled: Boolean(textbookId),
    staleTime: 5_000,
    refetchInterval: (query) => query.state.data?.current_job ? 5_000 : false,
  });
}

export function useManagedBookStructure(textbookId: string | undefined, enabled = true) {
  return useQuery({
    queryKey: queryKeys.education.bookStructure(textbookId ?? ''),
    queryFn: () => educationApi.getManagedBookStructure(textbookId ?? ''),
    enabled: Boolean(textbookId) && enabled,
    staleTime: 30_000,
  });
}

export function useManagedBookSourceSlice(
  textbookId: string | undefined,
  startLine: number | undefined,
  endLine: number | undefined,
  enabled = true,
) {
  return useQuery({
    queryKey: queryKeys.education.bookSourceSlice(
      textbookId ?? '',
      startLine ?? 0,
      endLine ?? 0,
    ),
    queryFn: () => educationApi.getManagedBookSourceSlice(
      textbookId ?? '',
      startLine ?? 0,
      endLine ?? 0,
    ),
    enabled: Boolean(textbookId && startLine && endLine) && enabled,
    staleTime: 30_000,
  });
}

export function useManagedBookOriginal(textbookId: string) {
  return useQuery({
    queryKey: queryKeys.education.bookOriginal(textbookId),
    queryFn: ({ signal }) => educationApi.getManagedBookOriginal(textbookId, signal),
    enabled: Boolean(textbookId),
    staleTime: Infinity,
    retry: false,
  });
}

export function useManagedBookOriginalLocation(textbookId: string, startLine?: number) {
  return useQuery({
    queryKey: queryKeys.education.bookOriginalLocation(textbookId, startLine ?? 0),
    queryFn: ({ signal }) => educationApi.getManagedBookOriginalLocation(textbookId, startLine!, signal),
    enabled: Boolean(textbookId && startLine),
    staleTime: Infinity,
    retry: false,
  });
}

export function useManagedKnowledgePointMaterial(
  textbookId: string | undefined,
  knowledgePointId: string | undefined,
  enabled = true,
) {
  return useQuery({
    queryKey: queryKeys.education.bookMaterial(textbookId ?? '', knowledgePointId ?? ''),
    queryFn: () => educationApi.getManagedKnowledgePointMaterial(
      textbookId ?? '',
      knowledgePointId ?? '',
    ),
    enabled: Boolean(textbookId && knowledgePointId) && enabled,
    staleTime: 10_000,
  });
}

export function useManagedBookAssignments(
  textbookId: string | undefined,
  enabled = true,
) {
  return useQuery({
    queryKey: queryKeys.education.bookAssignments(textbookId ?? ''),
    queryFn: () => educationApi.listManagedBookAssignments(textbookId ?? ''),
    enabled: Boolean(textbookId) && enabled,
    staleTime: 10_000,
  });
}

export function useManagedBookAssignmentMutations() {
  const queryClient = useQueryClient();
  const invalidate = (textbookId: string) => Promise.all([
    queryClient.invalidateQueries({
      queryKey: queryKeys.education.bookAssignments(textbookId),
    }),
    queryClient.invalidateQueries({
      queryKey: queryKeys.education.textbookWorkbench(textbookId),
    }),
  ]);
  return {
    assign: useMutation({
      mutationFn: ({ textbookId, studentUserIds }: {
        textbookId: string;
        studentUserIds: string[];
      }) => educationApi.assignManagedBookStudents(textbookId, {
        student_user_ids: studentUserIds,
      }),
      onSuccess: (_assignments, variables) => invalidate(variables.textbookId),
    }),
    revoke: useMutation({
      mutationFn: ({ textbookId, studentUserIds }: {
        textbookId: string;
        studentUserIds: string[];
      }) => educationApi.revokeManagedBookStudents(textbookId, {
        student_user_ids: studentUserIds,
      }),
      onSuccess: (_result, variables) => invalidate(variables.textbookId),
    }),
  };
}

export function useManagedBookMutations() {
  const queryClient = useQueryClient();
  const invalidateBook = (textbookId: string) => Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.education.textbookWorkbench(textbookId) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.education.bookStructure(textbookId) }),
  ]);
  return {
    createTextbook: useMutation({
      mutationFn: educationApi.createManagedTextbook,
      onSuccess: () => queryClient.invalidateQueries({
        queryKey: queryKeys.education.textbooks(),
      }),
    }),
    createJob: useMutation({
      mutationFn: ({ textbookId, input }: {
        textbookId: string;
        input: Parameters<typeof educationApi.createManagedBookJob>[1];
      }) => educationApi.createManagedBookJob(textbookId, input),
      onSuccess: (_job, variables) => invalidateBook(variables.textbookId),
    }),
    cancelJob: useMutation({
      mutationFn: educationApi.cancelManagedBookJob,
      onSuccess: (job) => invalidateBook(job.textbook_id),
    }),
    retryJob: useMutation({
      mutationFn: educationApi.retryManagedBookJob,
      onSuccess: (job) => invalidateBook(job.textbook_id),
    }),
  };
}

function usePageVisibility() {
  const [visible, setVisible] = useState(
    () => typeof document === 'undefined' || document.visibilityState === 'visible',
  );
  useEffect(() => {
    const update = () => setVisible(document.visibilityState === 'visible');
    document.addEventListener('visibilitychange', update);
    return () => document.removeEventListener('visibilitychange', update);
  }, []);
  return visible;
}

function mergeBoundedActivity(
  previous: readonly BookActivityEvent[],
  incoming: readonly BookActivityEvent[],
) {
  if (incoming.length === 0) return [...previous];
  const bySequence = new Map(previous.map((entry) => [entry.seq, entry]));
  for (const entry of incoming) {
    if (entry.kind === 'summary' && entry.status === 'truncated') {
      const newer = [...bySequence.values()].some((saved) => saved.job_id === entry.job_id
        && saved.kind === 'summary' && saved.status === 'truncated' && saved.seq > entry.seq);
      if (newer) continue;
      for (const [seq, saved] of bySequence) {
        if (saved.job_id === entry.job_id && saved.kind === 'summary' && saved.status === 'truncated') bySequence.delete(seq);
      }
    }
    bySequence.set(entry.seq, entry);
  }
  const ordered = [...bySequence.values()].sort((left, right) => left.seq - right.seq);
  const business = ordered.filter((entry) => entry.kind !== 'tool').slice(-1_000);
  const remaining = 1_000 - business.length;
  const tools = remaining > 0 ? ordered.filter((entry) => entry.kind === 'tool').slice(-remaining) : [];
  return [...business, ...tools].sort((left, right) => left.seq - right.seq);
}

export function useBookActivity(
  jobId: string | undefined,
  textbookId: string | undefined,
  enabled = true,
  streamEnabled = true,
) {
  const queryClient = useQueryClient();
  const job = useBookJob(jobId, enabled);
  const [events, setEvents] = useState<BookActivityEvent[]>([]);
  const eventsRef = useRef<BookActivityEvent[]>([]);
  const lastProcessedSeqRef = useRef(0);
  const [connectionState, setConnectionState] = useState<BookActivityConnectionState>('connecting');
  const [liveAfterSeq, setLiveAfterSeq] = useState<number | null>(null);
  const [streamTerminal, setStreamTerminal] = useState(false);
  const [streamError, setStreamError] = useState<unknown>(null);
  const [streamAccessLost, setStreamAccessLost] = useState(false);
  const accessLost = streamAccessLost || (
    isAxiosError(job.error) && [401, 403, 404].includes(job.error.response?.status ?? 0)
  );
  const visible = usePageVisibility();
  const terminal = TERMINAL_MANAGED_BOOK_STATUSES.has(job.data?.status ?? 'queued');
  const snapshotJobId = job.data?.job_id;
  const belongsToTextbook = Boolean(job.data && job.data.job_id === jobId && job.data.textbook_id === textbookId);

  useEffect(() => {
    if (!enabled || !textbookId || !snapshotJobId || !belongsToTextbook) return;
    void queryClient.invalidateQueries({
      queryKey: queryKeys.education.textbook(textbookId),
    });
  }, [enabled, textbookId, queryClient, snapshotJobId, belongsToTextbook, job.data?.status, job.data?.succeeded_items]);

  // Only durable boundaries refresh history; resource counts and live durations do not.
  const statisticsRevision = JSON.stringify([
    job.data?.request_round, job.data?.status, job.data?.succeeded_items, job.data?.finished_at,
    job.data?.items.map((item) => [
      item.item_id, item.attempt, item.status, item.execution_phase, item.finished_at,
      item.timing_summary?.status, item.timing_summary?.terminal_at,
      item.timing_summary?.phases.map((phase) => [
        phase.phase, phase.status, phase.segment_count, phase.started_at, phase.ended_at,
      ]),
    ]),
  ]);
  useEffect(() => {
    if (!enabled || !snapshotJobId || !belongsToTextbook || accessLost) return;
    void queryClient.invalidateQueries({ queryKey: queryKeys.education.bookStatistics(snapshotJobId) });
  }, [enabled, snapshotJobId, belongsToTextbook, queryClient, accessLost, statisticsRevision]);

  useEffect(() => {
    eventsRef.current = [];
    lastProcessedSeqRef.current = 0;
    setEvents([]);
    setStreamError(null);
    setStreamAccessLost(false);
    setConnectionState('connecting');
    setLiveAfterSeq(null);
    setStreamTerminal(false);
  }, [jobId, textbookId, enabled]);

  useEffect(() => {
    if (!enabled || !jobId || !visible || !belongsToTextbook || accessLost || (terminal && !streamEnabled)) return;
    const abortController = new AbortController();
    let disposed = false;
    let replayBoundary: number | null = null;
    setLiveAfterSeq(null);
    const jobKey = queryKeys.education.bookJob(jobId);
    const refreshJob = () => queryClient.fetchQuery({
      queryKey: jobKey,
      queryFn: () => educationApi.getBookJob(jobId),
      staleTime: 0,
    });
    const scheduler = createCoalescedRefreshScheduler(refreshJob);
    const invalidateWorkbench = () => textbookId
      ? queryClient.invalidateQueries({
        queryKey: queryKeys.education.textbookWorkbench(textbookId),
      })
      : Promise.resolve();

    if (!terminal) scheduler.notify();
    const fallbackTimer = terminal ? undefined : window.setInterval(() => scheduler.notify(), 5_000);
    if (!streamEnabled) {
      return () => {
        disposed = true;
        window.clearInterval(fallbackTimer);
        scheduler.dispose();
      };
    }
    const afterSeq = lastProcessedSeqRef.current;
    void educationApi.watchBookActivity(jobId, {
      afterSeq,
      signal: abortController.signal,
      onConnectionChange: (state) => {
        if (disposed) return;
        setConnectionState(state);
        if (state !== 'connected') {
          replayBoundary = null;
          setLiveAfterSeq(null);
        }
        if (state === 'connected') scheduler.notify();
      },
      onError: (error) => {
        if (!disposed) setStreamError(error);
      },
      onAccessLost: () => {
        if (disposed) return;
        eventsRef.current = [];
        lastProcessedSeqRef.current = 0;
        setEvents([]);
        setLiveAfterSeq(null);
        setStreamError(new Error('教材活动已不可访问'));
        setStreamAccessLost(true);
        disposed = true;
        abortController.abort();
        window.clearInterval(fallbackTimer);
        scheduler.dispose();
      },
      onPage: async (page) => {
        if (disposed) return;
        setStreamError(null);
        if (TERMINAL_MANAGED_BOOK_STATUSES.has(page.status)) setStreamTerminal(true);
        if (replayBoundary === null) {
          replayBoundary = page.high_water_seq;
          setLiveAfterSeq(replayBoundary);
        }
        if (page.events.length > 0) {
          const merged = mergeBoundedActivity(eventsRef.current, page.events);
          eventsRef.current = merged;
          lastProcessedSeqRef.current = Math.max(lastProcessedSeqRef.current, ...page.events.map((entry) => entry.seq));
          setEvents(merged);
        }
        queryClient.setQueryData<BookJob>(jobKey, (current) => current
          ? { ...current, activity_status: page.activity_status }
          : current);
        const hasBusinessEvent = page.events.some(
          (entry) => entry.kind !== 'tool' && entry.kind !== 'progress',
        );
        if (hasBusinessEvent) scheduler.notify();
        if (TERMINAL_MANAGED_BOOK_STATUSES.has(page.status)) {
          await scheduler.flush();
          if (!disposed) await invalidateWorkbench();
        }
      },
      onCursorExpired: async () => {
        if (disposed) return;
        eventsRef.current = [];
        lastProcessedSeqRef.current = 0;
        setEvents([]);
        replayBoundary = null;
        setLiveAfterSeq(null);
        await scheduler.flush();
        if (!disposed) await invalidateWorkbench();
      },
    }).catch((error) => {
      if (!disposed && !abortController.signal.aborted) setStreamError(error);
    });

    return () => {
      disposed = true;
      abortController.abort();
      window.clearInterval(fallbackTimer);
      scheduler.dispose();
    };
  }, [enabled, jobId, queryClient, terminal, textbookId, visible, streamEnabled, belongsToTextbook, accessLost]);

  return {
    ...job,
    events: belongsToTextbook ? events : [],
    connectionState: accessLost ? 'access_lost' as const : connectionState,
    accessLost,
    liveAfterSeq,
    streamTerminal,
    streamError,
  };
}

export function useEducationTasks() {
  return useQuery({
    queryKey: queryKeys.education.tasks(),
    queryFn: educationApi.listEducationTasks,
    staleTime: 15_000,
  });
}

export function useEducationTaskDetail(taskId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.education.task(taskId ?? ''),
    queryFn: () => educationApi.getEducationTaskDetail(taskId ?? ''),
    enabled: Boolean(taskId),
    staleTime: 10_000,
  });
}

export function useEducationTaskCalendar(params: EducationTaskCalendarRequest | undefined) {
  return useQuery({
    queryKey: queryKeys.education.calendar(params ?? {}),
    queryFn: () => educationApi.getEducationTaskCalendar(params as EducationTaskCalendarRequest),
    enabled: Boolean(params),
    staleTime: 15_000,
  });
}

export function useEducationHomeworkDictionaries() {
  return useQuery({
    queryKey: queryKeys.education.dictionaries(),
    queryFn: educationApi.getEducationHomeworkDictionaries,
    staleTime: Infinity,
  });
}

export function useEducationAssets() {
  return useQuery({
    queryKey: queryKeys.education.assets(),
    queryFn: educationApi.listEducationAssets,
    staleTime: 15_000,
  });
}

export function useEducationMembers(enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.education.members(),
    queryFn: educationApi.listEducationMembers,
    enabled,
    staleTime: 30_000,
  });
}

export function useEducationTaskMutations() {
  const queryClient = useQueryClient();
  const invalidate = () => queryClient.invalidateQueries({ queryKey: queryKeys.education.all });
  return {
    create: useMutation({ mutationFn: educationApi.createEducationTask, onSuccess: invalidate }),
    checkIn: useMutation({ mutationFn: ({ taskId, ...input }: { taskId: string } & Parameters<typeof educationApi.checkInEducationTask>[1]) => educationApi.checkInEducationTask(taskId, input), onSuccess: invalidate }),
    appendRevision: useMutation({ mutationFn: ({ taskId, ...input }: { taskId: string } & Parameters<typeof educationApi.appendEducationTaskRevision>[1]) => educationApi.appendEducationTaskRevision(taskId, input), onSuccess: invalidate }),
    review: useMutation({ mutationFn: ({ taskId, decision, feedbackText }: { taskId: string; decision: 'feedback' | 'revision_requested'; feedbackText: string }) => educationApi.reviewEducationTask(taskId, decision, feedbackText), onSuccess: invalidate }),
    cancel: useMutation({ mutationFn: educationApi.cancelEducationTask, onSuccess: invalidate }),
  };
}

export function useLearningAssignments(enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.education.learning(),
    queryFn: educationApi.listLearningAssignments,
    enabled,
    staleTime: 15_000,
  });
}

export function useStudentTextbookStructure(assignmentId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.education.assignmentStructure(assignmentId ?? ''),
    queryFn: () => educationApi.getStudentTextbookStructure(assignmentId ?? ''),
    enabled: Boolean(assignmentId),
    staleTime: 15_000,
  });
}

export function useStudentKnowledgePointMaterial(
  assignmentId: string | undefined,
  knowledgePointId: string | undefined,
) {
  return useQuery({
    queryKey: queryKeys.education.assignmentKnowledgePoint(assignmentId ?? '', knowledgePointId ?? ''),
    queryFn: () => educationApi.getStudentKnowledgePointMaterial(assignmentId ?? '', knowledgePointId ?? ''),
    enabled: Boolean(assignmentId && knowledgePointId),
    staleTime: 30_000,
  });
}

export function useStudentLearningItems(
  assignmentId: string | undefined,
  filters: { skillNodeId?: string; knowledgePointId?: string } = {},
  enabled = true,
) {
  return useQuery({
    queryKey: queryKeys.education.assignmentLearningItems(assignmentId ?? '', filters),
    queryFn: () => educationApi.listStudentLearningItems(assignmentId ?? '', filters),
    enabled: Boolean(assignmentId) && enabled,
    staleTime: 5_000,
  });
}

export function useLearningAssetMutations() {
  const queryClient = useQueryClient();
  const invalidate = () => queryClient.invalidateQueries({ queryKey: queryKeys.education.all });
  return {
    add: useMutation({
      mutationFn: ({
        assignmentId,
        knowledgePointId,
        ...input
      }: {
        assignmentId: string;
        knowledgePointId: string;
        skillNodeId?: string;
        kind: 'question' | 'highlight' | 'note';
        content: string;
        sourceAnchor?: Record<string, unknown> | null;
      }) => educationApi.createStudentLearningItem(assignmentId, knowledgePointId, input),
      onSuccess: invalidate,
    }),
    update: useMutation({
      mutationFn: ({ assignmentId, itemId, content, sourceAnchor }: { assignmentId: string; itemId: string; content: string; sourceAnchor?: Record<string, unknown> | null }) =>
        educationApi.updateStudentLearningItem(assignmentId, itemId, { content, sourceAnchor }),
      onSuccess: invalidate,
    }),
    remove: useMutation({
      mutationFn: ({ assignmentId, itemId }: { assignmentId: string; itemId: string }) =>
        educationApi.deleteStudentLearningItem(assignmentId, itemId),
      onSuccess: invalidate,
    }),
    summarize: useMutation({
      mutationFn: ({ assignmentId, skillNodeId }: { assignmentId: string; skillNodeId: string }) =>
        educationApi.generateStudentNodeSummary(assignmentId, skillNodeId),
      onSuccess: invalidate,
    }),
    progress: useMutation({
      mutationFn: ({ assignmentId, knowledgePointId, status }: { assignmentId: string; knowledgePointId: string; status: 'learning' | 'read' | 'review_recommended' }) =>
        educationApi.updateStudentKpProgress(assignmentId, knowledgePointId, status),
      onSuccess: invalidate,
    }),
  };
}

export function useLearningChatSpace(assignmentId: string | undefined) {
  return useQuery({
    queryKey: [...queryKeys.education.assignment(assignmentId ?? ''), 'chat-space'],
    queryFn: () => educationApi.getLearningChatSpace(assignmentId ?? ''),
    enabled: Boolean(assignmentId),
    staleTime: Infinity,
  });
}

export function useBookReadingState(textbookId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.education.bookReadingState(textbookId ?? ''),
    queryFn: () => educationApi.getBookReadingState(textbookId!),
    enabled: Boolean(textbookId),
    select: (rows) => Object.fromEntries(rows.map((row) => [row.knowledge_point_id, row.state])),
  });
}

export function useBookReadingMutation(textbookId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ knowledgePointId, state }: { knowledgePointId: string; state: 'viewed' | 'asked' }) => educationApi.recordBookReading(textbookId, knowledgePointId, state),
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.education.bookReadingState(textbookId) }),
  });
}

export function useBookQuestions(textbookId: string, knowledgePointId: string, assignmentId?: string) {
  return useQuery({
    queryKey: queryKeys.education.bookQuestions(textbookId, knowledgePointId, assignmentId),
    queryFn: () => educationApi.getBookQuestions(textbookId, knowledgePointId, assignmentId),
    staleTime: 0,
  });
}

export function useLessonQuestion() {
  return useMutation({ mutationFn: educationApi.askBookLesson });
}

export function useLessonChatSpace(textbookId: string, knowledgePointId: string, assignmentId?: string) {
  return useQuery({
    queryKey: queryKeys.education.lessonChatSpace(textbookId, knowledgePointId, assignmentId),
    queryFn: () => educationApi.getLessonChatSpace(textbookId, knowledgePointId, assignmentId),
    staleTime: Infinity,
    retry: false,
  });
}

export function useParentLearningTranscript(assignmentId: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: [...queryKeys.education.assignment(assignmentId ?? ''), 'chat-transcript'],
    queryFn: () => educationApi.getParentLearningTranscript(assignmentId ?? ''),
    enabled: Boolean(assignmentId) && enabled,
    staleTime: 10_000,
  });
}
