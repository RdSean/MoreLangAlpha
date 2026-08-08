import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import EducationPage from '../EducationPage';

const state = vi.hoisted(() => ({
  member: null as { user_id: string; name: string; role: 'parent' | 'student' } | null,
  members: [] as Array<{ user_id: string; name: string; role: 'parent' | 'student' }>,
  tasks: [] as Array<Record<string, unknown>>,
  create: vi.fn(),
  submit: vi.fn(),
  review: vi.fn(),
  cancel: vi.fn(),
  upload: vi.fn(),
  membersEnabled: vi.fn(),
}));

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ member: state.member }),
}));

vi.mock('../api', () => ({
  uploadEducationAsset: state.upload,
}));

vi.mock('../queries', () => ({
  useEducationTasks: () => ({ data: state.tasks, isLoading: false }),
  useEducationMembers: (enabled: boolean) => {
    state.membersEnabled(enabled);
    return { data: state.members };
  },
  useEducationTaskMutations: () => ({
    create: { mutateAsync: state.create, isPending: false },
    submit: { mutateAsync: state.submit, isPending: false },
    review: { mutateAsync: state.review, isPending: false },
    cancel: { mutateAsync: state.cancel, isPending: false },
  }),
}));

const task = (status: 'open' | 'submitted' | 'revision_requested' | 'completed' | 'cancelled') => ({
  task_id: 'task-1',
  task_rule_id: 'rule-1',
  household_id: 'household-1',
  assigned_student_id: 'student-1',
  occurrence_date: '2026-08-09',
  due_at: '2026-08-10T01:00:00.000Z',
  title: '读书笔记',
  description: '记录三个发现。',
  status,
});

beforeEach(() => {
  state.member = null;
  state.members = [];
  state.tasks = [];
  state.create.mockReset().mockResolvedValue(undefined);
  state.submit.mockReset().mockResolvedValue(undefined);
  state.review.mockReset().mockResolvedValue(undefined);
  state.cancel.mockReset().mockResolvedValue(undefined);
  state.upload.mockReset().mockResolvedValue({ asset_id: 'asset-1' });
  state.membersEnabled.mockReset();
  vi.stubGlobal('crypto', { randomUUID: () => 'submission-idempotency-key' });
});

describe('EducationPage', () => {
  it('lets a parent create a task for a household student', async () => {
    state.member = { user_id: 'parent-1', name: '家长', role: 'parent' };
    state.members = [{ user_id: 'student-1', name: '学生', role: 'student' }];
    state.tasks = [task('submitted')];

    render(<EducationPage />);

    expect(screen.getByRole('heading', { name: '家庭作业' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '反馈' })).toBeInTheDocument();
    expect(state.membersEnabled).toHaveBeenCalledWith(true);

    fireEvent.click(screen.getByRole('button', { name: '创建作业' }));
    fireEvent.change(screen.getByLabelText('学生'), { target: { value: 'student-1' } });
    fireEvent.change(screen.getByLabelText('标题'), { target: { value: '新的阅读任务' } });
    fireEvent.change(screen.getByLabelText('截止时间'), { target: { value: '2026-08-10T10:00' } });
    fireEvent.click(screen.getByRole('button', { name: '创建作业' }));

    await waitFor(() => expect(state.create).toHaveBeenCalledWith(expect.objectContaining({
      assigned_student_id: 'student-1',
      title: '新的阅读任务',
      frequency: 'once',
      material_asset_ids: [],
    })));
  });

  it('sends text-only parent feedback for a submitted task', async () => {
    state.member = { user_id: 'parent-1', name: '家长', role: 'parent' };
    state.tasks = [task('submitted')];

    render(<EducationPage />);

    fireEvent.click(screen.getByRole('button', { name: '反馈' }));
    fireEvent.change(screen.getByPlaceholderText('写下修改建议或完成反馈'), { target: { value: '请补充第二段。' } });
    fireEvent.click(screen.getByRole('button', { name: '请求修改' }));

    await waitFor(() => expect(state.review).toHaveBeenCalledWith({
      taskId: 'task-1',
      decision: 'revision_requested',
      feedbackText: '请补充第二段。',
    }));
  });

  it('limits students to submission and resubmission actions', async () => {
    state.member = { user_id: 'student-1', name: '学生', role: 'student' };
    state.tasks = [task('revision_requested')];

    render(<EducationPage />);

    expect(screen.getByRole('heading', { name: '我的作业' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '创建作业' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '反馈' })).not.toBeInTheDocument();
    expect(state.membersEnabled).toHaveBeenCalledWith(false);

    fireEvent.click(screen.getByRole('button', { name: '提交作业' }));
    fireEvent.change(screen.getByPlaceholderText('写下完成情况'), { target: { value: '已根据反馈修改。' } });
    const attachment = new File(['完成内容'], 'homework.pdf', { type: 'application/pdf' });
    fireEvent.change(screen.getByLabelText('附件'), { target: { files: [attachment] } });
    fireEvent.click(screen.getByRole('button', { name: '提交' }));

    await waitFor(() => expect(state.upload).toHaveBeenCalledWith(attachment));
    await waitFor(() => expect(state.submit).toHaveBeenCalledWith({
      taskId: 'task-1',
      submission_text: '已根据反馈修改。',
      idempotency_key: 'submission-idempotency-key',
      asset_ids: ['asset-1'],
    }));
  });
});
