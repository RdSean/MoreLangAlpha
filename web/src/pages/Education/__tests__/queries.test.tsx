import { beforeEach, describe, expect, it, vi } from 'vitest';
import { waitFor } from '@testing-library/react';
import { renderHookWithProviders } from '@/test/utils';
import * as educationApi from '../api';
import { useEducationTaskCalendar, useEducationTaskDetail } from '../queries';

vi.mock('../api', () => ({
  getEducationTaskCalendar: vi.fn(),
  getEducationTaskDetail: vi.fn(),
}));

const getEducationTaskCalendar = educationApi.getEducationTaskCalendar as unknown as ReturnType<typeof vi.fn>;
const getEducationTaskDetail = educationApi.getEducationTaskDetail as unknown as ReturnType<typeof vi.fn>;

describe('education queries', () => {
  beforeEach(() => {
    getEducationTaskCalendar.mockReset();
    getEducationTaskDetail.mockReset();
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
