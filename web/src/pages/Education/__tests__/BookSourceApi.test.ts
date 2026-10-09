import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/api/client', () => ({
  api: {
    delete: vi.fn(),
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import { api } from '@/api/client';
import {
  assignManagedBookStudents,
  createManagedTextbook,
  listManagedBookAssignments,
  listManagedBookSources,
  revokeManagedBookStudents,
  uploadTextbookCover,
  deleteTextbookCover,
} from '../api';

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

  it('lists, adds, and revokes managed textbook assignments', async () => {
    const assignment = {
      textbook_id: 'book-1',
      student_user_id: 'student-1',
      assigned_at: '2026-10-02T07:00:00Z',
    };
    const input = { student_user_ids: ['student-1'] };
    vi.mocked(api.get).mockResolvedValue({ data: [assignment] });
    vi.mocked(api.post).mockResolvedValue({ data: [assignment] });
    vi.mocked(api.delete).mockResolvedValue({});

    await expect(listManagedBookAssignments('book-1')).resolves.toEqual([assignment]);
    await expect(assignManagedBookStudents('book-1', input)).resolves.toEqual([assignment]);
    await expect(revokeManagedBookStudents('book-1', input)).resolves.toBeUndefined();

    const url = '/api/v1/education/textbooks/book-1/assignments';
    expect(api.get).toHaveBeenCalledWith(url);
    expect(api.post).toHaveBeenCalledWith(url, input);
    expect(api.delete).toHaveBeenCalledWith(url, { data: input });
  });

  it('uploads and removes a textbook cover through the authenticated API', async () => {
    const file = new File(['png'], 'cover.png', { type: 'image/png' });
    vi.mocked(api.post).mockResolvedValue({ data: { cover_available: true, cover_updated_at: 'now' } });
    vi.mocked(api.delete).mockResolvedValue({});

    await expect(uploadTextbookCover('book-1', file)).resolves.toEqual({ cover_available: true, cover_updated_at: 'now' });
    await expect(deleteTextbookCover('book-1')).resolves.toBeUndefined();

    expect(api.post).toHaveBeenCalledWith(
      '/api/v1/education/textbooks/book-1/cover',
      expect.any(FormData),
      { headers: { 'Content-Type': 'multipart/form-data' } },
    );
    expect(api.delete).toHaveBeenCalledWith('/api/v1/education/textbooks/book-1/cover');
  });
});
