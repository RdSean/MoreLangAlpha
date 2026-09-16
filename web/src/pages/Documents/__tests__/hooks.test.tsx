import { act } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderHookWithProviders } from '@/test/utils';
import * as documentsApi from '../api';
import { useDocumentTeachingUsage } from '../hooks';

vi.mock('../api', () => ({
  getDocumentTeachingUsage: vi.fn(),
}));

const getDocumentTeachingUsage = documentsApi.getDocumentTeachingUsage as unknown as ReturnType<typeof vi.fn>;

function usage(status: string) {
  return {
    document_id: 'doc-1',
    producer_job_id: 'job-1',
    primary_artifact_id: 'art-1',
    textbook_id: 'textbook-1',
    textbook_title: 'Reading Explorer 3',
    content_version_id: 'version-1',
    content_version_sequence: 1,
    artifact_position: 1,
    teaching_package_id: 'package-1',
    teaching_package_sequence: 1,
    status,
    publication_id: null,
    is_published: false,
    has_asset_manifest: false,
  };
}

describe('document teaching usage query', () => {
  beforeEach(() => {
    getDocumentTeachingUsage.mockReset();
  });

  it('polls while any package is active', async () => {
    vi.useFakeTimers();
    try {
      getDocumentTeachingUsage.mockResolvedValue([usage('generating_teaching')]);

      const { result } = renderHookWithProviders(() => useDocumentTeachingUsage('doc-1'));

      await act(async () => { await vi.advanceTimersByTimeAsync(0); });
      expect(getDocumentTeachingUsage).toHaveBeenCalledTimes(1);
      expect(result.current.data?.[0].status).toBe('generating_teaching');

      await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
      expect(getDocumentTeachingUsage).toHaveBeenCalledTimes(2);

      await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
      expect(getDocumentTeachingUsage).toHaveBeenCalledTimes(3);
    } finally {
      vi.useRealTimers();
    }
  });

  it('stops polling once every package status is terminal', async () => {
    vi.useFakeTimers();
    try {
      getDocumentTeachingUsage.mockResolvedValue([usage('review')]);

      const { result } = renderHookWithProviders(() => useDocumentTeachingUsage('doc-1'));

      await act(async () => { await vi.advanceTimersByTimeAsync(0); });
      expect(getDocumentTeachingUsage).toHaveBeenCalledTimes(1);
      expect(result.current.data?.[0].status).toBe('review');

      await act(async () => { await vi.advanceTimersByTimeAsync(15_000); });
      expect(getDocumentTeachingUsage).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });
});
