import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import EducationPage, { CreateHomeworkPage, ParentCreateDialog } from '../EducationPage';
import type { EducationHomeworkDictionaries } from '../types';

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
  deleteAsset: vi.fn(),
  membersEnabled: vi.fn(),
  sound: vi.fn(),
  calendarError: false,
  dictionaries: {
    timezone: 'Asia/Tokyo',
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
  } as EducationHomeworkDictionaries | undefined,
}));

function renderCreateHomeworkPage() {
  return render(<MemoryRouter><CreateHomeworkPage /></MemoryRouter>);
}

function renderCreateHomeworkDialog() {
  return render(
    <MemoryRouter>
      <ParentCreateDialog
        students={state.members}
        dictionaries={state.dictionaries}
        onSubmit={state.create}
        isPending={false}
      />
    </MemoryRouter>,
  );
}

function choose(label: string) {
  fireEvent.click(screen.getByRole('button', { name: label }));
}

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ member: state.member }),
}));

vi.mock('../api', () => ({
  uploadEducationAsset: state.upload,
  deleteEducationAsset: state.deleteAsset,
}));

vi.mock('../completionSound', () => ({ createCompletionSound: () => ({ play: state.sound, close: vi.fn() }) }));
vi.mock('../calendarQueries', () => ({ useFamilyCalendarEvents: () => ({ data: { events: [] }, isLoading: false, isError: false }) }));

vi.mock('../queries', () => ({
  useEducationTaskDetail: () => ({ data: { parent_materials: [], submissions: [{ submission_id: 'submission-1', task_id: 'task-1', sequence: 1, submission_text: '已经阅读第三章。', assets: [], reviews: [] }] }, isLoading: false }),
  useEducationTaskCalendar: (params: { start_date: string; end_date: string; student_id?: string } | undefined) => ({
    isLoading: false,
    isError: state.calendarError,
    refetch: vi.fn(),
    data: params && !state.calendarError ? {
      stats: { total_points: state.tasks.filter(t => t.status === 'completed' && (!params.student_id || t.assigned_student_id === params.student_id)).length },
      days: Array.from(new Set(state.tasks.map(t => t.occurrence_date as string))).map(date => {
        const tasks = state.tasks.filter(t => t.occurrence_date === date && t.status !== 'cancelled' && (!params.student_id || t.assigned_student_id === params.student_id));
        return { date, tasks, task_count: tasks.length, completed_count: tasks.filter(t => t.status === 'completed').length, overdue_count: 0 };
      }),
    } : undefined,
  }),
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

afterEach(() => vi.useRealTimers());

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2026-08-09T06:00:00Z'));
  state.sound.mockReset();
  state.calendarError = false;
  state.member = null;
  state.members = [];
  state.tasks = [];
  state.create.mockReset().mockResolvedValue(undefined);
  state.checkIn.mockReset().mockResolvedValue(undefined);
  state.appendRevision.mockReset().mockResolvedValue(undefined);
  state.review.mockReset().mockResolvedValue(undefined);
  state.cancel.mockReset().mockResolvedValue(undefined);
  state.upload.mockReset().mockResolvedValue({ asset_id: 'asset-1' });
  state.deleteAsset.mockReset().mockResolvedValue(undefined);
  state.membersEnabled.mockReset();
  state.dictionaries = {
    timezone: 'Asia/Tokyo',
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
  it('prefills the drawer from any double-clicked date and creates in the household timezone', async () => {
    state.member = { user_id: 'parent-1', name: '家长', role: 'parent' };
    state.members = [{ user_id: 'student-1', name: '学生', role: 'student', grade_code: 'g4' }];
    render(<MemoryRouter><EducationPage /></MemoryRouter>);
    fireEvent.doubleClick(screen.getByRole('button', { name: /2026-08-23/ }));
    const drawer = screen.getByRole('dialog');
    expect(within(drawer).getByLabelText('截止时间')).toHaveValue('2026-08-23T20:00');
    fireEvent.click(within(drawer).getByRole('button', { name: '创建作业' }));
    await waitFor(() => expect(state.create).toHaveBeenCalledWith(expect.objectContaining({ due_at: '2026-08-23T11:00:00.000Z', frequency: 'once' })));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /2026-08-01/ }));
    fireEvent.click(screen.getByRole('button', { name: '创建作业' }));
    expect(screen.getByLabelText('截止时间')).toHaveValue('2026-08-01T20:00');
  });
  it('creates a classified practice task with its required source', async () => {
    state.member = { user_id: 'parent-1', name: '家长', role: 'parent' };
    state.members = [{ user_id: 'student-1', name: '学生', role: 'student', grade_code: 'g4' }];
    state.tasks = [task('completed')];

    const educationPage = render(<MemoryRouter><EducationPage /></MemoryRouter>);

    expect(screen.getByRole('heading', { name: '家庭作业' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '反馈' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '创建作业' })).toBeVisible();
    expect(screen.queryByRole('link', { name: '教材加工' })).not.toBeInTheDocument();
    educationPage.unmount();

    renderCreateHomeworkPage();
    expect(state.membersEnabled).toHaveBeenCalledWith(true);

    choose('数学');
    choose('练习');
    choose('校内作业');
    fireEvent.change(screen.getByLabelText('说明'), { target: { value: '新的练习任务' } });
    fireEvent.change(screen.getByLabelText('截止时间'), { target: { value: '2026-08-10T10:00' } });
    fireEvent.click(screen.getByRole('button', { name: '创建作业' }));

    await waitFor(() => expect(state.create).toHaveBeenCalledWith(expect.objectContaining({
      assigned_student_id: 'student-1',
      subject_code: 'math',
      type_code: 'practice',
      practice_source_code: 'schoolwork',
      frequency: 'once',
      material_asset_ids: [],
      idempotency_key: 'submission-idempotency-key',
    })));
  });

  it('interprets a deadline as household wall-clock time instead of browser local time', async () => {
    state.member = { user_id: 'parent-1', name: '家长', role: 'parent' };
    state.members = [{ user_id: 'student-1', name: '学生', role: 'student', grade_code: 'g4' }];
    state.dictionaries = { ...state.dictionaries!, timezone: 'America/New_York' };

    renderCreateHomeworkPage();

    choose('语文');
    choose('阅读');
    fireEvent.change(screen.getByLabelText('说明'), { target: { value: '家庭时区作业' } });
    fireEvent.change(screen.getByLabelText('截止时间'), { target: { value: '2026-08-10T10:00' } });
    expect(screen.getByText('家庭时区：America/New_York')).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('button', { name: '创建作业' }).at(-1)!);

    await waitFor(() => expect(state.create).toHaveBeenCalledWith(expect.objectContaining({
      due_at: '2026-08-10T14:00:00.000Z',
    })));
  });

  it('renders task deadlines in the household timezone instead of the browser timezone', () => {
    state.member = { user_id: 'student-1', name: '学生', role: 'student' };
    state.tasks = [task('open')];
    state.dictionaries = { ...state.dictionaries!, timezone: 'America/New_York' };
    const expected = new Intl.DateTimeFormat(undefined, {
      timeZone: 'America/New_York', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    }).format(new Date('2026-08-10T01:00:00.000Z'));

    render(<MemoryRouter><EducationPage /></MemoryRouter>);

    expect(screen.getByText(`截止 ${expected}`)).toBeInTheDocument();
  });

  it('creates a weekly task with the selected weekdays and all parent materials', async () => {
    state.member = { user_id: 'parent-1', name: '家长', role: 'parent' };
    state.members = [{ user_id: 'student-1', name: '学生', role: 'student', grade_code: 'g4' }];
    state.upload
      .mockResolvedValueOnce({ asset_id: 'asset-1' })
      .mockResolvedValueOnce({ asset_id: 'asset-2' });

    renderCreateHomeworkPage();

    expect(screen.getByText('当前年级：四年级')).toBeInTheDocument();
    choose('语文');
    choose('阅读');
    fireEvent.change(screen.getByLabelText('说明'), { target: { value: '每周阅读' } });
    fireEvent.change(screen.getByLabelText('截止时间'), { target: { value: '2026-08-10T10:00' } });
    choose('每周指定日期');
    fireEvent.click(screen.getByRole('checkbox', { name: '周一' }));
    fireEvent.click(screen.getByRole('checkbox', { name: '周三' }));
    const first = new File(['first'], 'first.jpg', { type: 'image/jpeg' });
    const second = new File(['second'], 'second.pdf', { type: 'application/pdf' });
    fireEvent.change(screen.getByLabelText('材料附件'), { target: { files: [first, second] } });
    fireEvent.click(screen.getByRole('button', { name: '创建作业' }));

    await waitFor(() => expect(state.create).toHaveBeenCalledWith(expect.objectContaining({
      assigned_student_id: 'student-1',
      subject_code: 'chinese',
      type_code: 'read',
      frequency: 'weekly',
      weekdays: [1, 3],
      material_asset_ids: ['asset-1', 'asset-2'],
      idempotency_key: 'submission-idempotency-key',
    })));
    expect(state.upload).toHaveBeenCalledWith(first, { stagingKey: 'submission-idempotency-key', stagingSlot: 0 });
    expect(state.upload).toHaveBeenCalledWith(second, { stagingKey: 'submission-idempotency-key', stagingSlot: 1 });
  });

  it('defers weekly date validation to the household timezone and shows its server error', async () => {
    state.member = { user_id: 'parent-1', name: '家长', role: 'parent' };
    state.members = [{ user_id: 'student-1', name: '学生', role: 'student', grade_code: 'g4' }];
    state.create.mockRejectedValue({ response: { data: { detail: 'No scheduled homework dates before the deadline' } } });

    renderCreateHomeworkPage();

    choose('语文');
    choose('阅读');
    fireEvent.change(screen.getByLabelText('说明'), { target: { value: '不匹配的每周阅读' } });
    fireEvent.change(screen.getByLabelText('截止时间'), { target: { value: '2026-08-09T10:00' } });
    choose('每周指定日期');
    fireEvent.click(screen.getByRole('checkbox', { name: '周一' }));
    expect(screen.getByLabelText('截止时间')).toHaveValue('2026-08-09T10:00');
    fireEvent.click(screen.getByRole('button', { name: '创建作业' }));

    await waitFor(() => expect(state.create).toHaveBeenCalled());
    expect(await screen.findByRole('alert')).toHaveTextContent('No scheduled homework dates before the deadline');
  });

  it('reuses staged parent materials and its creation key when a create response is lost', async () => {
    state.member = { user_id: 'parent-1', name: '家长', role: 'parent' };
    state.members = [{ user_id: 'student-1', name: '学生', role: 'student', grade_code: 'g4' }];
    state.create.mockRejectedValueOnce(new Error('network unavailable')).mockResolvedValueOnce(undefined);
    const attachment = new File(['first'], 'first.pdf', { type: 'application/pdf' });

    renderCreateHomeworkPage();

    choose('语文');
    choose('阅读');
    fireEvent.change(screen.getByLabelText('说明'), { target: { value: '可重试作业' } });
    fireEvent.change(screen.getByLabelText('截止时间'), { target: { value: '2026-08-10T10:00' } });
    fireEvent.change(screen.getByLabelText('材料附件'), { target: { files: [attachment] } });
    fireEvent.click(screen.getAllByRole('button', { name: '创建作业' }).at(-1)!);
    expect(await screen.findByRole('alert')).toHaveTextContent('network unavailable');
    fireEvent.click(screen.getAllByRole('button', { name: '创建作业' }).at(-1)!);

    await waitFor(() => expect(state.create).toHaveBeenCalledTimes(2));
    expect(state.upload).toHaveBeenCalledTimes(1);
    expect(state.create.mock.calls[1][0]).toEqual(state.create.mock.calls[0][0]);
  });

  it('cleans up parent materials when a failed create dialog is closed', async () => {
    state.member = { user_id: 'parent-1', name: '家长', role: 'parent' };
    state.members = [{ user_id: 'student-1', name: '学生', role: 'student', grade_code: 'g4' }];
    state.create.mockRejectedValueOnce(new Error('network unavailable'));
    const attachment = new File(['first'], 'first.pdf', { type: 'application/pdf' });

    renderCreateHomeworkDialog();

    fireEvent.click(screen.getByRole('button', { name: '创建作业' }));
    choose('语文');
    choose('阅读');
    fireEvent.change(screen.getByLabelText('说明'), { target: { value: '关闭后回收' } });
    fireEvent.change(screen.getByLabelText('截止时间'), { target: { value: '2026-08-10T10:00' } });
    fireEvent.change(screen.getByLabelText('材料附件'), { target: { files: [attachment] } });
    fireEvent.click(screen.getAllByRole('button', { name: '创建作业' }).at(-1)!);
    expect(await screen.findByRole('alert')).toHaveTextContent('network unavailable');
    fireEvent.keyDown(document, { key: 'Escape' });

    await waitFor(() => expect(state.deleteAsset).toHaveBeenCalledWith('asset-1'));
  });

  it('keeps a create dialog and staged attachments open while its request is pending', async () => {
    state.member = { user_id: 'parent-1', name: '家长', role: 'parent' };
    state.members = [{ user_id: 'student-1', name: '学生', role: 'student', grade_code: 'g4' }];
    let resolveCreate: (() => void) | undefined;
    state.create.mockImplementationOnce(() => new Promise<void>((resolve) => { resolveCreate = resolve; }));
    const attachment = new File(['first'], 'first.pdf', { type: 'application/pdf' });

    renderCreateHomeworkDialog();

    fireEvent.click(screen.getByRole('button', { name: '创建作业' }));
    choose('语文');
    choose('阅读');
    fireEvent.change(screen.getByLabelText('说明'), { target: { value: '处理中作业' } });
    fireEvent.change(screen.getByLabelText('截止时间'), { target: { value: '2026-08-10T10:00' } });
    fireEvent.change(screen.getByLabelText('材料附件'), { target: { files: [attachment] } });
    fireEvent.click(screen.getAllByRole('button', { name: '创建作业' }).at(-1)!);
    await waitFor(() => expect(state.create).toHaveBeenCalledOnce());
    fireEvent.keyDown(document, { key: 'Escape' });

    expect(screen.getByRole('heading', { name: '创建作业' })).toBeInTheDocument();
    expect(state.deleteAsset).not.toHaveBeenCalled();
    resolveCreate?.();
    await waitFor(() => expect(screen.queryByRole('heading', { name: '创建作业' })).not.toBeInTheDocument());
  });

  it('rejects more than twenty parent materials before starting uploads', async () => {
    state.member = { user_id: 'parent-1', name: '家长', role: 'parent' };
    state.members = [{ user_id: 'student-1', name: '学生', role: 'student', grade_code: 'g4' }];

    renderCreateHomeworkPage();

    choose('语文');
    choose('阅读');
    fireEvent.change(screen.getByLabelText('说明'), { target: { value: '附件过多' } });
    fireEvent.change(screen.getByLabelText('截止时间'), { target: { value: '2026-08-10T10:00' } });
    fireEvent.change(screen.getByLabelText('材料附件'), {
      target: { files: Array.from({ length: 21 }, (_, index) => new File(['x'], `${index}.jpg`, { type: 'image/jpeg' })) },
    });
    fireEvent.click(screen.getByRole('button', { name: '创建作业' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('最多可上传 20 份附件。');
    expect(state.upload).not.toHaveBeenCalled();
    expect(state.create).not.toHaveBeenCalled();
  });

  it('blocks creation and guides the parent when the selected student has no grade', () => {
    state.member = { user_id: 'parent-1', name: '家长', role: 'parent' };
    state.members = [{ user_id: 'student-1', name: '学生', role: 'student', grade_code: null }];

    renderCreateHomeworkPage();

    expect(screen.getByText('当前年级：未设置年级')).toBeInTheDocument();
    expect(screen.getByText('请先在‘设置 > 家庭账户’中为该学生设置当前年级。')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: '创建作业' }).at(-1)).toBeDisabled();
  });

  it('waits for dictionaries instead of treating an existing student grade as unset', () => {
    state.member = { user_id: 'parent-1', name: '家长', role: 'parent' };
    state.members = [{ user_id: 'student-1', name: '学生', role: 'student', grade_code: 'g4' }];
    state.dictionaries = undefined;

    renderCreateHomeworkPage();
    choose('学生');

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
    expect(screen.getByRole('heading', { name: '完成打卡' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '确认打卡' }));

    await waitFor(() => expect(state.checkIn).toHaveBeenCalledWith({
      taskId: 'task-1',
      submission_text: '',
      idempotency_key: 'submission-idempotency-key',
      asset_ids: [],
    }));
  });

  it('sends optional first check-in text and multiple attachments', async () => {
    state.member = { user_id: 'student-1', name: '学生', role: 'student' };
    state.tasks = [task('open')];
    state.upload
      .mockResolvedValueOnce({ asset_id: 'asset-1' })
      .mockResolvedValueOnce({ asset_id: 'asset-2' });
    const first = new File(['first'], 'first.jpg', { type: 'image/jpeg' });
    const second = new File(['second'], 'second.pdf', { type: 'application/pdf' });

    render(<MemoryRouter><EducationPage /></MemoryRouter>);

    fireEvent.click(screen.getByRole('button', { name: '完成打卡' }));
    fireEvent.change(screen.getByPlaceholderText('可选的完成说明'), { target: { value: '已经读完。' } });
    fireEvent.change(screen.getByLabelText('附件'), { target: { files: [first, second] } });
    fireEvent.click(screen.getByRole('button', { name: '确认打卡' }));

    await waitFor(() => expect(state.checkIn).toHaveBeenCalledWith({
      taskId: 'task-1',
      submission_text: '已经读完。',
      idempotency_key: 'submission-idempotency-key',
      asset_ids: ['asset-1', 'asset-2'],
    }));
  });

  it('reuses staged student attachments when a check-in response is lost', async () => {
    state.member = { user_id: 'student-1', name: '学生', role: 'student' };
    state.tasks = [task('open')];
    state.checkIn.mockRejectedValueOnce(new Error('network unavailable')).mockResolvedValueOnce(undefined);
    const attachment = new File(['first'], 'first.pdf', { type: 'application/pdf' });

    render(<MemoryRouter><EducationPage /></MemoryRouter>);

    fireEvent.click(screen.getByRole('button', { name: '完成打卡' }));
    fireEvent.change(screen.getByLabelText('附件'), { target: { files: [attachment] } });
    fireEvent.click(screen.getByRole('button', { name: '确认打卡' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('network unavailable');
    fireEvent.click(screen.getByRole('button', { name: '确认打卡' }));

    await waitFor(() => expect(state.checkIn).toHaveBeenCalledTimes(2));
    expect(state.upload).toHaveBeenCalledTimes(1);
    expect(state.checkIn.mock.calls[1][0]).toEqual(state.checkIn.mock.calls[0][0]);
  });

  it('cleans up staged student attachments after a definite check-in rejection', async () => {
    state.member = { user_id: 'student-1', name: '学生', role: 'student' };
    state.tasks = [task('open')];
    state.checkIn.mockRejectedValue({ response: { status: 400, data: { detail: '该作业已取消。' } } });
    const attachment = new File(['first'], 'first.pdf', { type: 'application/pdf' });

    render(<MemoryRouter><EducationPage /></MemoryRouter>);

    fireEvent.click(screen.getByRole('button', { name: '完成打卡' }));
    fireEvent.change(screen.getByLabelText('附件'), { target: { files: [attachment] } });
    fireEvent.click(screen.getByRole('button', { name: '确认打卡' }));

    await waitFor(() => expect(state.deleteAsset).toHaveBeenCalledWith('asset-1'));
  });

  it('retries staged attachment cleanup after a failed check-in closes', async () => {
    state.member = { user_id: 'student-1', name: '学生', role: 'student' };
    state.tasks = [task('open')];
    state.checkIn.mockRejectedValue({ response: { status: 400, data: { detail: '该作业已取消。' } } });
    state.deleteAsset.mockRejectedValueOnce(new Error('storage unavailable')).mockResolvedValueOnce(undefined);
    const attachment = new File(['first'], 'first.pdf', { type: 'application/pdf' });

    render(<MemoryRouter><EducationPage /></MemoryRouter>);

    fireEvent.click(screen.getByRole('button', { name: '完成打卡' }));
    fireEvent.change(screen.getByLabelText('附件'), { target: { files: [attachment] } });
    fireEvent.click(screen.getByRole('button', { name: '确认打卡' }));
    await waitFor(() => expect(state.deleteAsset).toHaveBeenCalledTimes(1));
    fireEvent.keyDown(document, { key: 'Escape' });

    await waitFor(() => expect(state.deleteAsset).toHaveBeenCalledTimes(2));
  });

  it('keeps a check-in dialog and staged attachments open while its request is pending', async () => {
    state.member = { user_id: 'student-1', name: '学生', role: 'student' };
    state.tasks = [task('open')];
    let resolveCheckIn: (() => void) | undefined;
    state.checkIn.mockImplementationOnce(() => new Promise<void>((resolve) => { resolveCheckIn = resolve; }));
    const attachment = new File(['first'], 'first.pdf', { type: 'application/pdf' });

    render(<MemoryRouter><EducationPage /></MemoryRouter>);

    fireEvent.click(screen.getByRole('button', { name: '完成打卡' }));
    fireEvent.change(screen.getByLabelText('附件'), { target: { files: [attachment] } });
    fireEvent.click(screen.getByRole('button', { name: '确认打卡' }));
    await waitFor(() => expect(state.checkIn).toHaveBeenCalledOnce());
    fireEvent.keyDown(document, { key: 'Escape' });

    expect(screen.getByRole('heading', { name: '完成打卡' })).toBeInTheDocument();
    expect(state.deleteAsset).not.toHaveBeenCalled();
    resolveCheckIn?.();
    await waitFor(() => expect(screen.queryByRole('heading', { name: '完成打卡' })).not.toBeInTheDocument());
  });

  it('rejects more than twenty first check-in attachments before starting uploads', async () => {
    state.member = { user_id: 'student-1', name: '学生', role: 'student' };
    state.tasks = [task('open')];

    render(<MemoryRouter><EducationPage /></MemoryRouter>);

    fireEvent.click(screen.getByRole('button', { name: '完成打卡' }));
    fireEvent.change(screen.getByLabelText('附件'), {
      target: { files: Array.from({ length: 21 }, (_, index) => new File(['x'], `${index}.jpg`, { type: 'image/jpeg' })) },
    });
    fireEvent.click(screen.getByRole('button', { name: '确认打卡' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('最多可上传 20 份附件。');
    expect(state.upload).not.toHaveBeenCalled();
    expect(state.checkIn).not.toHaveBeenCalled();
  });

  it('rejects more than twenty revision attachments before starting uploads', async () => {
    state.member = { user_id: 'student-1', name: '学生', role: 'student' };
    state.tasks = [task('completed')];

    render(<MemoryRouter><EducationPage /></MemoryRouter>);

    fireEvent.click(screen.getByRole('button', { name: '补充提交' }));
    fireEvent.change(screen.getByLabelText('附件'), {
      target: { files: Array.from({ length: 21 }, (_, index) => new File(['x'], `${index}.jpg`, { type: 'image/jpeg' })) },
    });
    fireEvent.click(screen.getByRole('button', { name: '提交补充' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('最多可上传 20 份附件。');
    expect(state.upload).not.toHaveBeenCalled();
    expect(state.appendRevision).not.toHaveBeenCalled();
  });

  it('shows the server detail when a homework mutation fails', async () => {
    state.member = { user_id: 'student-1', name: '学生', role: 'student' };
    state.tasks = [task('open')];
    state.checkIn.mockRejectedValue({ response: { data: { detail: '该作业已取消。' } } });

    render(<MemoryRouter><EducationPage /></MemoryRouter>);

    fireEvent.click(screen.getByRole('button', { name: '完成打卡' }));
    fireEvent.click(screen.getByRole('button', { name: '确认打卡' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('该作业已取消。');
  });

  it('shows cancellation errors instead of leaving a rejected mutation unhandled', async () => {
    state.member = { user_id: 'parent-1', name: '家长', role: 'parent' };
    state.tasks = [task('open')];
    state.cancel.mockRejectedValue({ response: { data: { detail: '作业已经完成，不能取消。' } } });

    render(<MemoryRouter><EducationPage /></MemoryRouter>);

    fireEvent.click(screen.getByRole('button', { name: '取消作业' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('作业已经完成，不能取消。');
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

  it('keeps a revision dialog and staged attachments open while its request is pending', async () => {
    state.member = { user_id: 'student-1', name: '学生', role: 'student' };
    state.tasks = [task('completed')];
    let resolveRevision: (() => void) | undefined;
    state.appendRevision.mockImplementationOnce(() => new Promise<void>((resolve) => { resolveRevision = resolve; }));
    const attachment = new File(['first'], 'first.pdf', { type: 'application/pdf' });

    render(<MemoryRouter><EducationPage /></MemoryRouter>);

    fireEvent.click(screen.getByRole('button', { name: '补充提交' }));
    fireEvent.change(screen.getByPlaceholderText('补充说明或修改内容'), { target: { value: '补充说明' } });
    fireEvent.change(screen.getByLabelText('附件'), { target: { files: [attachment] } });
    fireEvent.click(screen.getByRole('button', { name: '提交补充' }));
    await waitFor(() => expect(state.appendRevision).toHaveBeenCalledOnce());
    fireEvent.keyDown(document, { key: 'Escape' });

    expect(screen.getByRole('heading', { name: '补充提交' })).toBeInTheDocument();
    expect(state.deleteAsset).not.toHaveBeenCalled();
    resolveRevision?.();
    await waitFor(() => expect(screen.queryByRole('heading', { name: '补充提交' })).not.toBeInTheDocument());
  });
});


describe('calendar homework notebook', () => {
  it('keeps the three core subjects and hides empty optional subjects', () => {
    state.member = { user_id: 'student-1', name: '学生', role: 'student' };
    render(<MemoryRouter><EducationPage /></MemoryRouter>);
    for (const name of ['语文', '数学', '英语']) expect(screen.getByRole('heading', { name })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '科学' })).not.toBeInTheDocument();
    expect(screen.getAllByText('今日未布置')).toHaveLength(3);
  });

  it('selects a date and renders only its subject homework', () => {
    state.member = { user_id: 'student-1', name: '学生', role: 'student' };
    state.dictionaries!.subjects.push({ code: 'science', name: '科学', color: '', sort_order: 4, homework_types: [] });
    state.tasks = [{ ...task('open'), subject_code: 'chinese' }, { ...task('open'), task_id: 'task-2', occurrence_date: '2026-08-10', subject_code: 'science', title: '观察植物' }];
    render(<MemoryRouter><EducationPage /></MemoryRouter>);
    expect(screen.getByRole('heading', { name: '读书笔记' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /2026-08-10/ }));
    expect(screen.queryByRole('heading', { name: '读书笔记' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '科学' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '观察植物' })).toBeInTheDocument();
  });

  it('allows a parent check-in and plays sound only on success', async () => {
    state.member = { user_id: 'parent-1', name: '家长', role: 'parent' };
    state.tasks = [task('open')];
    state.checkIn.mockRejectedValueOnce(new Error('暂时无法提交'));
    render(<MemoryRouter><EducationPage /></MemoryRouter>);
    fireEvent.click(screen.getByRole('button', { name: '完成打卡' }));
    fireEvent.click(screen.getByRole('button', { name: '确认打卡' }));
    await screen.findByRole('alert');
    expect(state.sound).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '确认打卡' }));
    await waitFor(() => expect(state.sound).toHaveBeenCalledTimes(1));
  });

  it('shows persisted total points and filters by child', () => {
    state.member = { user_id: 'parent-1', name: '家长', role: 'parent' };
    state.members = [{ user_id: 'student-1', name: '小一', role: 'student' }, { user_id: 'student-2', name: '小二', role: 'student' }];
    state.tasks = [task('completed'), { ...task('completed'), task_id: 'task-2', assigned_student_id: 'student-2' }];
    render(<MemoryRouter><EducationPage /></MemoryRouter>);
    expect(screen.getByLabelText('累计积分')).toHaveTextContent('2');
    fireEvent.change(screen.getByLabelText('选择孩子'), { target: { value: 'student-1' } });
    expect(screen.getByLabelText('累计积分')).toHaveTextContent('1');
    expect(within(screen.getByRole('region', { name: '当天作业本' })).getAllByRole('heading', { name: '读书笔记' })).toHaveLength(1);
  });

  it('shows a retry error instead of an empty notebook on a failed calendar request', () => {
    state.calendarError = true;
    render(<MemoryRouter><EducationPage /></MemoryRouter>);
    expect(screen.getByRole('alert')).toHaveTextContent('作业日历加载失败');
    expect(screen.queryByText('今日未布置')).not.toBeInTheDocument();
  });
});


it('lets parents read the actual submission before writing feedback', () => {
  state.member = { user_id: 'parent-1', name: '家长', role: 'parent' };
  state.tasks = [task('completed')];
  render(<MemoryRouter><EducationPage /></MemoryRouter>);
  fireEvent.click(screen.getByRole('button', { name: '反馈' }));
  expect(screen.getByText('已经阅读第三章。')).toBeInTheDocument();
});
