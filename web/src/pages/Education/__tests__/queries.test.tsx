import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, waitFor } from '@testing-library/react';
import { createTestQueryClient, renderHookWithProviders } from '@/test/utils';
import { queryKeys } from '@/lib/queryKeys';
import * as educationApi from '../api';
import { useBookPipelineMutations, useBookPipelineProgress, useCompletedParseJobs, useEducationTaskCalendar, useEducationTaskDetail, useStructureMutations, useTextbookMutations } from '../queries';

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
  cancelBookPipelineJob: vi.fn(),
  getBookPipelineJobProgress: vi.fn(),
  generateKnowledgePointLesson: vi.fn(),
  resumeStructureGenerationJob: vi.fn(),
  generateBookAssets: vi.fn(),
  updateTextbookStructure: vi.fn(),
  acceptTextbookStructure: vi.fn(),
  createKnowledgePointLessonRevision: vi.fn(),
  approveKnowledgePointLesson: vi.fn(),
  publishTextbookStructure: vi.fn(),
}));

const getEducationTaskCalendar = educationApi.getEducationTaskCalendar as unknown as ReturnType<typeof vi.fn>;
const getEducationTaskDetail = educationApi.getEducationTaskDetail as unknown as ReturnType<typeof vi.fn>;
const listCompletedParseJobs = educationApi.listCompletedParseJobs as unknown as ReturnType<typeof vi.fn>;
const startTextbookProcessingFromParseJobs = educationApi.startTextbookProcessingFromParseJobs as unknown as ReturnType<typeof vi.fn>;
const getBookPipelineJobProgress = educationApi.getBookPipelineJobProgress as unknown as ReturnType<typeof vi.fn>;
const cancelBookPipelineJob = educationApi.cancelBookPipelineJob as unknown as ReturnType<typeof vi.fn>;
const generateKnowledgePointLesson = educationApi.generateKnowledgePointLesson as unknown as ReturnType<typeof vi.fn>;

describe('education queries', () => {
  beforeEach(() => {
    getEducationTaskCalendar.mockReset();
    getEducationTaskDetail.mockReset();
    listCompletedParseJobs.mockReset();
    startTextbookProcessingFromParseJobs.mockReset();
    cancelBookPipelineJob.mockReset();
    getBookPipelineJobProgress.mockReset();
    generateKnowledgePointLesson.mockReset();
  });

  it('passes lesson generation guidance through the mutation', async () => {
    generateKnowledgePointLesson.mockResolvedValue({
      generation_job_id: 'generation-1',
      version_id: 'version-1',
      scope: 'lesson',
      status: 'queued',
      attempt_count: 0,
    });
    const { result } = renderHookWithProviders(() => useStructureMutations());

    await result.current.generateLesson.mutateAsync({
      knowledgePointId: 'kp-1',
      autoGrading: true,
      prompt: '使用中文讲解。',
    });

    expect(generateKnowledgePointLesson).toHaveBeenCalledWith(
      'kp-1',
      true,
      '使用中文讲解。',
    );
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

  it('polls book-pipeline progress every two seconds until terminal', async () => {
    vi.useFakeTimers();
    try {
      getBookPipelineJobProgress
        .mockResolvedValueOnce({
          job_id: 'job-1',
          status: 'running',
          stages: [],
          last_sequence: 1,
        })
        .mockResolvedValue({
          job_id: 'job-1',
          status: 'completed',
          stages: [],
          last_sequence: 2,
        });

      const { result, queryClient } = renderHookWithProviders(() =>
        useBookPipelineProgress('job-1'),
      );

      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(getBookPipelineJobProgress).toHaveBeenCalledTimes(1);
      expect(result.current.data?.status).toBe('running');

      await act(async () => {
        await vi.advanceTimersByTimeAsync(2_000);
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(getBookPipelineJobProgress).toHaveBeenCalledTimes(2);
      expect(
        queryClient.getQueryData<{ status: string }>(
          queryKeys.education.bookPipelineJobProgress('job-1'),
        )?.status,
      ).toBe('completed');

      await act(async () => {
        await vi.advanceTimersByTimeAsync(10_000);
      });
      expect(getBookPipelineJobProgress).toHaveBeenCalledTimes(2);
    } finally {
      vi.useRealTimers();
    }
  });

  it('cancels a book-pipeline job and invalidates its progress', async () => {
    cancelBookPipelineJob.mockResolvedValue({
      generation_job_id: 'job-1',
      version_id: 'version-1',
      scope: 'book_pipeline',
      status: 'running',
      attempt_count: 1,
      pause_after_chapter_analysis: false,
      reused_existing_job: false,
    });
    const queryClient = createTestQueryClient();
    const invalidate = vi
      .spyOn(queryClient, 'invalidateQueries')
      .mockResolvedValue(undefined);
    const { result } = renderHookWithProviders(
      () => useBookPipelineMutations(),
      { queryClient },
    );

    await result.current.cancel.mutateAsync('job-1');

    expect(cancelBookPipelineJob).toHaveBeenCalledWith(
      'job-1',
      expect.anything(),
    );
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: queryKeys.education.bookPipelineJobProgress('job-1'),
    });
  });
});
