import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import * as familyAccountsApi from './api';

export function useFamilyChildren(enabled = true) {
  return useQuery({
    queryKey: queryKeys.settings.family.children(),
    queryFn: familyAccountsApi.listFamilyChildren,
    enabled,
    staleTime: 30_000,
  });
}

function invalidateFamilyLlmQueries(queryClient: ReturnType<typeof useQueryClient>) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.settings.family.llmPool() }),
    queryClient.invalidateQueries({ queryKey: queryKeys.settings.family.availability() }),
    queryClient.invalidateQueries({ queryKey: queryKeys.settings.family.preference() }),
  ]);
}

export function useFamilyLlmPool(enabled = true) {
  return useQuery({
    queryKey: queryKeys.settings.family.llmPool(),
    queryFn: familyAccountsApi.getFamilyLlmPool,
    enabled,
    staleTime: 30_000,
  });
}

export function useCreateFamilyLlmEndpoint() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: familyAccountsApi.createFamilyLlmEndpoint,
    onSuccess: () => invalidateFamilyLlmQueries(queryClient),
  });
}

export function useUpdateFamilyLlmEndpoint() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ endpointId, input }: {
      endpointId: string;
      input: familyAccountsApi.FamilyLlmEndpointUpdate;
    }) => familyAccountsApi.updateFamilyLlmEndpoint(endpointId, input),
    onSuccess: () => invalidateFamilyLlmQueries(queryClient),
  });
}

export function useDeleteFamilyLlmEndpoint() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: familyAccountsApi.deleteFamilyLlmEndpoint,
    onSuccess: () => invalidateFamilyLlmQueries(queryClient),
  });
}

export function useSetFamilyLlmDefault() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: familyAccountsApi.setFamilyLlmDefault,
    onSuccess: () => invalidateFamilyLlmQueries(queryClient),
  });
}

export function useFamilyChildWorkspace(studentUserId: string | null, enabled = true) {
  return useQuery({
    queryKey: queryKeys.settings.family.workspace(studentUserId ?? ''),
    queryFn: () => familyAccountsApi.getFamilyChildWorkspace(studentUserId ?? ''),
    enabled: Boolean(studentUserId) && enabled,
    staleTime: 30_000,
  });
}

export function useFamilyChildThreads(studentUserId: string | null, limit = 20, offset = 0, enabled = true) {
  return useQuery({
    queryKey: queryKeys.settings.family.threads(studentUserId ?? '', limit, offset),
    queryFn: () => familyAccountsApi.listFamilyChildThreads(studentUserId ?? '', limit, offset),
    enabled: Boolean(studentUserId) && enabled,
    staleTime: 15_000,
  });
}

export function useCreateChildAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: familyAccountsApi.createChildAccount,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.settings.family.children() }),
  });
}
