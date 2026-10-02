import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/api/client', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import { api } from '@/api/client';
import { createManagedTextbook, listManagedBookSources } from '../api';

describe('managed textbook source API', () => {
  beforeEach(() => vi.clearAllMocks());

  it('lists eligible completed parse artifacts', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { items: [{ parse_job_id: 'job-1' }] } });

    await expect(listManagedBookSources()).resolves.toEqual([{ parse_job_id: 'job-1' }]);
    expect(api.get).toHaveBeenCalledWith('/api/v1/education/textbook-sources');
  });

  it('creates and queues a textbook in one request', async () => {
    const input = {
      parse_job_id: 'job-1',
      primary_artifact_id: 'artifact-1',
      title: '精读教材',
      idempotency_key: 'request-1',
    };
    vi.mocked(api.post).mockResolvedValue({ data: { textbook_id: 'book-1', job_id: 'book-job-1' } });

    await expect(createManagedTextbook(input)).resolves.toEqual({ textbook_id: 'book-1', job_id: 'book-job-1' });
    expect(api.post).toHaveBeenCalledWith('/api/v1/education/textbooks', input);
  });
});
