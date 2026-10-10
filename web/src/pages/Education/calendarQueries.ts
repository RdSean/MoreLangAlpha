import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/contexts/AuthContext';
import { queryKeys } from '@/lib/queryKeys';
import { getFamilyCalendarEvents, getFamilyCalendarSources, importFamilyCalendar, removeFamilyCalendar, type FamilyCalendarRange } from './calendarApi';

export function useFamilyCalendarSources() {
  const { member } = useAuth();
  return useQuery({
    queryKey: queryKeys.education.familyCalendarSources(member?.household_id ?? ''),
    queryFn: getFamilyCalendarSources,
    enabled: Boolean(member?.household_id),
    staleTime: 30_000,
    refetchOnWindowFocus: 'always',
  });
}

export function useFamilyCalendarEvents(params: FamilyCalendarRange) {
  const { member } = useAuth();
  return useQuery({
    queryKey: queryKeys.education.familyCalendarEvents(member?.household_id ?? '', params),
    queryFn: () => getFamilyCalendarEvents(params),
    enabled: Boolean(member?.household_id),
    staleTime: 30_000,
    refetchOnWindowFocus: 'always',
  });
}

export function useImportFamilyCalendar() {
  const client = useQueryClient();
  const { member } = useAuth();
  return useMutation({
    mutationFn: importFamilyCalendar,
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.education.familyCalendar(member?.household_id ?? '') }),
  });
}

export function useRemoveFamilyCalendar() {
  const client = useQueryClient();
  const { member } = useAuth();
  return useMutation({
    mutationFn: removeFamilyCalendar,
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.education.familyCalendar(member?.household_id ?? '') }),
  });
}
