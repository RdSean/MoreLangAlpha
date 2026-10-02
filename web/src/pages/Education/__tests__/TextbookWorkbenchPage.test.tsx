import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { scrollMemory } from '@/lib/scrollMemory';
import { BookGenerationForm } from '../components/BookGenerationForm';
import { BookReader } from '../components/BookReader';
import TextbookWorkbenchPage from '../TextbookWorkbenchPage';
import type {
  BookSourceSlice,
  BookStructure,
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
  sourceSlice: vi.fn(),
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
  useTextbookWorkbench: () => ({ data: pageState.workbench, isLoading: false, isError: false }),
  useManagedBookStructure: () => ({ data: pageState.structure, isLoading: false, isError: false }),
  useManagedBookSourceSlice: (bookId: string, startLine: number, endLine: number) => ({
    data: pageState.sourceSlice(bookId, startLine, endLine),
    isLoading: false,
  }),
  useManagedKnowledgePointMaterial: (_bookId: string, knowledgePointId: string) => ({
    data: knowledgePointId === 'kp-db-2'
      ? {
        textbook_id: 'book-1',
        knowledge_point_id: 'kp-db-2',
        skill_kp_id: 'sports-training',
        material_available: true,
        markdown: '# 已有冠军训练讲义\n\n[回到全球运动](materials/kp-db-1.md)',
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
  useBookActivity: () => ({ data: undefined, events: [], connectionState: 'connected' }),
  useManagedBookMutations: () => ({
    createJob: { mutateAsync: pageState.createJob, isPending: false },
    cancelJob: { mutateAsync: pageState.cancelJob, isPending: false },
    retryJob: { mutateAsync: pageState.retryJob, isPending: false },
  }),
}));

beforeEach(() => {
  vi.clearAllMocks();
  scrollMemory.clear();
  pageState.workbench.current_job = null;
  pageState.workbench.recent_job = null;
  pageState.createJob.mockResolvedValue({ job_id: 'job-created' });
  pageState.cancelJob.mockResolvedValue({ job_id: 'job-active' });
  pageState.retryJob.mockResolvedValue({ job_id: 'job-retry' });
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
  it('shows source first when no lesson exists and submits generation inline', async () => {
    const user = userEvent.setup();
    const onGenerate = vi.fn().mockResolvedValue(undefined);
    render(
      <BookReader
        title="足球如何成为全球运动"
        view="source"
        material={emptyMaterial}
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

  it('keeps a successful lesson readable while switching to its source', () => {
    const onViewChange = vi.fn();
    const { rerender } = render(
      <BookReader
        title="足球如何成为全球运动"
        view="material"
        material={readyMaterial}
        source={source}
        onViewChange={onViewChange}
        onGenerate={vi.fn()}
      />,
    );

    expect(screen.getByText('这是一份已经提交的讲义。')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: '原文' }));
    expect(onViewChange).toHaveBeenCalledWith('source');

    rerender(
      <BookReader
        title="足球如何成为全球运动"
        view="source"
        material={readyMaterial}
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

describe('TextbookWorkbenchPage', () => {
  it('chooses the first KP and source view when the URL has no selection', async () => {
    renderWorkbench();

    await waitFor(() => {
      expect(screen.getByTestId('location')).toHaveTextContent('?kp=sports-global-game&view=source');
    });
    expect(screen.getByRole('heading', { name: '足球如何成为全球运动' })).toBeInTheDocument();
  });

  it('loads bounded context around the selected source anchor', async () => {
    renderWorkbench('/textbooks/book-1?kp=sports-global-game&view=source');

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
    renderWorkbench('/textbooks/book-1?node=appendix&view=source');

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Vocabulary Index' })).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: '生成讲义' })).not.toBeInTheDocument();
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
});
