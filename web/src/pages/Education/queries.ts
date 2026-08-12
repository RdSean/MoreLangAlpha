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
