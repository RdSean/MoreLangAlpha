import { beforeEach, describe, expect, it, vi } from 'vitest';
import { waitFor } from '@testing-library/react';
import { renderHookWithProviders } from '@/test/utils';
import * as educationApi from '../api';
import { useTeachingJob, useTextbook } from '../queries';

vi.mock('../api', () => ({
  getTeachingJob: vi.fn(),
  getTextbook: vi.fn(),
}));

const getTeachingJob = educationApi.getTeachingJob as unknown as ReturnType<typeof vi.fn>;
const getTextbook = educationApi.getTextbook as unknown as ReturnType<typeof vi.fn>;

describe('education queries', () => {
  beforeEach(() => {
    getTeachingJob.mockReset();
    getTextbook.mockReset();
  });

  it('refreshes the active textbook after a teaching job reaches a terminal status', async () => {
    let resolveTeachingJob: (value: unknown) => void = () => {};
    const completedJob = {
      job_id: 'teaching-job-1',
      teaching_package_id: 'package-1',
      content_version_id: 'version-1',
      status: 'completed',
      phase: 'review',
      attempt_count: 1,
      completed_chapter_count: 1,
      total_chapter_count: 1,
      actions: [],
      events: [],
      attempts: [],
    };
    getTextbook
      .mockResolvedValueOnce({ textbook_id: 'textbook-1', household_id: 'household-1', title: '教学包加工中', slug: 'english-2', versions: [] })
      .mockResolvedValueOnce({ textbook_id: 'textbook-1', household_id: 'household-1', title: '等待家长审阅', slug: 'english-2', versions: [] });
    getTeachingJob
      .mockReturnValueOnce(new Promise((resolve) => {
        resolveTeachingJob = resolve;
      }))
      .mockResolvedValue(completedJob);

    const { result } = renderHookWithProviders(() => ({
      textbook: useTextbook('textbook-1'),
      job: useTeachingJob('teaching-job-1', true),
    }));

    await waitFor(() => expect(result.current.textbook.data?.title).toBe('教学包加工中'));

    resolveTeachingJob(completedJob);

    await waitFor(() => expect(result.current.textbook.data?.title).toBe('等待家长审阅'));
    expect(getTextbook).toHaveBeenCalledTimes(2);
  });
});
