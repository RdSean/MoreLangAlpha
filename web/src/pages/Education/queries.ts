import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
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

export function useManagedTextbookLibrary() {
  return useQuery({
    queryKey: queryKeys.education.textbooks(),
    queryFn: educationApi.listManagedTextbooks,
    staleTime: 15_000,
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
  for (const entry of incoming) bySequence.set(entry.seq, entry);
  return [...bySequence.values()]
    .sort((left, right) => left.seq - right.seq)
    .slice(-1_000);
}

export function useBookActivity(
  jobId: string | undefined,
  textbookId: string | undefined,
  enabled = true,
) {
  const queryClient = useQueryClient();
  const job = useBookJob(jobId, enabled);
  const [events, setEvents] = useState<BookActivityEvent[]>([]);
  const eventsRef = useRef<BookActivityEvent[]>([]);
  const [connectionState, setConnectionState] = useState<BookActivityConnectionState>('connecting');
  const [streamError, setStreamError] = useState<unknown>(null);
  const visible = usePageVisibility();
  const terminal = TERMINAL_MANAGED_BOOK_STATUSES.has(job.data?.status ?? 'queued');

  useEffect(() => {
    eventsRef.current = [];
    setEvents([]);
    setStreamError(null);
    setConnectionState('connecting');
  }, [jobId]);

  useEffect(() => {
    if (!enabled || !jobId || !visible || terminal) return;
    const abortController = new AbortController();
    let disposed = false;
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

    const fallbackTimer = window.setInterval(() => scheduler.notify(), 5_000);
    const afterSeq = eventsRef.current.at(-1)?.seq ?? 0;
    void educationApi.watchBookActivity(jobId, {
      afterSeq,
      signal: abortController.signal,
      onConnectionChange: (state) => {
        if (disposed) return;
        setConnectionState(state);
        if (state === 'connected') scheduler.notify();
      },
      onError: (error) => {
        if (!disposed) setStreamError(error);
      },
      onPage: async (page) => {
        if (disposed) return;
        setStreamError(null);
        if (page.events.length > 0) {
          setEvents((previous) => {
            const merged = mergeBoundedActivity(previous, page.events);
            eventsRef.current = merged;
            return merged;
          });
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
        setEvents([]);
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
  }, [enabled, jobId, queryClient, terminal, textbookId, visible]);

  return {
    ...job,
    events,
    connectionState,
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

export function useStudentKnowledgePointLesson(
  assignmentId: string | undefined,
  knowledgePointId: string | undefined,
) {
  return useQuery({
    queryKey: queryKeys.education.assignmentKnowledgePoint(assignmentId ?? '', knowledgePointId ?? ''),
    queryFn: () => educationApi.getStudentKnowledgePointLesson(assignmentId ?? '', knowledgePointId ?? ''),
    enabled: Boolean(assignmentId && knowledgePointId),
    staleTime: 30_000,
  });
}

export function useStudentLearningItems(
  assignmentId: string | undefined,
  filters: { unitId?: string; knowledgePointId?: string } = {},
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
        unitId?: string;
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
      mutationFn: ({ assignmentId, unitId }: { assignmentId: string; unitId: string }) =>
        educationApi.generateStudentUnitSummary(assignmentId, unitId),
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

export function useParentLearningTranscript(assignmentId: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: [...queryKeys.education.assignment(assignmentId ?? ''), 'chat-transcript'],
    queryFn: () => educationApi.getParentLearningTranscript(assignmentId ?? ''),
    enabled: Boolean(assignmentId) && enabled,
    staleTime: 10_000,
  });
}
