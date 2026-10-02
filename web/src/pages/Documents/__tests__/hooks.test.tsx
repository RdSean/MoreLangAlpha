import { act } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { queryKeys } from '@/lib/queryKeys';
import { createTestQueryClient, renderHookWithProviders } from '@/test/utils';
import * as documentsApi from '../api';
import { useDocumentMutations, useDocumentTeachingUsage } from '../hooks';

vi.mock('../api', () => ({
  getDocumentTeachingUsage: vi.fn(),
  createDataset: vi.fn(),
  updateDataset: vi.fn(),
  deleteDataset: vi.fn(),
  createTag: vi.fn(),
  deleteTag: vi.fn(),
  uploadDocument: vi.fn(),
  inspectDocument: vi.fn(),
  createDocumentParseJob: vi.fn(),
  cancelDocumentJob: vi.fn(),
  updateDocument: vi.fn(),
  deleteDocument: vi.fn(),
}));

const getDocumentTeachingUsage = documentsApi.getDocumentTeachingUsage as unknown as ReturnType<typeof vi.fn>;
const createDocumentParseJob = documentsApi.createDocumentParseJob as unknown as ReturnType<typeof vi.fn>;
const updateDocument = documentsApi.updateDocument as unknown as ReturnType<typeof vi.fn>;
const deleteDocument = documentsApi.deleteDocument as unknown as ReturnType<typeof vi.fn>;

function usage(structureStatus: string) {
  return {
    document_id: 'doc-1',
    parse_job_id: 'job-1',
    primary_artifact_id: 'art-1',
    textbook_id: 'textbook-1',
    textbook_title: 'Reading Explorer 3',
    source_filename: 'lesson.pdf',
    source_completed_at: '2026-09-16T12:00:00Z',
    structure_status: structureStatus,
    materials: { ready: 0, total: 0 },
    updated_at: '2026-10-02T12:00:00Z',
  };
}

describe('document teaching usage query', () => {
  beforeEach(() => {
    getDocumentTeachingUsage.mockReset();
    createDocumentParseJob.mockReset();
    updateDocument.mockReset();
    deleteDocument.mockReset();
  });

  it('polls while any package is active', async () => {
    vi.useFakeTimers();
    try {
      getDocumentTeachingUsage.mockResolvedValue([usage('running')]);

      const { result } = renderHookWithProviders(() => useDocumentTeachingUsage('doc-1'));

      await act(async () => { await vi.advanceTimersByTimeAsync(0); });
      expect(getDocumentTeachingUsage).toHaveBeenCalledTimes(1);
      expect(result.current.data?.[0].structure_status).toBe('running');

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
      getDocumentTeachingUsage.mockResolvedValue([usage('ready')]);

      const { result } = renderHookWithProviders(() => useDocumentTeachingUsage('doc-1'));

      await act(async () => { await vi.advanceTimersByTimeAsync(0); });
      expect(getDocumentTeachingUsage).toHaveBeenCalledTimes(1);
      expect(result.current.data?.[0].structure_status).toBe('ready');

      await act(async () => { await vi.advanceTimersByTimeAsync(15_000); });
      expect(getDocumentTeachingUsage).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('document mutation invalidation', () => {
  it('refreshes completed parse-job candidates when source availability changes', async () => {
    createDocumentParseJob.mockResolvedValue({ job: { job_id: 'job-1' }, status: 202 });
    updateDocument.mockResolvedValue({ document_id: 'doc-1' });
    deleteDocument.mockResolvedValue(undefined);
    const queryClient = createTestQueryClient();
    const invalidateQueries = vi.spyOn(queryClient, 'invalidateQueries');
    const { result } = renderHookWithProviders(() => useDocumentMutations(), { queryClient });

    await result.current.createParseJob.mutateAsync({
      documentId: 'doc-1',
      input: { inspection_id: 'inspection-1', parser_id: 'datalab' },
    });
    await result.current.updateDocument.mutateAsync({
      documentId: 'doc-1',
      original_filename: 'renamed.pdf',
    });
    await result.current.deleteDocument.mutateAsync('doc-1');
    await result.current.refreshDocument('doc-1');

    expect(invalidateQueries).toHaveBeenCalledWith({
      queryKey: queryKeys.documents.completedParseJobs(),
    });
    expect(invalidateQueries.mock.calls.filter(([options]) => (
      JSON.stringify(options?.queryKey) === JSON.stringify(queryKeys.documents.completedParseJobs())
    ))).toHaveLength(4);
  });
});
