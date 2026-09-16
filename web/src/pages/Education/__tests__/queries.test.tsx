import { beforeEach, describe, expect, it, vi } from 'vitest';
import { waitFor } from '@testing-library/react';
import { createTestQueryClient, renderHookWithProviders } from '@/test/utils';
import { queryKeys } from '@/lib/queryKeys';
import * as educationApi from '../api';
import { useCompletedParseJobs, useEducationTaskCalendar, useEducationTaskDetail, useTeachingJob, useTextbook, useTextbookMutations } from '../queries';

vi.mock('../api', () => ({
  getTeachingJob: vi.fn(),
  getTextbook: vi.fn(),
  getEducationTaskCalendar: vi.fn(),
  getEducationTaskDetail: vi.fn(),
  createTextbook: vi.fn(),
  startTextbookProcessing: vi.fn(),
  listCompletedParseJobs: vi.fn(),
  startTextbookProcessingFromParseJobs: vi.fn(),
  runTextbookProcessing: vi.fn(),
  retryTextbookProcessing: vi.fn(),
  createTeachingPackage: vi.fn(),
  cancelTeachingJob: vi.fn(),
  resumeTeachingJob: vi.fn(),
  publishTextbookVersion: vi.fn(),
  assignTextbookPublication: vi.fn(),
  updateLearningProgress: vi.fn(),
  answerLearningQuestion: vi.fn(),
}));

const getTeachingJob = educationApi.getTeachingJob as unknown as ReturnType<typeof vi.fn>;
const getTextbook = educationApi.getTextbook as unknown as ReturnType<typeof vi.fn>;
const getEducationTaskCalendar = educationApi.getEducationTaskCalendar as unknown as ReturnType<typeof vi.fn>;
const getEducationTaskDetail = educationApi.getEducationTaskDetail as unknown as ReturnType<typeof vi.fn>;
const createTeachingPackage = educationApi.createTeachingPackage as unknown as ReturnType<typeof vi.fn>;
const listCompletedParseJobs = educationApi.listCompletedParseJobs as unknown as ReturnType<typeof vi.fn>;
const startTextbookProcessingFromParseJobs = educationApi.startTextbookProcessingFromParseJobs as unknown as ReturnType<typeof vi.fn>;

describe('education queries', () => {
  beforeEach(() => {
    getTeachingJob.mockReset();
    getTextbook.mockReset();
    getEducationTaskCalendar.mockReset();
    getEducationTaskDetail.mockReset();
    createTeachingPackage.mockReset();
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

    const queryClient = createTestQueryClient();
    const invalidateQueries = vi.spyOn(queryClient, 'invalidateQueries');
    const { result } = renderHookWithProviders(() => ({
      textbook: useTextbook('textbook-1'),
      job: useTeachingJob('teaching-job-1', true),
    }), { queryClient });

    await waitFor(() => expect(result.current.textbook.data?.title).toBe('教学包加工中'));

    resolveTeachingJob(completedJob);

    await waitFor(() => expect(result.current.textbook.data?.title).toBe('等待家长审阅'));
    expect(getTextbook).toHaveBeenCalledTimes(2);
    expect(invalidateQueries).toHaveBeenCalledWith({
      queryKey: queryKeys.documents.teachingUsages(),
    });
  });

  it('invalidates document teaching usage after teaching package mutations', async () => {
    createTeachingPackage.mockResolvedValue({ job_id: 'teaching-job-1' });
    const queryClient = createTestQueryClient();
    const invalidateQueries = vi.spyOn(queryClient, 'invalidateQueries');
    const { result } = renderHookWithProviders(() => useTextbookMutations(), { queryClient });

    await result.current.createTeaching.mutateAsync('version-1');

    await waitFor(() => expect(invalidateQueries).toHaveBeenCalledWith({
      queryKey: queryKeys.documents.teachingUsages(),
    }));
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
