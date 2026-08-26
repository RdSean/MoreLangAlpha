import { act, renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';

import { queryKeys } from '@/lib/queryKeys';
import * as familyAccountsApi from '../api';
import { useUpdateFamilyChildEducationProfile } from '../queries';

vi.mock('../api', () => ({
  updateFamilyChildEducationProfile: vi.fn(),
}));

const updateProfile = familyAccountsApi.updateFamilyChildEducationProfile as unknown as ReturnType<typeof vi.fn>;

function wrapperFor(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

describe('family account queries', () => {
  beforeEach(() => {
    updateProfile.mockReset();
  });

  it('writes the returned student profile into its query cache before refetching', async () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: Infinity },
        mutations: { retry: false },
      },
    });
    const queryKey = queryKeys.settings.family.educationProfile('student-1');
    const previousProfile = { household_id: 'household-1', user_id: 'student-1', grade_code: 'g4' };
    const updatedProfile = { household_id: 'household-1', user_id: 'student-1', grade_code: 'g5' };
    queryClient.setQueryData(queryKey, previousProfile);
    updateProfile.mockResolvedValue(updatedProfile);

    const { result } = renderHook(() => useUpdateFamilyChildEducationProfile(), { wrapper: wrapperFor(queryClient) });

    await act(async () => {
      await result.current.mutateAsync({ studentUserId: 'student-1', gradeCode: 'g5' });
    });

    expect(queryClient.getQueryData(queryKey)).toEqual(updatedProfile);
  });
});
