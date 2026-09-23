import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import TextbookDetailPage from '../TextbookDetailPage';

const state = vi.hoisted(() => ({
  textbook: null as Record<string, unknown> | null,
  structure: null as Record<string, unknown> | null,
  parseJobs: [] as Array<Record<string, unknown>>,
  parseJobsError: false,
  refetchParseJobs: vi.fn(),
  start: vi.fn(),
  run: vi.fn(),
  retry: vi.fn(),
  assign: vi.fn(),
  publishStructure: vi.fn(),
}));

vi.mock('../api', () => ({
  getEducationAssetDownloadUrl: vi.fn(),
}));

vi.mock('../queries', () => ({
  useCompletedParseJobs: () => ({
    data: state.parseJobs,
    isLoading: false,
    isError: state.parseJobsError,
    refetch: state.refetchParseJobs,
  }),
  useEducationMembers: () => ({ data: [] }),
  useLatestTextbookStructure: () => ({
    data: state.structure,
    isLoading: false,
  }),
  useTextbook: () => ({ data: state.textbook, isLoading: false }),
  useTextbookMutations: () => ({
    start: { mutateAsync: state.start, isPending: false },
    run: { mutateAsync: state.run, isPending: false },
    retry: { mutateAsync: state.retry, isPending: false },
    assign: { mutateAsync: state.assign, isPending: false },
  }),
  useStructureMutations: () => ({
    publish: { mutateAsync: state.publishStructure, isPending: false },
  }),
}));

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/textbooks/textbook-1']}>
      <Routes>
        <Route path="/textbooks/:textbookId" element={<TextbookDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

function version(overrides: Record<string, unknown> = {}) {
  return {
    version_id: 'version-1',
    sequence: 1,
    status: 'review',
    extractor_name: 'managed_ptc',
    extractor_version: '1',
    processing_job_id: null,
    processing_job_status: null,
    processing_error: null,
    chapter_count: 1,
    is_published: false,
    publication_id: null,
    sources: [],
    chapters: [],
    assignments: [],
    ...overrides,
  };
}

function structure(overrides: Record<string, unknown> = {}) {
  return {
    structure_id: 'structure-1',
    version_id: 'version-1',
    sequence: 1,
    status: 'review',
    schema_version: 'langalpha-managed-textbook-structure/v1',
    processing_profile_sha256: 'a'.repeat(64),
    input_manifest_sha256: 'b'.repeat(64),
    source_revision: 'c'.repeat(64),
    units: [],
    lesson_summary: {
      total: 4,
      accepted: 4,
      generated: 4,
      approved: 2,
    },
    ...overrides,
  };
}

beforeEach(() => {
  state.textbook = {
    textbook_id: 'textbook-1',
    household_id: 'household-1',
    title: '英语第二册',
    slug: 'english-2',
    versions: [],
  };
  state.structure = null;
  state.parseJobs = [
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
      parse_completed_at: '2026-08-13T00:00:00Z',
      size_bytes: 1024,
      artifact_count: 3,
    },
  ];
  state.parseJobsError = false;
  state.refetchParseJobs.mockReset();
  state.start.mockReset().mockResolvedValue({ job_id: 'job-1' });
  state.run.mockReset().mockResolvedValue(undefined);
  state.retry.mockReset().mockResolvedValue(undefined);
  state.assign.mockReset().mockResolvedValue(undefined);
  state.publishStructure.mockReset().mockResolvedValue({ publication_id: 'publication-1' });
});

describe('TextbookDetailPage', () => {
  it('creates a frozen content version from library parse jobs', async () => {
    const user = userEvent.setup();
    renderPage();

    expect(screen.getByRole('heading', { name: '第一步：准备教材内容' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '选择教材来源' }));
    await user.click(screen.getByRole('checkbox', { name: 'body.pdf' }));
    await user.click(screen.getByRole('button', { name: '创建教材内容' }));

    await waitFor(() =>
      expect(state.start).toHaveBeenCalledWith({
        textbookId: 'textbook-1',
        sourceParseJobIds: ['job-parse-1'],
      }),
    );
  });

  it('only closes the source picker from its close button', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('button', { name: '选择教材来源' }));
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    fireEvent.pointerDown(document.body);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Close' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('shows the four workflow steps and links review versions to unified processing', () => {
    state.textbook = {
      ...state.textbook,
      versions: [version()],
    };
    renderPage();

    expect(screen.getByTestId('textbook-workflow-stepper')).toBeInTheDocument();
    expect(screen.getByText('内容准备')).toBeInTheDocument();
    expect(screen.getByText('结构分析')).toBeInTheDocument();
    expect(screen.getByText('知识点课程')).toBeInTheDocument();
    expect(screen.getByText('发布')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '开始处理' })).toHaveAttribute(
      'href',
      '/textbooks/textbook-1/versions/version-1/processing',
    );
  });

  it('links an existing book pipeline job back to its status page', () => {
    state.textbook = {
      ...state.textbook,
      versions: [
        version({
          processing_job_id: 'book-job-1',
          processing_job_scope: 'book_pipeline',
          processing_job_status: 'failed',
          processing_error: 'invalid package',
        }),
      ],
    };
    renderPage();

    expect(screen.getByText('加工失败')).toBeInTheDocument();
    expect(screen.getByText('invalid package')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '查看处理状态' })).toHaveAttribute(
      'href',
      '/textbooks/textbook-1/versions/version-1/processing?job=book-job-1',
    );
    expect(
      screen.queryByRole('link', { name: '开始处理' }),
    ).not.toBeInTheDocument();
  });

  it('shows lesson progress from the latest structure', () => {
    state.textbook = {
      ...state.textbook,
      versions: [version()],
    };
    state.structure = structure({ status: 'accepted' });
    renderPage();

    expect(screen.getByText('知识点 4/4 已接受，课程 2/4 已通过。')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '查看知识点课程' })).toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: '确认知识点候选' }),
    ).not.toBeInTheDocument();
  });

  it('uses the candidate review entry and generic summary for a content tree', () => {
    state.textbook = {
      ...state.textbook,
      versions: [version()],
    };
    state.structure = structure({
      schema_version: 'langalpha-book-content-tree/v1',
      status: 'review',
      lesson_summary: {
        total: 3,
        accepted: 1,
        generated: 0,
        approved: 0,
      },
    });
    renderPage();

    expect(screen.getByText('知识点 1/3 已接受，课程 0/3 已通过。')).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: '确认知识点候选' }),
    ).toHaveAttribute(
      'href',
      '/textbooks/textbook-1/versions/version-1/candidates',
    );
    expect(
      screen.queryByRole('link', { name: '审阅结构与知识点' }),
    ).not.toBeInTheDocument();
  });

  it('publishes only after every accepted knowledge point has an approved lesson', async () => {
    const user = userEvent.setup();
    state.textbook = {
      ...state.textbook,
      versions: [version()],
    };
    state.structure = structure({
      status: 'accepted',
      lesson_summary: {
        total: 4,
        accepted: 4,
        generated: 4,
        approved: 4,
      },
    });
    renderPage();

    await user.click(screen.getByRole('button', { name: '发布教材' }));
    await waitFor(() =>
      expect(state.publishStructure).toHaveBeenCalledWith({
        versionId: 'version-1',
        structureId: 'structure-1',
      }),
    );
  });

  it('runs and retries the content-preparation stage from the stepper', async () => {
    const user = userEvent.setup();
    state.textbook = {
      ...state.textbook,
      versions: [
        version({
          status: 'processing',
          processing_job_id: 'processing-1',
          processing_job_status: 'queued',
        }),
      ],
    };
    const view = renderPage();
    await user.click(screen.getByRole('button', { name: '执行内容准备' }));
    await waitFor(() => expect(state.run).toHaveBeenCalledWith('processing-1'));
    view.unmount();

    state.textbook = {
      ...state.textbook,
      versions: [
        version({
          status: 'failed',
          processing_job_id: 'processing-1',
          processing_job_status: 'failed',
        }),
      ],
    };
    renderPage();
    await user.click(screen.getByRole('button', { name: '重试内容准备' }));
    await waitFor(() => expect(state.retry).toHaveBeenCalledWith('processing-1'));
  });

  it('shows a retry action when parse jobs cannot be loaded', async () => {
    state.parseJobsError = true;
    renderPage();

    fireEvent.click(screen.getByRole('button', { name: '选择教材来源' }));
    expect(screen.getByRole('alert')).toHaveTextContent('无法加载已完成解析的资料');
    fireEvent.click(screen.getByRole('button', { name: '重试' }));
    expect(state.refetchParseJobs).toHaveBeenCalled();
  });
});
