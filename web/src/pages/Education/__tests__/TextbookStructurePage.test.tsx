import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import TextbookStructurePage from '../TextbookStructurePage';

const structureState = vi.hoisted(() => ({
  data: undefined as Record<string, unknown> | undefined,
  statusOverride: undefined as string | undefined,
  scopeVerifiedOverride: undefined as boolean | undefined,
}));

const save = vi.fn().mockResolvedValue({});
const accept = vi.fn().mockResolvedValue({});
const create = vi.fn().mockResolvedValue({ generation_job_id: 'generation-1' });
const generateLesson = vi.fn().mockResolvedValue({ generation_job_id: 'lesson-1' });
const refetch = vi.fn().mockResolvedValue({});
let progressData: Record<string, unknown> | null = null;
let lessonGenerationStatus: Record<string, unknown> = {
  knowledge_point_id: 'kp-1',
  generating: false,
  generation_job_id: null,
  status: null,
  attempt_count: 0,
  auto_grading: false,
};

vi.mock('../queries', () => ({
  useLatestTextbookStructure: () => {
    structureState.data ??= {
      structure_id: 'structure-1',
      version_id: 'version-1',
      sequence: 1,
      status: structureState.statusOverride ?? 'review',
      schema_version: 'langalpha-managed-textbook-structure/v1',
      processing_profile_sha256: 'a'.repeat(64),
      input_manifest_sha256: 'b'.repeat(64),
      source_revision: 'c'.repeat(64),
      validation_warnings: [
        'source_quote_unresolved',
        'source_quote_unresolved',
        'unit_type_promoted',
      ],
      units: [
        {
          unit_id: 'unit-1',
          position: 1,
          slug: 'unit-1-sports',
          title: 'Unit 1: Sports',
          summary: '',
          unit_type: 'teaching',
          confidence: 0.96,
          status: 'review',
          source_refs: [{ source_id: 'source-1', start: 0, end: 50, quote: 'Unit 1' }],
          scopes: [
            {
              scope_id: 'scope-1',
              slot: 'reading_a',
              title: 'The World’s Game',
              summary: '',
              reading_skill: '',
              vocabulary_building: '',
              critical_thinking: '',
              source_id: 'source-1',
              line_start: 10,
              line_end: 40,
              char_start: 100,
              char_end: 900,
              verified: structureState.scopeVerifiedOverride ?? false,
            },
            {
              scope_id: 'scope-2',
              slot: 'reading_b',
              title: 'What Makes an Olympic Champion?',
              summary: '',
              reading_skill: '',
              vocabulary_building: '',
              critical_thinking: '',
              source_id: 'source-1',
              line_start: 41,
              line_end: 70,
              char_start: 901,
              char_end: 1400,
              verified: true,
            },
          ],
          knowledge_points: [
            {
              knowledge_point_id: 'kp-1',
              position: 1,
              slug: 'world-game',
              title: '世界运动',
              summary: '',
              scope_slot: 'reading_a',
              confidence: 0.9,
              status: 'review',
              source_refs: [{ source_id: 'source-1', start: 0, end: 40 }],
            },
            {
              knowledge_point_id: 'kp-2',
              position: 2,
              slug: 'love-for-soccer',
              title: '足球之爱',
              summary: '',
              confidence: 0.9,
              status: 'review',
              source_refs: [{ source_id: 'source-1', start: null, end: null }],
            },
          ],
        },
      ],
      lesson_summary: {
        total: 2,
        accepted: 0,
        generated: 0,
        approved: 0,
      },
    };
    return {
      data: structureState.data,
      isLoading: false,
      refetch,
    };
  },
  useStructureGenerationJob: () => ({ data: undefined }),
  useStructureGenerationProgress: () => ({
    data: progressData,
    isPending: false,
    isError: false,
  }),
  useKnowledgePointLessonByPoint: () => ({
    data: null,
    isLoading: false,
    refetch,
  }),
  useKnowledgePointSourcePreview: () => ({
    data: {
      knowledge_point_id: 'kp-1',
      knowledge_point_title: '世界运动',
      unit_id: 'unit-1',
      unit_title: 'Unit 1: Sports',
      snippets: [
        {
          source_id: 'source-1',
          source_title: 'Reading Explorer 3',
          start: 2,
          end: 8,
          quote: 'Unit 1',
          markdown: '# Unit 1\n\n足球的历史与流行原因。',
          truncated_before: false,
          truncated_after: false,
        },
      ],
    },
    isLoading: false,
    isError: false,
  }),
  useLessonGenerationStatus: () => ({
    data: lessonGenerationStatus,
    isPending: false,
    isError: false,
  }),
  useStructureMutations: () => ({
    create: { mutateAsync: create, isPending: false },
    resumeStructure: { mutateAsync: vi.fn().mockResolvedValue({ generation_job_id: 'generation-resume' }), isPending: false },
    generateBookAssets: { mutateAsync: vi.fn().mockResolvedValue({ generation_job_id: 'assets-1' }), isPending: false },
    save: { mutateAsync: save, isPending: false },
    accept: { mutateAsync: accept, isPending: false },
    generateLesson: { mutateAsync: generateLesson, isPending: false },
  }),
}));

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/textbooks/textbook-1/versions/version-1/structure']}>
      <Routes>
        <Route
          path="/textbooks/:textbookId/versions/:versionId/structure"
          element={<TextbookStructurePage />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe('TextbookStructurePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    structureState.data = undefined;
    structureState.statusOverride = undefined;
    structureState.scopeVerifiedOverride = undefined;
    progressData = null;
    lessonGenerationStatus = {
      knowledge_point_id: 'kp-1',
      generating: false,
      generation_job_id: null,
      status: null,
      attempt_count: 0,
      auto_grading: false,
    };
  });

  it('renders Unit and knowledge-point review tree', async () => {
    const user = userEvent.setup();
    renderPage();

    expect(screen.getByRole('button', { name: '选择 Unit 1: Sports' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '选择知识点 世界运动' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '选择知识点 足球之爱' })).toBeInTheDocument();
    await user.click(screen.getByRole('tab', { name: '课程' }));
    expect(screen.getByText('还没有课程 Markdown')).toBeInTheDocument();
    expect(screen.getByTestId('structure-warning-summary')).toHaveTextContent(
      '部分引用暂时无法定位到解析 Markdown',
    );
    expect(screen.getByTestId('structure-warning-summary')).toHaveTextContent('（2 处）');
  });

  it('shows original markdown before a lesson exists', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('tab', { name: '原文依据' }));

    expect(await screen.findByText('Reading Explorer 3')).toBeInTheDocument();
    expect(screen.getAllByText('Unit 1').length).toBeGreaterThan(0);
    expect(screen.getByText(/足球的历史与流行原因/)).toBeInTheDocument();
  });

  it('flags a reading without a verified scope', () => {
    renderPage();

    expect(screen.getByTestId('scope-warning')).toHaveTextContent('范围待确认');
    expect(screen.getByTestId('scope-warning')).toHaveTextContent('The World’s Game');
  });

  it('assigns a knowledge point to an exact Reading scope', async () => {
    const user = userEvent.setup();
    renderPage();

    const scope = screen.getByRole('combobox', { name: '阅读范围 世界运动' });
    expect(scope).toHaveValue('reading_a');
    await user.selectOptions(scope, 'reading_b');
    await user.click(screen.getByRole('button', { name: '保存结构' }));

    await waitFor(() => expect(save).toHaveBeenCalled());
    expect(save.mock.calls.at(-1)?.[0].units[0].knowledge_points[0].scope_slot).toBe(
      'reading_b',
    );
  });

  it('shows a processing timeline while a structure job is active', () => {
    structureState.data = {
      structure_id: 'structure-1',
      version_id: 'version-1',
      sequence: 1,
      status: 'running',
      schema_version: 'langalpha-managed-textbook-structure/v1',
      processing_profile_sha256: 'a'.repeat(64),
      input_manifest_sha256: 'b'.repeat(64),
      source_revision: 'c'.repeat(64),
      validation_warnings: [],
      units: [],
      lesson_summary: { total: 0, accepted: 0, generated: 0, approved: 0 },
      latest_generation_job_id: 'generation-1',
      latest_generation_job: {
        generation_job_id: 'generation-1',
        status: 'running',
        attempt_count: 1,
        created_at: new Date().toISOString(),
        started_at: new Date().toISOString(),
        heartbeat_at: new Date().toISOString(),
      },
    };

    progressData = {
      generation_job_id: 'generation-1',
      status: 'running',
      truncated: false,
      events: [
        {
          sequence: 0,
          kind: 'tool',
          label: '扫描源文档：01-rex-3e-sb3.pdf.md',
          detail: null,
          status: 'completed',
          timestamp: '2026-09-21T04:45:46Z',
          count: 1,
        },
        {
          sequence: 1,
          kind: 'tool',
          label: '派出并行子任务分析单元',
          detail: null,
          status: 'running',
          timestamp: '2026-09-21T04:46:10Z',
          count: 3,
        },
      ],
    };

    renderPage();

    const progressCard = screen.getByTestId('structure-active-job');
    expect(progressCard).toHaveTextContent('分析教材结构');
    expect(progressCard).toHaveTextContent('扫描源文档：01-rex-3e-sb3.pdf.md');
    expect(progressCard).toHaveTextContent('派出并行子任务分析单元');
    expect(progressCard).toHaveTextContent('×3');
  });

  it('shows a lesson generation timeline in the knowledge-point workspace', () => {
    structureState.statusOverride = 'accepted';
    lessonGenerationStatus = {
      knowledge_point_id: 'kp-1',
      generating: true,
      generation_job_id: 'lesson-generation-1',
      status: 'running',
      attempt_count: 1,
      auto_grading: false,
      started_at: new Date().toISOString(),
      heartbeat_at: new Date().toISOString(),
    };
    progressData = {
      generation_job_id: 'lesson-generation-1',
      status: 'running',
      truncated: false,
      events: [
        {
          sequence: 0,
          kind: 'tool',
          label: '读取冻结输入清单',
          detail: null,
          status: 'completed',
          timestamp: '2026-09-21T04:45:46Z',
          count: 1,
        },
        {
          sequence: 1,
          kind: 'tool',
          label: '生成课程草稿',
          detail: null,
          status: 'running',
          timestamp: '2026-09-21T04:46:10Z',
          count: 1,
        },
      ],
    };

    renderPage();

    const lessonProgress = screen.getByTestId('lesson-generation-progress');
    expect(lessonProgress).toHaveTextContent('课程生成进度');
    expect(lessonProgress).toHaveTextContent('分析教材结构');
    expect(lessonProgress).toHaveTextContent('读取冻结输入清单');
    expect(screen.getByText(/任务已提交，上方会显示阶段进度和实时处理步骤/)).toBeInTheDocument();
  });

  it('submits trimmed lesson generation guidance', async () => {
    structureState.statusOverride = 'accepted';
    structureState.scopeVerifiedOverride = true;
    const user = userEvent.setup();
    renderPage();

    const prompt = screen.getByRole('textbox', { name: '课程生成要求（可选）' });
    await user.type(prompt, '  使用中文讲解，保留英文术语。  ');
    await user.click(screen.getByRole('button', { name: '生成课程' }));

    await waitFor(() => expect(generateLesson).toHaveBeenCalledWith({
      knowledgePointId: 'kp-1',
      autoGrading: false,
      prompt: '使用中文讲解，保留英文术语。',
    }));
  });

  it('restores persisted lesson guidance in the structure workspace', () => {
    structureState.statusOverride = 'accepted';
    lessonGenerationStatus = {
      ...lessonGenerationStatus,
      prompt: '使用中文讲解，保留英文术语。',
    };
    renderPage();

    expect(
      screen.getByRole('textbox', { name: '课程生成要求（可选）' }),
    ).toHaveValue('使用中文讲解，保留英文术语。');
  });

  it('supports add, split, merge, and delete knowledge-point actions', async () => {
    const user = userEvent.setup();
    let view = renderPage();

    await user.click(screen.getByRole('tab', { name: '原文依据' }));
    await user.click(screen.getByRole('button', { name: '选择 Unit 1: Sports' }));
    await user.click(screen.getByRole('button', { name: '添加知识点' }));
    expect(screen.getByDisplayValue('新知识点')).toBeInTheDocument();

    view.unmount();
    view = renderPage();
    await user.click(screen.getByRole('tab', { name: '原文依据' }));
    await user.click(screen.getByRole('button', { name: '选择 Unit 1: Sports' }));
    await user.click(screen.getByRole('button', { name: '拆分 世界运动' }));
    expect(screen.getByDisplayValue('世界运动（拆分）')).toBeInTheDocument();

    view.unmount();
    view = renderPage();
    await user.click(screen.getByRole('tab', { name: '原文依据' }));
    await user.click(screen.getByRole('button', { name: '选择 Unit 1: Sports' }));
    await user.click(screen.getByRole('button', { name: '合并 足球之爱' }));
    expect(screen.getByDisplayValue('世界运动 / 足球之爱')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '删除 世界运动 / 足球之爱' }));
    expect(screen.queryByDisplayValue('世界运动 / 足球之爱')).not.toBeInTheDocument();
  });

  it('shows Chinese tips for knowledge-point action buttons', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('button', { name: '选择 Unit 1: Sports' }));
    await user.hover(screen.getByRole('button', { name: '拆分 世界运动' }));

    expect(await screen.findAllByText(
      '拆分知识点：保留当前内容，并在下方创建一个副本，适合把过大的知识点拆成两个。',
    )).not.toHaveLength(0);
  });

  it('saves edits and accepts the structure', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole('button', { name: '选择 Unit 1: Sports' }));
    const title = screen.getByDisplayValue('世界运动');
    fireEvent.change(title, { target: { value: '世界运动（修订）' } });

    await user.click(screen.getByRole('button', { name: '保存结构' }));
    await waitFor(() => expect(save).toHaveBeenCalledWith(expect.objectContaining({
      structureId: 'structure-1',
    })));

    await user.click(screen.getByRole('button', { name: '接受结构' }));
    await waitFor(() => expect(accept).toHaveBeenCalledWith('structure-1'));
  });

  it('keeps save and accept reachable from a knowledge point workspace', async () => {
    const user = userEvent.setup();
    renderPage();

    expect(screen.getByRole('tab', { name: '原文依据' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '保存结构' }));
    await waitFor(() => expect(save).toHaveBeenCalledWith(expect.objectContaining({
      structureId: 'structure-1',
    })));
  });
});
