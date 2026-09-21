import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import TextbookStructurePage from '../TextbookStructurePage';

const structureState = vi.hoisted(() => ({
  data: undefined as Record<string, unknown> | undefined,
}));

const save = vi.fn().mockResolvedValue({});
const accept = vi.fn().mockResolvedValue({});
const create = vi.fn().mockResolvedValue({ generation_job_id: 'generation-1' });
const refetch = vi.fn().mockResolvedValue({});
let progressData: Record<string, unknown> | null = null;

vi.mock('../queries', () => ({
  useLatestTextbookStructure: () => {
    structureState.data ??= {
      structure_id: 'structure-1',
      version_id: 'version-1',
      sequence: 1,
      status: 'review',
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
          knowledge_points: [
            {
              knowledge_point_id: 'kp-1',
              position: 1,
              slug: 'world-game',
              title: '世界运动',
              summary: '',
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
  useStructureMutations: () => ({
    create: { mutateAsync: create, isPending: false },
    resumeStructure: { mutateAsync: vi.fn().mockResolvedValue({ generation_job_id: 'generation-resume' }), isPending: false },
    generateBookAssets: { mutateAsync: vi.fn().mockResolvedValue({ generation_job_id: 'assets-1' }), isPending: false },
    save: { mutateAsync: save, isPending: false },
    accept: { mutateAsync: accept, isPending: false },
    generateLesson: { mutateAsync: vi.fn().mockResolvedValue({ generation_job_id: 'lesson-1' }), isPending: false },
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
    progressData = null;
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

    expect(screen.getByTestId('structure-generation-timeline')).toHaveTextContent('分析教材结构');
    expect(screen.getByText(/可以关闭页面，处理会继续在后台进行/)).toBeInTheDocument();
    expect(screen.getByTestId('structure-activity-list')).toHaveTextContent('扫描源文档：01-rex-3e-sb3.pdf.md');
    expect(screen.getByTestId('structure-activity-list')).toHaveTextContent('派出并行子任务分析单元');
    expect(screen.getByTestId('structure-activity-list')).toHaveTextContent('×3');
  });

  it('supports add, split, merge, and delete knowledge-point actions', async () => {
    const user = userEvent.setup();
    let view = renderPage();

    await user.click(screen.getByRole('button', { name: '选择 Unit 1: Sports' }));
    await user.click(screen.getByRole('button', { name: '添加知识点' }));
    expect(screen.getByDisplayValue('新知识点')).toBeInTheDocument();

    view.unmount();
    view = renderPage();
    await user.click(screen.getByRole('button', { name: '选择 Unit 1: Sports' }));
    await user.click(screen.getByRole('button', { name: '拆分 世界运动' }));
    expect(screen.getByDisplayValue('世界运动（拆分）')).toBeInTheDocument();

    view.unmount();
    view = renderPage();
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
