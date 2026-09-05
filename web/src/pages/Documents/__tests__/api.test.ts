import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Mock } from 'vitest';

vi.mock('@/api/client', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    defaults: { baseURL: 'http://localhost:8000' },
  },
}));

import { api } from '@/api/client';
import {
  artifactDownloadUrl,
  cancelDocumentJob,
  createDocumentParseJob,
  listDocuments,
  uploadDocument,
  watchDocumentJob,
} from '../api';
import type { ParseJob } from '../types';

const mockGet = api.get as Mock;
const mockPost = api.post as Mock;

function job(status: ParseJob['status'], version: number): ParseJob {
  return {
    job_id: 'job-A1b2C3d4E5f6',
    document_id: 'doc-A1b2C3d4E5f6',
    inspection_id: 'ins-A1b2C3d4E5f6',
    parser_id: 'anydoc-local',
    parser_name: 'AnyDoc Local',
    parser_version: '0.2.4',
    parser_options: {},
    request_mode: 'async',
    status,
    stage: status === 'completed' ? 'completed' : 'parsing',
    percentage: status === 'completed' ? 100 : 40,
    status_version: version,
    attempt_count: 1,
  };
}

function sseResponse(snapshot: ParseJob): Response {
  return new Response(
    `id: ${snapshot.status_version}\nevent: snapshot\ndata: ${JSON.stringify(snapshot)}\n\n`,
    { status: 200, headers: { 'Content-Type': 'text/event-stream' } },
  );
}

describe('Documents API', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('serializes upload file and repeated Dataset/tag fields', async () => {
    mockPost.mockResolvedValue({ data: { document_id: 'doc-A1b2C3d4E5f6' } });
    const file = new File(['%PDF-demo'], 'lesson.pdf', { type: 'application/pdf' });

    await uploadDocument(file, {
      datasetIds: ['dts-A1b2C3d4E5f6', 'dts-Z9y8X7w6V5u4'],
      tagIds: ['tag-A1b2C3d4E5f6', 'tag-Z9y8X7w6V5u4'],
    });

    const [url, body, config] = mockPost.mock.calls[0];
    expect(url).toBe('/api/v1/documents');
    expect(config.headers['Content-Type']).toBe('multipart/form-data');
    expect((body as FormData).get('file')).toBe(file);
    expect((body as FormData).getAll('dataset_ids')).toEqual([
      'dts-A1b2C3d4E5f6',
      'dts-Z9y8X7w6V5u4',
    ]);
    expect((body as FormData).getAll('tag_ids')).toEqual([
      'tag-A1b2C3d4E5f6',
      'tag-Z9y8X7w6V5u4',
    ]);
  });

  it('passes document filters and pagination as query parameters', async () => {
    mockGet.mockResolvedValue({ data: { items: [], total: 0, limit: 20, offset: 40 } });
    const filters = {
      query: 'algebra',
      dataset_id: 'dts-A1b2C3d4E5f6',
      tag_ids: ['tag-A1b2C3d4E5f6'],
      classification: 'text_based' as const,
      parse_status: 'completed' as const,
      limit: 20,
      offset: 40,
    };

    await listDocuments(filters);

    expect(mockGet).toHaveBeenCalledWith('/api/v1/documents', {
      params: filters,
      paramsSerializer: { indexes: null },
    });
  });

  it.each([200, 202] as const)('preserves parse-job HTTP status %s', async (status) => {
    const queued = job('queued', 0);
    mockPost.mockResolvedValue({ data: queued, status });

    const result = await createDocumentParseJob(queued.document_id, {
      inspection_id: queued.inspection_id,
      parser_id: queued.parser_id,
      mode: status === 200 ? 'sync' : 'async',
      options: {},
    });

    expect(result).toEqual({ job: queued, status });
  });

  it('posts cancellation to the owned job endpoint', async () => {
    const cancelled = job('cancelled', 3);
    mockPost.mockResolvedValue({ data: cancelled });

    await cancelDocumentJob(cancelled.job_id);

    expect(mockPost).toHaveBeenCalledWith(
      `/api/v1/document-jobs/${cancelled.job_id}/cancel`,
    );
  });

  it('builds the authenticated redirect endpoint without exposing object storage', () => {
    expect(artifactDownloadUrl('art-A1b2C3d4E5f6')).toBe(
      'http://localhost:8000/api/v1/document-artifacts/art-A1b2C3d4E5f6/download',
    );
  });

  it('reconnects SSE from the latest database status version', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(sseResponse(job('running', 2)))
      .mockResolvedValueOnce(sseResponse(job('completed', 3)));
    vi.stubGlobal('fetch', fetchMock);
    const seen: number[] = [];

    await watchDocumentJob('job-A1b2C3d4E5f6', {
      onSnapshot: (snapshot) => seen.push(snapshot.status_version),
      reconnectDelayMs: 0,
    });

    expect(seen).toEqual([2, 3]);
    expect(fetchMock.mock.calls[0][0]).toContain('after_status_version=-1');
    expect(fetchMock.mock.calls[1][0]).toContain('after_status_version=2');
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ credentials: 'include' });
  });

  it('falls back to periodic owned-job GET after repeated SSE errors', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')));
    const completed = job('completed', 4);
    mockGet.mockResolvedValue({ data: completed });
    const seen: number[] = [];

    await watchDocumentJob('job-A1b2C3d4E5f6', {
      onSnapshot: (snapshot) => seen.push(snapshot.status_version),
      maxSseErrors: 2,
      reconnectDelayMs: 0,
      pollIntervalMs: 0,
    });

    expect(mockGet).toHaveBeenCalledWith('/api/v1/document-jobs/job-A1b2C3d4E5f6');
    expect(seen).toEqual([4]);
  });
});
