import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useState } from 'react';
import { scrollMemory } from '@/lib/scrollMemory';
import i18n from '@/i18n';
import { BookGenerationForm } from '../components/BookGenerationForm';
import { BookReader } from '../components/BookReader';
import { BookAssignmentDialog } from '../components/BookAssignmentDialog';
import TextbookWorkbenchPage from '../TextbookWorkbenchPage';
import { processingJob } from './bookProcessingFixtures';
import type {
  BookAssignment,
  BookSourceSlice,
  BookStructure,
  EducationMember,
  KnowledgePointMaterial,
  TextbookWorkbench,
} from '../types';

const source: BookSourceSlice = {
  textbook_id: 'book-1',
  start_line: 10,
  end_line: 22,
  total_lines: 120,
  markdown: '# The World’s Game\n\nFootball is played around the world.',
};

const authState = vi.hoisted(() => ({ role: 'parent' as 'parent' | 'student' }));
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ member: { role: authState.role } }),
}));

vi.mock('../components/BookOriginalReader', () => ({
  BookOriginalReader: ({ startLine, restoredPage }: { startLine?: number; restoredPage?: number }) => <div data-testid="original-file">PDF start line {startLine}; page {restoredPage ?? 'automatic'}</div>,
}));

const emptyMaterial: KnowledgePointMaterial = {
  textbook_id: 'book-1',
  knowledge_point_id: 'kp-db-1',
  skill_kp_id: 'sports-global-game',
  material_available: false,
  markdown: null,
  generated_at: null,
  depth: null,
  requirements: null,
  content_sha256: null,
};

const readyMaterial: KnowledgePointMaterial = {
  ...emptyMaterial,
  material_available: true,
  markdown: '# 足球如何成为全球运动\n\n这是一份已经提交的讲义。',
  generated_at: '2026-10-02T06:00:00Z',
  depth: 'lesson',
  content_sha256: 'a'.repeat(64),
};

const pageState = vi.hoisted(() => ({
  createJob: vi.fn(),
  cancelJob: vi.fn(),
  retryJob: vi.fn(),
  assignStudents: vi.fn(),
  revokeStudents: vi.fn(),
  membersRefetch: vi.fn(),
  assignmentsRefetch: vi.fn(),
  sourceSlice: vi.fn(),
  activityHook: vi.fn(),
  statisticsHook: vi.fn(),
  firstMaterialReady: false,
  activityError: null as unknown,
  activityAccessLost: false,
  activityJob: undefined as ReturnType<typeof processingJob> | undefined,
  members: [
    { user_id: 'parent-1', name: '陈女士', role: 'parent' },
    { user_id: 'student-1', name: '小雨', role: 'student' },
    { user_id: 'student-2', name: '小川', role: 'student' },
  ] as EducationMember[],
  assignments: [
    {
      textbook_id: 'book-1',
      student_user_id: 'student-1',
      assigned_at: '2026-10-02T07:00:00Z',
    },
  ] as BookAssignment[],
  workbench: {
    textbook_id: 'book-1',
    title: 'Reading Explorer 3',
    structure_status: 'ready',
    materials: { total: 2, ready: 1 },
    current_job: null,
    recent_job: null,
    current_structure_id: 'structure-1',
    assigned_student_count: 0,
    updated_at: '2026-10-02T06:00:00Z',
    source: {
      document_id: 'document-1',
      parse_job_id: 'parse-1',
      primary_artifact_id: 'artifact-1',
      filename: 'reading-explorer.md',
      media_type: 'text/markdown',
      parser_id: 'markdown',
      parser_name: 'Markdown',
      completed_at: '2026-10-02T05:00:00Z',
      frozen_at: '2026-10-02T05:30:00Z',
      content_sha256: 'a'.repeat(64),
      size_bytes: 1200,
      image_count: 0,
    },
  } as TextbookWorkbench,
  structure: {
    textbook_id: 'book-1',
    structure_id: 'structure-1',
    schema_version: '2.1.0',
    warnings: [],
    structure: {
      schema_version: '2.1.0',
      book: { title: 'Reading Explorer 3' },
      source: { path: 'source.md', total_lines: 120 },
      coverage: {},
      nodes: [
        {
          id: 'unit-1',
          title: 'Sports and Fitness',
          anchor: { start_line: 1, end_line: 80 },
          children: [],
        },
        {
          id: 'appendix',
          title: 'Vocabulary Index',
          anchor: { start_line: 81, end_line: 120 },
          children: [],
        },
      ],
    },
    knowledge_points: [
      {
        knowledge_point_id: 'kp-db-1',
        skill_kp_id: 'sports-global-game',
        position: 1,
        title: '足球如何成为全球运动',
        unit_skill_node_id: 'unit-1',
        node_skill_ids: [],
        start_line: 10,
        end_line: 22,
        content_file: null,
        material_available: false,
      },
      {
        knowledge_point_id: 'kp-db-2',
        skill_kp_id: 'sports-training',
        position: 2,
        title: '冠军的训练方法',
        unit_skill_node_id: 'unit-1',
        node_skill_ids: [],
        start_line: 23,
        end_line: 40,
        content_file: 'chapters/sports-training.md',
        material_available: true,
      },
    ],
  } as BookStructure,
}));

vi.mock('../queries', () => ({
  useBookQuestions: () => ({ data: [], isLoading: false, isFetching: false }),
  useLessonQuestion: () => ({ mutateAsync: vi.fn() }),
  useBookReadingMutation: () => ({ mutate: vi.fn(), isError: false }),
  useBookReadingState: () => ({ data: {} }),
  useTextbookWorkbench: () => ({
    data: pageState.workbench,
    isLoading: false,
    isError: false,
  }),
  useManagedBookStructure: (_id: string, enabled: boolean) => ({
    data: enabled ? pageState.structure : undefined,
    isLoading: false,
    isError: false,
  }),
  useManagedBookSourceSlice: (
    bookId: string,
    startLine: number,
    endLine: number,
    enabled = true,
  ) => ({
    data: enabled ? pageState.sourceSlice(bookId, startLine, endLine) : undefined,
    isLoading: false,
  }),
  useManagedKnowledgePointMaterial: (
    _bookId: string,
    knowledgePointId: string,
  ) => ({
    data:
      knowledgePointId === 'kp-db-1' && pageState.firstMaterialReady
        ? readyMaterial
        : knowledgePointId === 'kp-db-2'
          ? {
              textbook_id: 'book-1',
              knowledge_point_id: 'kp-db-2',
              skill_kp_id: 'sports-training',
              material_available: true,
              markdown:
                '# 已有冠军训练讲义\n\n[回到全球运动](materials/kp-db-1.md)',
              generated_at: '2026-10-02T06:00:00Z',
              depth: 'lesson',
              requirements: null,
              content_sha256: 'b'.repeat(64),
            }
          : {
              textbook_id: 'book-1',
              knowledge_point_id: knowledgePointId,
              skill_kp_id: 'sports-global-game',
              material_available: false,
              markdown: null,
              generated_at: null,
              depth: null,
              requirements: null,
              content_sha256: null,
            },
    isLoading: false,
  }),
  useBookActivity: (...args: unknown[]) => { pageState.activityHook(...args);
    return {
      data: pageState.activityJob,
      events: [],
      connectionState: 'connected',
      accessLost: pageState.activityAccessLost,
      isError: Boolean(pageState.activityError),
      error: pageState.activityError,
    };
  },
  useBookJobStatistics: (...args: unknown[]) => {
    pageState.statisticsHook(...args);
    return { data: undefined, isLoading: false, isError: false };
  },
  useEducationMembers: () => ({
    data: pageState.members,
    isLoading: false,
    isError: false,
    refetch: pageState.membersRefetch,
  }),
  useManagedBookAssignments: () => ({
    data: pageState.assignments,
    isLoading: false,
    isError: false,
    refetch: pageState.assignmentsRefetch,
  }),
  useManagedBookAssignmentMutations: () => ({
    assign: { mutateAsync: pageState.assignStudents, isPending: false },
    revoke: { mutateAsync: pageState.revokeStudents, isPending: false },
  }),
  useManagedBookMutations: () => ({
    createJob: { mutateAsync: pageState.createJob, isPending: false },
    cancelJob: { mutateAsync: pageState.cancelJob, isPending: false },
    retryJob: { mutateAsync: pageState.retryJob, isPending: false },
  }),
}));

beforeEach(() => {
  authState.role = 'parent';
  void i18n.changeLanguage('zh-CN');
  vi.clearAllMocks();
  scrollMemory.clear();
  pageState.activityJob = undefined;
  pageState.firstMaterialReady = false;
  pageState.activityError = null;
  pageState.activityAccessLost = false;
  pageState.workbench.structure_status = 'ready';
  pageState.workbench.source_status = 'ready';
    pageState.workbench.current_job = null;
  pageState.workbench.recent_job = null;
  pageState.createJob.mockResolvedValue({ job_id: 'job-created' });
  pageState.cancelJob.mockResolvedValue({ job_id: 'job-active' });
  pageState.retryJob.mockResolvedValue({ job_id: 'job-retry' });
  pageState.assignStudents.mockResolvedValue([]);
  pageState.revokeStudents.mockResolvedValue(undefined);
  pageState.sourceSlice.mockImplementation((_bookId, startLine, endLine) => ({
    textbook_id: 'book-1',
    start_line: startLine,
    end_line: endLine,
    total_lines: 120,
    markdown: `# Source ${startLine}-${endLine}`,
  }));
});

describe('BookGenerationForm', () => {
  it('defaults a mixed batch to missing lessons and names the replacement count', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(
      <BookGenerationForm
        targetCount={3}
        existingCount={1}
        onSubmit={onSubmit}
        onCancel={vi.fn()}
      />,
    );

    expect(screen.getByRole('heading', { name: '生成未生成的 2 份讲义' })).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: '重新生成所选 3 份（将替换 1 份已有讲义）' })).not.toBeChecked();
    await user.click(screen.getByRole('button', { name: '开始生成' }));

    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ replaceExisting: false }));
  });
});

describe('BookReader', () => {
  it('allows the action header to grow without changing plain source headers', () => {
    const { rerender } = render(<BookReader title="位值" view="material" material={readyMaterial}
      headerActions={<button>导出 PDF</button>} onViewChange={vi.fn()} />);
    expect(screen.getByRole('heading', { name: '位值' }).closest('header')).toHaveClass('has-actions');
    rerender(<BookReader title="原文" view="source" source={source} onViewChange={vi.fn()} />);
    expect(screen.getByRole('heading', { name: '原文' }).closest('header')).not.toHaveClass('has-actions');
  });

  it('hides generation unless parent management is explicitly allowed', () => {
    render(<BookReader title="足球" view="material" material={readyMaterial}
      onViewChange={vi.fn()} onGenerate={vi.fn()} />);
    expect(screen.queryByRole('button', { name: '重新生成讲义' })).not.toBeInTheDocument();
  });

  it('confirms replacement, preserves settings on cancel, and submits only once', async () => {
    const user = userEvent.setup();
    let resolveGeneration!: () => void;
    const onGenerate = vi.fn(() => new Promise<void>((resolve) => { resolveGeneration = resolve; }));
    render(<BookReader title="足球" view="material" material={readyMaterial}
      canManageMaterials onViewChange={vi.fn()} onGenerate={onGenerate} />);
    expect(screen.getByRole('button', { name: '重新生成讲义' })).toHaveTextContent('重新生成讲义');
    await user.click(screen.getByRole('button', { name: '重新生成讲义' }));
    await user.type(screen.getByLabelText('补充要求（可选）'), '增加例题');
    await user.click(screen.getByRole('button', { name: '开始生成' }));
    expect(screen.getByRole('dialog', { name: '确认重新生成讲义？' })).toBeInTheDocument();
    expect(onGenerate).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: '保留现有讲义' }));
    expect(screen.getByLabelText('补充要求（可选）')).toHaveValue('增加例题');
    expect(screen.getByText('这是一份已经提交的讲义。')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '开始生成' }));
    await user.dblClick(screen.getByRole('button', { name: '确认重新生成' }));
    expect(onGenerate).toHaveBeenCalledTimes(1);
    expect(onGenerate).toHaveBeenCalledWith(expect.objectContaining({ requirements: '增加例题', replaceExisting: true }));
    resolveGeneration();
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('shows source first when no lesson exists and submits generation inline', async () => {
    const user = userEvent.setup();
    const onGenerate = vi.fn().mockResolvedValue(undefined);
    render(
      <BookReader
        title="足球如何成为全球运动"
        view="source"
        material={emptyMaterial}
        canManageMaterials
        source={source}
        onViewChange={vi.fn()}
        onGenerate={onGenerate}
      />,
    );

    expect(screen.getByText('第 10–22 行，共 120 行')).toBeInTheDocument();
    expect(screen.getByText('Football is played around the world.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '生成讲义' }));
    fireEvent.click(screen.getByRole('radio', { name: '深入讲解' }));
    await user.type(screen.getByLabelText('补充要求（可选）'), '多给两个例子');
    await user.click(screen.getByRole('button', { name: '开始生成' }));

    expect(onGenerate).toHaveBeenCalledWith({
      depth: 'deep',
      requirements: '多给两个例子',
      replaceExisting: false,
      includeSupplementary: false,
    });
  });

  it('retains the lesson and allows retry after a failed replacement submission', async () => {
    const user = userEvent.setup();
    const onGenerate = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(undefined);
    render(<BookReader title="足球" view="material" material={readyMaterial}
      canManageMaterials onViewChange={vi.fn()} onGenerate={onGenerate} />);
    await user.click(screen.getByRole('button', { name: '重新生成讲义' }));
    await user.click(screen.getByRole('button', { name: '开始生成' }));
    await user.click(screen.getByRole('button', { name: '确认重新生成' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('提交失败');
    expect(screen.getByText('这是一份已经提交的讲义。')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '确认重新生成' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(onGenerate).toHaveBeenCalledTimes(2);
  });

  it('keeps a successful lesson readable while switching to its source', () => {
    const onViewChange = vi.fn();
    const { rerender } = render(
      <BookReader
        title="足球如何成为全球运动"
        view="material"
        material={readyMaterial}
        canManageMaterials
        source={source}
        onViewChange={onViewChange}
        onGenerate={vi.fn()}
      />,
    );

    expect(screen.getByText('这是一份已经提交的讲义。')).toBeInTheDocument();
    expect(screen.queryByRole('tablist', { name: '阅读视图' })).not.toBeInTheDocument();

    rerender(
      <BookReader
        title="足球如何成为全球运动"
        view="source"
        material={readyMaterial}
        canManageMaterials
        source={source}
        onViewChange={onViewChange}
        onGenerate={vi.fn()}
      />,
    );
    expect(screen.getByText('Football is played around the world.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重新生成讲义' })).toBeInTheDocument();
  });

  it('does not offer lesson generation for a source-directory node', () => {
    render(
      <BookReader
        title="Vocabulary Index"
        view="source"
        source={source}
        onViewChange={vi.fn()}
      />,
    );

    expect(screen.queryByRole('button', { name: '生成讲义' })).not.toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: '讲义' })).not.toBeInTheDocument();
  });

  it('restores independent material and source scroll positions', () => {
    const { rerender, unmount } = render(
      <BookReader
        title="足球如何成为全球运动"
        view="material"
        material={readyMaterial}
        source={source}
        readingPositionKey="book-1:sports-global-game:material"
        onViewChange={vi.fn()}
      />,
    );
    const reader = screen.getByTestId('book-reader-scroll');
    reader.scrollTop = 184;
    fireEvent.scroll(reader);

    rerender(
      <BookReader
        title="足球如何成为全球运动"
        view="source"
        material={readyMaterial}
        source={source}
        readingPositionKey="book-1:sports-global-game:source"
        onViewChange={vi.fn()}
      />,
    );
    expect(reader.scrollTop).toBe(0);
    reader.scrollTop = 63;
    fireEvent.scroll(reader);

    rerender(
      <BookReader
        title="足球如何成为全球运动"
        view="material"
        material={readyMaterial}
        source={source}
        readingPositionKey="book-1:sports-global-game:material"
        onViewChange={vi.fn()}
      />,
    );
    expect(reader.scrollTop).toBe(184);

    unmount();
    render(
      <BookReader
        title="足球如何成为全球运动"
        view="source"
        material={readyMaterial}
        source={source}
        readingPositionKey="book-1:sports-global-game:source"
        onViewChange={vi.fn()}
      />,
    );
    expect(screen.getByTestId('book-reader-scroll').scrollTop).toBe(63);
  });
});

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.search}</output>;
}

function renderWorkbench(initialEntry = '/textbooks/book-1') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route
          path="/textbooks/:textbookId"
          element={<><TextbookWorkbenchPage /><LocationProbe /></>}
        />
      </Routes>
    </MemoryRouter>,
  );
}

function renderAssignmentDialog() {
  function DialogHarness() {
    const [open, setOpen] = useState(true);
    return <BookAssignmentDialog textbookId="book-1" open={open} onOpenChange={setOpen} />;
  }
  render(<DialogHarness />);
}

describe('TextbookWorkbenchPage', () => {
  it('opens the learning prompt without fetching source Markdown for an ungenerated knowledge point', () => {
    pageState.sourceSlice.mockReturnValue({ ...source, start_line: 1, end_line: 34, markdown: '\n'.repeat(9) + 'Target source paragraph.' });
    const { container } = renderWorkbench('/textbooks/book-1?kp=sports-global-game&view=source&nav=knowledge');
    expect(screen.getByRole('button', { name: '开始学习' })).toBeInTheDocument();
    expect(screen.queryByText('Target source paragraph.')).not.toBeInTheDocument();
    expect(pageState.sourceSlice).not.toHaveBeenCalled();
    expect(container.querySelector('[data-source-highlight]')).toBeNull();
    expect(container.querySelector('blockquote')).toBeNull();
  });

  it('offers lecture regeneration only to parent members', () => {
    const { unmount } = renderWorkbench('/textbooks/book-1?kp=sports-training&view=material');
    expect(screen.getByRole('button', { name: '重新生成讲义' })).toHaveTextContent('重新生成讲义');
    unmount();
    authState.role = 'student';
    renderWorkbench('/textbooks/book-1?kp=sports-training&view=material');
    expect(screen.queryByRole('button', { name: '重新生成讲义' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '生成讲义' })).not.toBeInTheDocument();
  });

  it('shows a waiting course prompt to students without offering generation', () => {
    authState.role = 'student';
    renderWorkbench('/textbooks/book-1?kp=sports-global-game&view=source&nav=knowledge');
    expect(screen.getByText('等待家长准备课程')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '开始学习' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '选择讲解模式' })).not.toBeInTheDocument();
    expect(pageState.sourceSlice).not.toHaveBeenCalled();
  });

  it('collapses and restores the directory without losing search or reading selection', async () => {
    const user = userEvent.setup();
    renderWorkbench('/textbooks/book-1?kp=sports-training&view=material');
    const search = screen.getByRole('searchbox', { name: '搜索教材内容' });
    await user.type(search, '冠军');
    await user.click(screen.getByRole('button', { name: '收起教材目录' }));
    expect(screen.getByTestId('textbook-workbench')).toHaveClass('is-nav-collapsed');
    expect(screen.getByText('已有冠军训练讲义')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '展开教材目录' }));
    expect(screen.getByTestId('textbook-workbench')).not.toHaveClass('is-nav-collapsed');
    expect(search).toHaveValue('冠军');
    expect(screen.getByTestId('location')).toHaveTextContent('?kp=sports-training&view=material');
  });

  it('hides a cached compact activity after access is lost', () => {
    pageState.activityJob = processingJob();
    pageState.workbench.current_job = pageState.activityJob;
    pageState.activityAccessLost = true;
    renderWorkbench('/textbooks/book-1?kp=sports-training&view=material&activity=job-1');
    expect(screen.getByRole('alert')).toHaveTextContent('处理活动已不可访问，计时已停止');
    expect(screen.queryByRole('complementary', { name: '教材处理活动' })).not.toBeInTheDocument();
  });
  it.each(['missing', 'access_lost'])('returns to legal reading from a %s activity without losing selection', async (failure) => {
    if (failure === 'missing') pageState.activityError = { isAxiosError: true, response: { status: 404 } };
    else { pageState.activityJob = processingJob(); pageState.activityAccessLost = true; }
    renderWorkbench('/textbooks/book-1?kp=sports-training&view=material&activity=job-1&panel=processing');
    expect(screen.getByRole('alert')).toHaveTextContent(failure === 'missing' ? '处理任务不存在或已不可访问' : '处理活动已不可访问，计时已停止');
    expect(screen.queryByRole('heading', { name: '处理时间线' })).not.toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole('button', { name: '返回当前教材' }));
    expect(screen.getByTestId('location')).toHaveTextContent('?kp=sports-training&view=material');
    expect(screen.getByTestId('location')).not.toHaveTextContent('activity');
    expect(screen.getByText('已有冠军训练讲义')).toBeInTheDocument();
  });
  it('opens the first submitted lesson while the structure cache still says unavailable', async () => {
    const job = processingJob({ kind: 'materials' });
    job.items[0] = {
      ...job.items[0],
      kind: 'material',
      status: 'succeeded',
      knowledge_point_id: 'kp-db-1',
      skill_kp_id: 'sports-global-game',
      knowledge_point_title: '足球如何成为全球运动',
    };
    pageState.activityJob = job;
    pageState.firstMaterialReady = true;
    renderWorkbench(
      '/textbooks/book-1?kp=sports-training&view=material&activity=job-1&panel=processing',
    );
    await userEvent
      .setup()
      .click(
        screen.getByRole('button', { name: '阅读讲义：足球如何成为全球运动' }),
      );
    expect(screen.getByTestId('location')).toHaveTextContent(
      'kp=sports-global-game&view=material',
    );

    expect(screen.getByText('这是一份已经提交的讲义。')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '知识点' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
  });
  it('rejects a foreign textbook activity URL and returns without losing the reader selection', async () => {
    pageState.activityJob = processingJob({ textbook_id: 'book-2' });
    renderWorkbench(
      '/textbooks/book-1?kp=sports-training&view=material&activity=job-1&panel=processing',
    );
    expect(screen.getByRole('alert')).toHaveTextContent(
      '该处理任务不属于当前教材',
    );
    expect(
      screen.queryByRole('heading', { name: '处理时间线' }),
    ).not.toBeInTheDocument();
    expect(pageState.statisticsHook).not.toHaveBeenCalled();
    await userEvent
      .setup()
      .click(screen.getByRole('button', { name: '返回当前教材' }));
    expect(screen.getByTestId('location')).toHaveTextContent(
      '?kp=sports-training&view=material',
    );
    expect(screen.getByTestId('location')).not.toHaveTextContent('activity');
    expect(screen.getByText('已有冠军训练讲义')).toBeInTheDocument();
  });
  it('defaults pending sources without a directory to processing and allows a manual reading return', async () => {
    pageState.workbench.structure_status = 'queued';
    pageState.workbench.source_status = 'pending';
    pageState.activityJob = processingJob({ status: 'queued' });
    pageState.workbench.current_job = pageState.activityJob;
    renderWorkbench();
    expect(screen.getByRole('heading', { name: 'Reading Explorer 3' })).toBeInTheDocument();
    expect(screen.getByRole('listitem', { name: '受理等待' })).toHaveTextContent('等待');
    expect(screen.getByTestId('location')).toHaveTextContent('panel=processing');
    await userEvent.setup().click(screen.getByRole('button', { name: '返回阅读' }));
    expect(screen.getByTestId('location')).toHaveTextContent('panel=reading');
    expect(screen.queryByRole('heading', { name: '处理时间线' })).not.toBeInTheDocument();
  });
  it('restores processing layout without a second subscription and preserves the reading selection', async () => {
    pageState.activityJob = processingJob();
    pageState.workbench.current_job = pageState.activityJob;
    renderWorkbench('/textbooks/book-1?kp=sports-training&view=material&activity=job-1&panel=processing');
    expect(screen.getByRole('heading', { name: 'Reading Explorer 3' })).toBeInTheDocument();
    expect(pageState.activityHook).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('button', { name: /^活动$/ })).not.toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole('button', { name: '返回阅读' }));
    expect(screen.getByTestId('location')).toHaveTextContent('kp=sports-training&view=material&activity=job-1');
    expect(screen.getByText('已有冠军训练讲义')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^活动$/ })).not.toBeInTheDocument();
  });

  it('hides activity after completion in a normal reader', () => {
    pageState.workbench.recent_job = processingJob({ status: 'succeeded' });
    renderWorkbench('/textbooks/book-1?kp=sports-training&view=material');
    expect(pageState.activityHook).toHaveBeenCalledWith(undefined, 'book-1', false);
    expect(screen.queryByRole('button', { name: '活动' })).not.toBeInTheDocument();
  });

  it('hides student assignment during structure processing and moves cancel into the timeline', () => {
    pageState.activityJob = processingJob();
    pageState.workbench.current_job = pageState.activityJob;
    renderWorkbench('/textbooks/book-1?activity=job-1&panel=processing');
    expect(screen.queryByRole('button', { name: '给学生使用' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '取消本次生成' }).closest('.book-processing-view')).not.toBeNull();
    expect(screen.getAllByRole('button', { name: '取消本次生成' })).toHaveLength(1);
  });

  it('keeps one cancel control beside the compact processing title while reading', () => {
    pageState.activityJob = processingJob();
    pageState.workbench.current_job = pageState.activityJob;
    renderWorkbench('/textbooks/book-1?kp=sports-training&view=material&activity=job-1');
    expect(screen.getByRole('button', { name: '取消本次生成' }).closest('aside')).not.toBeNull();
    expect(screen.getAllByRole('button', { name: '取消本次生成' })).toHaveLength(1);
  });

  it.each(['error', 'loading', 'foreign', 'access_lost'])('keeps cancellation reachable when the full activity is %s', async (state) => {
    pageState.workbench.current_job = processingJob();
    if (state === 'error') pageState.activityError = { isAxiosError: true, response: { status: 503 } };
    if (state === 'foreign') pageState.activityJob = processingJob({ textbook_id: 'book-2' });
    if (state === 'access_lost') {
      pageState.activityJob = processingJob();
      pageState.activityAccessLost = true;
    }
    renderWorkbench('/textbooks/book-1?activity=job-1&panel=processing');
    await userEvent.setup().click(screen.getByRole('button', { name: '取消本次生成' }));
    expect(pageState.cancelJob).toHaveBeenCalledWith('job-1');
  });

  it('dismisses completed processing when entering learning and preserves the reader selection', async () => {
    pageState.activityJob = processingJob({ status: 'succeeded' });
    renderWorkbench('/textbooks/book-1?kp=sports-training&view=material&activity=job-1&panel=processing');
    await userEvent.setup().click(screen.getByRole('button', { name: '进入学习空间' }));
    expect(screen.getByTestId('location')).toHaveTextContent('kp=sports-training&view=material');
    expect(screen.getByTestId('location')).not.toHaveTextContent('activity');
    expect(screen.queryByRole('complementary', { name: '教材处理活动' })).not.toBeInTheDocument();
    expect(screen.getByText('已有冠军训练讲义')).toBeInTheDocument();
  });

  it('preserves reader scroll across full processing and compact layouts', async () => {
    pageState.activityJob = processingJob();
    pageState.workbench.current_job = pageState.activityJob;
    renderWorkbench('/textbooks/book-1?kp=sports-training&view=material&activity=job-1');
    const reader = screen.getByRole('region', { name: '讲义与问答' });
    reader.scrollTop = 184;
    fireEvent.scroll(reader);
    await userEvent.setup().click(screen.getByRole('button', { name: '打开整页时间线' }));
    expect(screen.queryByTestId('book-reader-scroll')).not.toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole('button', { name: '返回阅读' }));
    expect(screen.getByRole('region', { name: '讲义与问答' }).scrollTop).toBe(184);
  });

  it('enters processing after lesson acceptance and does not erase the current view', async () => {
    renderWorkbench('/textbooks/book-1?kp=sports-global-game&view=source');
    await userEvent.setup().click(screen.getByRole('button', { name: '开始学习' }));
    expect(screen.getByTestId('location')).toHaveTextContent('panel=processing');
    expect(screen.getByTestId('location')).toHaveTextContent('kp=sports-global-game&view=source');
  });

  it('does not leave processing when the server reports completion', () => {
    pageState.activityJob = processingJob({ status: 'succeeded' });
    renderWorkbench('/textbooks/book-1?kp=sports-training&view=material&activity=job-1&panel=processing');
    expect(screen.getByRole('heading', { name: 'Reading Explorer 3' })).toBeInTheDocument();
    expect(screen.getByTestId('location')).toHaveTextContent('panel=processing');
  });
  it('chooses the first KP and source view when the URL has no selection', async () => {
    renderWorkbench();

    await waitFor(() => {
      expect(screen.getByTestId('location')).toHaveTextContent('?kp=sports-global-game&view=source');
    });
    expect(screen.getByRole('heading', { name: '足球如何成为全球运动' })).toBeInTheDocument();
  });

  it('loads bounded context around the selected source anchor', async () => {
    renderWorkbench('/textbooks/book-1?kp=sports-global-game&view=source&nav=text');

    await waitFor(() => {
      expect(pageState.sourceSlice).toHaveBeenCalledWith('book-1', 1, 34);
    });
    expect(screen.getByText('第 10–22 行，共 120 行')).toBeInTheDocument();
  });

  it('uses material by default for a generated KP and source for an ungenerated KP', async () => {
    renderWorkbench('/textbooks/book-1?kp=sports-training');

    await waitFor(() => expect(screen.getByText('已有冠军训练讲义')).toBeInTheDocument());
    fireEvent.click(screen.getByText('足球如何成为全球运动'));

    await waitFor(() => {
      expect(screen.getByTestId('location')).toHaveTextContent('kp=sports-global-game');
      expect(screen.getByTestId('location')).toHaveTextContent('view=source');
    });
  });

  it('opens a linked knowledge point source when its material is not generated', async () => {
    const user = userEvent.setup();
    renderWorkbench('/textbooks/book-1?kp=sports-training&view=material');

    await user.click(await screen.findByRole('link', { name: '回到全球运动' }));

    await waitFor(() => {
      expect(screen.getByTestId('location')).toHaveTextContent('kp=sports-global-game');
      expect(screen.getByTestId('location')).toHaveTextContent('view=source');
    });
  });

  it('opens a source node without exposing generation controls', async () => {
    const { container } = renderWorkbench('/textbooks/book-1?node=appendix&view=source');

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Vocabulary Index' })).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: '生成讲义' })).not.toBeInTheDocument();
    expect(pageState.sourceSlice).toHaveBeenCalledWith('book-1', 81, 120);
    expect(container.querySelector('[data-source-highlight]')).toBeNull();
  });

  it('opens original and text directory independently and preserves the original view on refresh', async () => {
    const user = userEvent.setup();
    renderWorkbench('/textbooks/book-1?node=appendix&view=original&nav=source&pdfPage=12');
    expect(await screen.findByTestId('original-file')).toHaveTextContent('PDF start line 81; page 12');
    expect(screen.getByRole('tab', { name: '原始教材' })).toHaveAttribute('aria-selected', 'true');
    await user.click(screen.getByRole('tab', { name: '文字目录' }));
    expect(screen.queryByTestId('original-file')).not.toBeInTheDocument();
    expect(screen.getByTestId('location')).toHaveTextContent('view=source');
    await user.click(screen.getByRole('tab', { name: '原始教材' }));
    await user.click(screen.getByRole('button', { name: '打开 Sports and Fitness' }));
    expect(screen.getByTestId('original-file')).toHaveTextContent('PDF start line 1; page automatic');
    expect(screen.getByTestId('location')).toHaveTextContent('view=original');
  });

  it('opens batch settings and skips selected knowledge points that already have material', async () => {
    const user = userEvent.setup();
    renderWorkbench();

    await user.click(screen.getByRole('button', { name: '批量选择' }));
    await user.click(screen.getByRole('checkbox', { name: '选择 Sports and Fitness 全部知识点' }));
    await user.click(screen.getByRole('button', { name: '生成所选讲义' }));

    expect(screen.getByRole('heading', { name: '生成未生成的 1 份讲义' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '开始生成' }));

    expect(pageState.createJob).toHaveBeenCalledWith({
      textbookId: 'book-1',
      input: expect.objectContaining({
        knowledge_point_ids: ['kp-db-1'],
        replace_existing: false,
      }),
    });
  });

  it('cancels an active job and retries only the server-defined unfinished items', async () => {
    const user = userEvent.setup();
    pageState.workbench.current_job = {
      job_id: 'job-active',
      kind: 'materials',
      status: 'running',
      total_items: 2,
      succeeded_items: 1,
      failed_items: 0,
      cancelled_items: 0,
      not_run_items: 0,
      high_water_seq: 3,
      activity_status: 'available',
      created_at: '2026-10-02T06:00:00Z',
      started_at: '2026-10-02T06:00:01Z',
      finished_at: null,
      safe_error: null,
    };
    const view = renderWorkbench();

    await user.click(screen.getByRole('button', { name: '取消本次生成' }));
    expect(pageState.cancelJob).toHaveBeenCalledWith('job-active');

    view.unmount();
    pageState.workbench.current_job = null;
    pageState.workbench.recent_job = {
      job_id: 'job-partial',
      kind: 'materials',
      status: 'partially_succeeded',
      total_items: 2,
      succeeded_items: 1,
      failed_items: 1,
      cancelled_items: 0,
      not_run_items: 0,
      high_water_seq: 8,
      activity_status: 'available',
      created_at: '2026-10-02T06:00:00Z',
      started_at: '2026-10-02T06:00:01Z',
      finished_at: '2026-10-02T06:10:00Z',
      safe_error: null,
    };
    renderWorkbench();

    await user.click(screen.getByRole('button', { name: '重试未完成项' }));
    expect(pageState.retryJob).toHaveBeenCalledWith('job-partial');
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('activity=job-retry'));
  });

  it('opens student access with current assignments preselected and excludes parents', async () => {
    renderAssignmentDialog();

    expect(screen.getByRole('dialog', { name: '给学生使用' })).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: '小雨' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: '小川' })).not.toBeChecked();
    expect(screen.queryByRole('checkbox', { name: '陈女士' })).not.toBeInTheDocument();
  });

  it('saves only added and removed student assignments', async () => {
    const user = userEvent.setup();
    renderAssignmentDialog();
    await user.click(screen.getByRole('checkbox', { name: '小雨' }));
    await user.click(screen.getByRole('checkbox', { name: '小川' }));
    await user.click(screen.getByRole('button', { name: '保存' }));

    expect(pageState.assignStudents).toHaveBeenCalledWith({
      textbookId: 'book-1',
      studentUserIds: ['student-2'],
    });
    expect(pageState.revokeStudents).toHaveBeenCalledWith({
      textbookId: 'book-1',
      studentUserIds: ['student-1'],
    });
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '给学生使用' })).not.toBeInTheDocument());
  });

  it('keeps the assignment dialog open while saving', async () => {
    const user = userEvent.setup();
    pageState.assignStudents.mockReturnValue(new Promise(() => undefined));
    renderAssignmentDialog();
    await user.click(screen.getByRole('checkbox', { name: '小川' }));
    await user.click(screen.getByRole('button', { name: '保存' }));

    expect(screen.getByRole('button', { name: '正在保存' })).toBeDisabled();
    expect(screen.getByRole('dialog', { name: '给学生使用' })).toBeInTheDocument();
  });

  it('shows a retry action without losing the selection when saving fails', async () => {
    const user = userEvent.setup();
    pageState.assignStudents
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce([]);
    renderAssignmentDialog();
    await user.click(screen.getByRole('checkbox', { name: '小川' }));
    await user.click(screen.getByRole('button', { name: '保存' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('保存学生授权失败');
    expect(screen.getByRole('checkbox', { name: '小川' })).toBeChecked();
    await user.click(screen.getByRole('button', { name: '重试' }));

    expect(pageState.assignStudents).toHaveBeenCalledTimes(2);
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
  });
});
