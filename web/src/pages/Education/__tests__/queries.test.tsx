import { beforeEach, describe, expect, it, vi } from 'vitest';
import { waitFor } from '@testing-library/react';
import { createTestQueryClient, renderHookWithProviders } from '@/test/utils';
import { queryKeys } from '@/lib/queryKeys';
import * as educationApi from '../api';
import { useCompletedParseJobs, useEducationTaskCalendar, useEducationTaskDetail, useTextbookMutations } from '../queries';

vi.mock('../api', () => ({
  getEducationTaskCalendar: vi.fn(),
  getEducationTaskDetail: vi.fn(),
  createTextbook: vi.fn(),
  startTextbookProcessing: vi.fn(),
  listCompletedParseJobs: vi.fn(),
  startTextbookProcessingFromParseJobs: vi.fn(),
  runTextbookProcessing: vi.fn(),
  retryTextbookProcessing: vi.fn(),
  assignTextbookPublication: vi.fn(),
}));

const getEducationTaskCalendar = educationApi.getEducationTaskCalendar as unknown as ReturnType<typeof vi.fn>;
const getEducationTaskDetail = educationApi.getEducationTaskDetail as unknown as ReturnType<typeof vi.fn>;
const listCompletedParseJobs = educationApi.listCompletedParseJobs as unknown as ReturnType<typeof vi.fn>;
const startTextbookProcessingFromParseJobs = educationApi.startTextbookProcessingFromParseJobs as unknown as ReturnType<typeof vi.fn>;

describe('education queries', () => {
  beforeEach(() => {
    getEducationTaskCalendar.mockReset();
    getEducationTaskDetail.mockReset();
    listCompletedParseJobs.mockReset();
    startTextbookProcessingFromParseJobs.mockReset();
  });

  it('loads completed parse-job candidates once when enabled', async () => {
    listCompletedParseJobs.mockResolvedValue([
      {
        producer_job_id: 'job-parse-1',
        document_id: 'doc-1',
        primary_artifact_id: 'art-1',
        filename: 'body.pdf',
        media_type: 'application/pdf',
        format: 'pdf',
        parser_id: 'datalab',
        parser_name: 'Datalab',
        parser_version: '2',
        parse_completed_at: '2026-09-16T10:00:00Z',
        size_bytes: 1024,
        artifact_count: 3,
      },
    ]);

    const queryClient = createTestQueryClient();
    const { result } = renderHookWithProviders(() => ({
      completed: useCompletedParseJobs(true),
      disabled: useCompletedParseJobs(false),
    }), { queryClient });

    await waitFor(() => expect(result.current.completed.data?.[0]?.producer_job_id).toBe('job-parse-1'));
    expect(listCompletedParseJobs).toHaveBeenCalledTimes(1);
    expect(queryClient.getQueryData(queryKeys.documents.completedParseJobs())).toEqual([
      expect.objectContaining({ producer_job_id: 'job-parse-1' }),
    ]);
  });

  it('starts textbook processing from selected parse jobs', async () => {
    startTextbookProcessingFromParseJobs.mockResolvedValue({ job_id: 'job-1' });
    const queryClient = createTestQueryClient();
    const { result } = renderHookWithProviders(() => useTextbookMutations(), { queryClient });

    await result.current.start.mutateAsync({
      textbookId: 'textbook-1',
      sourceParseJobIds: ['job-parse-1', 'job-parse-2'],
    });

    expect(startTextbookProcessingFromParseJobs).toHaveBeenCalledWith(
      'textbook-1',
      ['job-parse-1', 'job-parse-2'],
    );
  });

  it('loads the role-scoped task detail only when a task is selected', async () => {
    getEducationTaskDetail.mockResolvedValue({
      task_id: 'task-1',
      parent_materials: [],
      submissions: [],
    });

    const { result } = renderHookWithProviders(() => useEducationTaskDetail('task-1'));

    await waitFor(() => expect(result.current.data?.task_id).toBe('task-1'));
    expect(getEducationTaskDetail).toHaveBeenCalledWith('task-1');
  });

  it('loads a calendar for the chosen student and month range', async () => {
    getEducationTaskCalendar.mockResolvedValue({
      student_id: 'student-1',
      start_date: '2026-08-01',
      end_date: '2026-08-31',
      days: [],
      stats: { today_count: 0, week_count: 0, overdue_count: 0, completed_count: 0 },
    });

    const { result } = renderHookWithProviders(() => useEducationTaskCalendar({
      start_date: '2026-08-01',
      end_date: '2026-08-31',
      student_id: 'student-1',
    }));

    await waitFor(() => expect(result.current.data?.student_id).toBe('student-1'));
    expect(getEducationTaskCalendar).toHaveBeenCalledWith({
      start_date: '2026-08-01',
      end_date: '2026-08-31',
      student_id: 'student-1',
    });
  });
});
