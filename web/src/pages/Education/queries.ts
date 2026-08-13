import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import * as educationApi from './api';

export function useEducationTasks() {
  return useQuery({
    queryKey: queryKeys.education.tasks(),
    queryFn: educationApi.listEducationTasks,
    staleTime: 15_000,
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
    queryKey: [...queryKeys.education.all, 'members'],
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
    submit: useMutation({ mutationFn: ({ taskId, ...input }: { taskId: string } & Parameters<typeof educationApi.submitEducationTask>[1]) => educationApi.submitEducationTask(taskId, input), onSuccess: invalidate }),
    review: useMutation({ mutationFn: ({ taskId, decision, feedbackText }: { taskId: string; decision: 'revision_requested' | 'completed'; feedbackText: string }) => educationApi.reviewEducationTask(taskId, decision, feedbackText), onSuccess: invalidate }),
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
  return {
    create: useMutation({ mutationFn: educationApi.createTextbook, onSuccess: invalidate }),
    start: useMutation({ mutationFn: ({ textbookId, sourceAssetIds }: { textbookId: string; sourceAssetIds: string[] }) => educationApi.startTextbookProcessing(textbookId, sourceAssetIds), onSuccess: invalidate }),
    run: useMutation({ mutationFn: educationApi.runTextbookProcessing, onSuccess: invalidate }),
    retry: useMutation({ mutationFn: educationApi.retryTextbookProcessing, onSuccess: invalidate }),
    publish: useMutation({ mutationFn: ({ textbookId, versionId, teachingPackageId }: { textbookId: string; versionId: string; teachingPackageId: string }) => educationApi.publishTextbookVersion(textbookId, versionId, teachingPackageId), onSuccess: invalidate }),
    assign: useMutation({ mutationFn: ({ publicationId, studentUserId }: { publicationId: string; studentUserId: string }) => educationApi.assignTextbookPublication(publicationId, studentUserId), onSuccess: invalidate }),
    progress: useMutation({ mutationFn: ({ assignmentId, chapterId, status }: { assignmentId: string; chapterId: string; status: 'learning' | 'read' | 'check_completed' | 'review_recommended' }) => educationApi.updateLearningProgress(assignmentId, chapterId, status), onSuccess: invalidate }),
    answer: useMutation({ mutationFn: ({ assignmentId, questionId, selectedOption }: { assignmentId: string; questionId: string; selectedOption: string }) => educationApi.answerLearningQuestion(assignmentId, questionId, selectedOption), onSuccess: invalidate }),
  };
}
