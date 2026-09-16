import { useEffect, useRef } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import * as educationApi from './api';
import type { EducationTaskCalendarRequest, TeachingJob, TeachingReviewAssetKind } from './types';

const terminalTeachingJobStatuses = new Set<TeachingJob['status']>(['completed', 'failed', 'cancelled']);

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

export function useTextbookLibrary() {
  return useQuery({
    queryKey: queryKeys.education.textbooks(),
    queryFn: educationApi.listTextbooks,
    staleTime: 15_000,
  });
}

export function useTextbook(textbookId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.education.textbook(textbookId ?? ''),
    queryFn: () => educationApi.getTextbook(textbookId ?? ''),
    enabled: Boolean(textbookId),
    staleTime: 10_000,
  });
}

export function useCompletedParseJobs(enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.documents.completedParseJobs(),
    queryFn: educationApi.listCompletedParseJobs,
    enabled,
    staleTime: 10_000,
  });
}

export function useTeachingJob(jobId: string | undefined, enabled: boolean) {
  const queryClient = useQueryClient();
  const lastInvalidatedTerminalStatus = useRef<TeachingJob['status'] | null>(null);
  const query = useQuery({
    queryKey: queryKeys.education.teachingJob(jobId ?? ''),
    queryFn: () => educationApi.getTeachingJob(jobId ?? ''),
    enabled: Boolean(jobId) && enabled,
    staleTime: 2_000,
    refetchInterval: enabled ? 5_000 : false,
    refetchIntervalInBackground: enabled,
  });

  useEffect(() => {
    const status = query.data?.status;
    if (!status || !terminalTeachingJobStatuses.has(status)) {
      lastInvalidatedTerminalStatus.current = null;
      return;
    }
    if (lastInvalidatedTerminalStatus.current === status) return;

    lastInvalidatedTerminalStatus.current = status;
    void Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.education.all }),
      queryClient.invalidateQueries({ queryKey: queryKeys.documents.teachingUsages() }),
    ]);
  }, [query.data?.status, queryClient]);

  return query;
}

export function useTeachingPackageAssets(teachingPackageId: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.education.teachingPackageAssets(teachingPackageId ?? ''),
    queryFn: () => educationApi.getTeachingPackageAssets(teachingPackageId ?? ''),
    enabled: Boolean(teachingPackageId) && enabled,
    staleTime: 15_000,
  });
}

export function useTeachingChapterAsset(
  teachingPackageId: string | undefined,
  chapterId: string | undefined,
  kind: TeachingReviewAssetKind | undefined,
  enabled: boolean,
) {
  return useQuery({
    queryKey: queryKeys.education.teachingChapterAsset(teachingPackageId ?? '', chapterId ?? '', kind ?? ''),
    queryFn: () => educationApi.getTeachingChapterAsset(
      teachingPackageId ?? '',
      chapterId ?? '',
      kind as TeachingReviewAssetKind,
    ),
    enabled: Boolean(teachingPackageId && chapterId && kind) && enabled,
    staleTime: Infinity,
  });
}

export function useLearningAssignments(enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.education.learning(),
    queryFn: educationApi.listLearningAssignments,
    enabled,
    staleTime: 15_000,
  });
}

export function useStudentLearning(assignmentId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.education.assignment(assignmentId ?? ''),
    queryFn: () => educationApi.getStudentLearning(assignmentId ?? ''),
    enabled: Boolean(assignmentId),
    staleTime: 10_000,
  });
}

export function useLearningChatSpace(assignmentId: string | undefined) {
  return useQuery({
    queryKey: [...queryKeys.education.assignment(assignmentId ?? ''), 'chat-space'],
    queryFn: () => educationApi.getLearningChatSpace(assignmentId ?? ''),
    enabled: Boolean(assignmentId),
    staleTime: Infinity,
  });
}

export function useParentLearningRecords(assignmentId: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: [...queryKeys.education.assignment(assignmentId ?? ''), 'records'],
    queryFn: () => educationApi.getParentLearningRecords(assignmentId ?? ''),
    enabled: Boolean(assignmentId) && enabled,
    staleTime: 10_000,
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

export function useTextbookMutations() {
  const queryClient = useQueryClient();
  const invalidate = () => queryClient.invalidateQueries({ queryKey: queryKeys.education.all });
  const invalidateTeaching = () => Promise.all([
    invalidate(),
    queryClient.invalidateQueries({ queryKey: queryKeys.documents.teachingUsages() }),
  ]);
  return {
    create: useMutation({ mutationFn: educationApi.createTextbook, onSuccess: invalidate }),
    start: useMutation({ mutationFn: ({ textbookId, sourceParseJobIds }: { textbookId: string; sourceParseJobIds: string[] }) => educationApi.startTextbookProcessingFromParseJobs(textbookId, sourceParseJobIds), onSuccess: invalidate }),
    run: useMutation({ mutationFn: educationApi.runTextbookProcessing, onSuccess: invalidate }),
    retry: useMutation({ mutationFn: educationApi.retryTextbookProcessing, onSuccess: invalidate }),
    createTeaching: useMutation({ mutationFn: educationApi.createTeachingPackage, onSuccess: invalidateTeaching }),
    cancelTeaching: useMutation({ mutationFn: educationApi.cancelTeachingJob, onSuccess: invalidateTeaching }),
    resumeTeaching: useMutation({ mutationFn: educationApi.resumeTeachingJob, onSuccess: invalidateTeaching }),
    publish: useMutation({ mutationFn: ({ textbookId, versionId, teachingPackageId }: { textbookId: string; versionId: string; teachingPackageId: string }) => educationApi.publishTextbookVersion(textbookId, versionId, teachingPackageId), onSuccess: invalidateTeaching }),
    assign: useMutation({ mutationFn: ({ publicationId, studentUserId }: { publicationId: string; studentUserId: string }) => educationApi.assignTextbookPublication(publicationId, studentUserId), onSuccess: invalidate }),
    progress: useMutation({ mutationFn: ({ assignmentId, chapterId, status }: { assignmentId: string; chapterId: string; status: 'learning' | 'read' | 'check_completed' | 'review_recommended' }) => educationApi.updateLearningProgress(assignmentId, chapterId, status), onSuccess: invalidate }),
    answer: useMutation({ mutationFn: ({ assignmentId, questionId, selectedOption }: { assignmentId: string; questionId: string; selectedOption: string }) => educationApi.answerLearningQuestion(assignmentId, questionId, selectedOption), onSuccess: invalidate }),
  };
}
