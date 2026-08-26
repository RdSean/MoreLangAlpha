import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { getEducationHomeworkDictionaries } from '@/pages/Education/api';
import * as familyAccountsApi from './api';

export function useFamilyChildren(enabled = true) {
  return useQuery({
    queryKey: queryKeys.settings.family.children(),
    queryFn: familyAccountsApi.listFamilyChildren,
    enabled,
    staleTime: 30_000,
  });
}

export function useFamilyLlmAvailability(enabled = true) {
  return useQuery({
    queryKey: queryKeys.settings.family.availability(),
    queryFn: familyAccountsApi.getFamilyLlmAvailability,
    enabled,
    staleTime: 15_000,
  });
}

export function useEducationHomeworkDictionaries(enabled = true) {
  return useQuery({
    queryKey: queryKeys.education.dictionaries(),
    queryFn: getEducationHomeworkDictionaries,
    enabled,
    staleTime: Infinity,
  });
}

export function useFamilyChildEducationProfile(studentUserId: string | null, enabled = true) {
  return useQuery({
    queryKey: queryKeys.settings.family.educationProfile(studentUserId ?? ''),
    queryFn: () => familyAccountsApi.getFamilyChildEducationProfile(studentUserId ?? ''),
    enabled: Boolean(studentUserId) && enabled,
    staleTime: 30_000,
  });
}

export function useUpdateFamilyChildEducationProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ studentUserId, gradeCode }: { studentUserId: string; gradeCode: string | null }) => (
      familyAccountsApi.updateFamilyChildEducationProfile(studentUserId, gradeCode)
    ),
    onSuccess: (profile) => {
      const profileQueryKey = queryKeys.settings.family.educationProfile(profile.user_id);
      queryClient.setQueryData(profileQueryKey, profile);
      return Promise.all([
        queryClient.invalidateQueries({ queryKey: profileQueryKey }),
      queryClient.invalidateQueries({ queryKey: queryKeys.education.members() }),
      ]);
    },
  });
}

export function useSetFamilyLlmPreference() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: familyAccountsApi.setFamilyLlmPreference,
    onSuccess: () => Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.settings.family.availability() }),
      queryClient.invalidateQueries({ queryKey: queryKeys.settings.family.preference() }),
    ]),
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
