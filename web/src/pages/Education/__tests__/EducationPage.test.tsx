import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import EducationPage from '../EducationPage';

const state = vi.hoisted(() => ({
  member: null as { user_id: string; name: string; role: 'parent' | 'student' } | null,
  members: [] as Array<{ user_id: string; name: string; role: 'parent' | 'student'; grade_code?: string | null }>,
  tasks: [] as Array<Record<string, unknown>>,
  create: vi.fn(),
  checkIn: vi.fn(),
  appendRevision: vi.fn(),
  review: vi.fn(),
  cancel: vi.fn(),
  upload: vi.fn(),
  membersEnabled: vi.fn(),
  dictionaries: {
    subjects: [
      { code: 'chinese', name: '语文', color: '#D95D39', sort_order: 1, homework_types: [{ code: 'read', name: '阅读', sort_order: 1 }] },
      { code: 'math', name: '数学', color: '#277DA1', sort_order: 2, homework_types: [{ code: 'practice', name: '练习', sort_order: 1 }] },
    ],
    grade_levels: [
      { code: 'g4', name: '四年级', stage: 'primary', sort_order: 4 },
    ],
    practice_sources: [
      { code: 'schoolwork', name: '校内作业', sort_order: 1 },
      { code: 'homework', name: '校外作业', sort_order: 2 },
    ],
  } as Record<string, unknown> | undefined,
}));

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ member: state.member }),
}));

vi.mock('../api', () => ({
  uploadEducationAsset: state.upload,
}));

vi.mock('../queries', () => ({
  useEducationTasks: () => ({ data: state.tasks, isLoading: false }),
  useEducationHomeworkDictionaries: () => ({ data: state.dictionaries, isLoading: !state.dictionaries }),
  useEducationMembers: (enabled: boolean) => {
    state.membersEnabled(enabled);
    return { data: state.members };
  },
  useLearningAssignments: () => ({ data: [], isLoading: false }),
  useEducationTaskMutations: () => ({
    create: { mutateAsync: state.create, isPending: false },
    checkIn: { mutateAsync: state.checkIn, isPending: false },
    appendRevision: { mutateAsync: state.appendRevision, isPending: false },
    review: { mutateAsync: state.review, isPending: false },
    cancel: { mutateAsync: state.cancel, isPending: false },
  }),
}));

const task = (status: 'open' | 'completed' | 'cancelled') => ({
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
  state.checkIn.mockReset().mockResolvedValue(undefined);
  state.appendRevision.mockReset().mockResolvedValue(undefined);
  state.review.mockReset().mockResolvedValue(undefined);
  state.cancel.mockReset().mockResolvedValue(undefined);
  state.upload.mockReset().mockResolvedValue({ asset_id: 'asset-1' });
  state.membersEnabled.mockReset();
  state.dictionaries = {
    subjects: [
      { code: 'chinese', name: '语文', color: '#D95D39', sort_order: 1, homework_types: [{ code: 'read', name: '阅读', sort_order: 1 }] },
      { code: 'math', name: '数学', color: '#277DA1', sort_order: 2, homework_types: [{ code: 'practice', name: '练习', sort_order: 1 }] },
    ],
    grade_levels: [
      { code: 'g4', name: '四年级', stage: 'primary', sort_order: 4 },
    ],
    practice_sources: [
      { code: 'schoolwork', name: '校内作业', sort_order: 1 },
      { code: 'homework', name: '校外作业', sort_order: 2 },
    ],
  };
  vi.stubGlobal('crypto', { randomUUID: () => 'submission-idempotency-key' });
});

describe('EducationPage', () => {
  it('creates a classified practice task with its required source', async () => {
    state.member = { user_id: 'parent-1', name: '家长', role: 'parent' };
    state.members = [{ user_id: 'student-1', name: '学生', role: 'student', grade_code: 'g4' }];
    state.tasks = [task('completed')];

    render(<MemoryRouter><EducationPage /></MemoryRouter>);

    expect(screen.getByRole('heading', { name: '家庭作业' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '反馈' })).toBeInTheDocument();
    expect(state.membersEnabled).toHaveBeenCalledWith(true);

    fireEvent.click(screen.getByRole('button', { name: '创建作业' }));
    fireEvent.change(screen.getByLabelText('学生'), { target: { value: 'student-1' } });
    fireEvent.change(screen.getByLabelText('科目'), { target: { value: 'math' } });
    fireEvent.change(screen.getByLabelText('作业类型'), { target: { value: 'practice' } });
    fireEvent.change(screen.getByLabelText('练习来源'), { target: { value: 'schoolwork' } });
    fireEvent.change(screen.getByLabelText('标题'), { target: { value: '新的练习任务' } });
    fireEvent.change(screen.getByLabelText('截止时间'), { target: { value: '2026-08-10T10:00' } });
    fireEvent.click(screen.getByRole('button', { name: '创建作业' }));

    await waitFor(() => expect(state.create).toHaveBeenCalledWith(expect.objectContaining({
      assigned_student_id: 'student-1',
      subject_code: 'math',
      type_code: 'practice',
      practice_source_code: 'schoolwork',
      frequency: 'once',
      material_asset_ids: [],
    })));
  });

  it('blocks creation and guides the parent when the selected student has no grade', () => {
    state.member = { user_id: 'parent-1', name: '家长', role: 'parent' };
    state.members = [{ user_id: 'student-1', name: '学生', role: 'student', grade_code: null }];

    render(<MemoryRouter><EducationPage /></MemoryRouter>);

    fireEvent.click(screen.getByRole('button', { name: '创建作业' }));
    fireEvent.change(screen.getByLabelText('学生'), { target: { value: 'student-1' } });

    expect(screen.getByText('当前年级：未设置年级')).toBeInTheDocument();
    expect(screen.getByText('请先在‘设置 > 家庭账户’中为该学生设置当前年级。')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: '创建作业' }).at(-1)).toBeDisabled();
  });

  it('waits for dictionaries instead of treating an existing student grade as unset', () => {
    state.member = { user_id: 'parent-1', name: '家长', role: 'parent' };
    state.members = [{ user_id: 'student-1', name: '学生', role: 'student', grade_code: 'g4' }];
    state.dictionaries = undefined;

    render(<MemoryRouter><EducationPage /></MemoryRouter>);

    fireEvent.click(screen.getByRole('button', { name: '创建作业' }));
    fireEvent.change(screen.getByLabelText('学生'), { target: { value: 'student-1' } });

    expect(screen.getByText('正在加载作业字典…')).toBeInTheDocument();
    expect(screen.queryByText('当前年级：未设置年级')).not.toBeInTheDocument();
    expect(screen.queryByText('请先在‘设置 > 家庭账户’中为该学生设置当前年级。')).not.toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: '创建作业' }).at(-1)).toBeDisabled();
  });

  it('sends allowed text-only parent feedback for a completed task', async () => {
    state.member = { user_id: 'parent-1', name: '家长', role: 'parent' };
    state.tasks = [task('completed')];

    render(<MemoryRouter><EducationPage /></MemoryRouter>);

    fireEvent.click(screen.getByRole('button', { name: '反馈' }));
    fireEvent.change(screen.getByPlaceholderText('写下修改建议或完成反馈'), { target: { value: '请补充第二段。' } });
    fireEvent.click(screen.getByRole('button', { name: '请求修改' }));

    await waitFor(() => expect(state.review).toHaveBeenCalledWith({
      taskId: 'task-1',
      decision: 'revision_requested',
      feedbackText: '请补充第二段。',
    }));
  });

  it('lets a student check in an open task without text or attachments', async () => {
    state.member = { user_id: 'student-1', name: '学生', role: 'student' };
    state.tasks = [task('open')];

    render(<MemoryRouter><EducationPage /></MemoryRouter>);

    fireEvent.click(screen.getByRole('button', { name: '完成打卡' }));

    await waitFor(() => expect(state.checkIn).toHaveBeenCalledWith({
      taskId: 'task-1',
      submission_text: '',
      idempotency_key: 'submission-idempotency-key',
      asset_ids: [],
    }));
  });

  it('lets a student append a meaningful revision after completion', async () => {
    state.member = { user_id: 'student-1', name: '学生', role: 'student' };
    state.tasks = [task('completed')];

    render(<MemoryRouter><EducationPage /></MemoryRouter>);

    fireEvent.click(screen.getByRole('button', { name: '补充提交' }));
    fireEvent.change(screen.getByPlaceholderText('补充说明或修改内容'), { target: { value: '已补充内容。' } });
    fireEvent.click(screen.getByRole('button', { name: '提交补充' }));

    await waitFor(() => expect(state.appendRevision).toHaveBeenCalledWith({
      taskId: 'task-1',
      submission_text: '已补充内容。',
      idempotency_key: 'submission-idempotency-key',
      asset_ids: [],
    }));
  });
});
