import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import i18n from '@/i18n';

const state = vi.hoisted(() => ({
  document: {} as Record<string, unknown>,
  jobs: {} as Record<string, unknown>,
  artifacts: {} as Record<string, unknown>,
  teachingUsage: {} as Record<string, unknown>,
  fetchArtifactText: vi.fn(),
  sourceDialogOpen: false,
}));

vi.mock('../hooks', () => ({
  useDocument: () => state.document,
  useDocumentJobs: () => state.jobs,
  useDocumentArtifacts: () => state.artifacts,
  useDocumentTeachingUsage: () => state.teachingUsage,
}));
vi.mock('../api', () => ({
  documentSourceUrl: (id: string) => `/api/v1/documents/${id}/source`,
  artifactDownloadUrl: (id: string) => `/api/v1/document-artifacts/${id}/download`,
  fetchArtifactText: (...args: unknown[]) => state.fetchArtifactText(...args),
}));
vi.mock('@/pages/ChatAgent/components/Markdown', () => ({
  default: ({ content }: { content: string }) => <div>{content}</div>,
}));
vi.mock('@/pages/ChatAgent/components/viewers/PreviewViewer', () => ({
  default: ({ isDragging }: { isDragging?: boolean }) => (
    <div data-testid="preview-viewer" data-dragging={String(Boolean(isDragging))}>Preview viewer</div>
  ),
}));
vi.mock('@/pages/Education/components/BookSourceDialog', () => ({
  BookSourceDialog: ({ open }: { open: boolean }) => {
    state.sourceDialogOpen = open;
    return open ? <div role="dialog" aria-label="教材来源" /> : null;
  },
}));

import DocumentDetailPage from '../DocumentDetailPage';

const document = {
  document_id: 'doc-1',
  original_filename: 'lesson.pdf',
  media_type: 'application/pdf',
  document_format: 'pdf',
  source_size_bytes: 1024,
  source_sha256: 'a'.repeat(64),
  datasets: [],
  tags: [],
  parse_status: 'completed',
};

const usage = (overrides: Record<string, unknown> = {}) => ({
  document_id: 'doc-1',
  parse_job_id: 'job-1',
  primary_artifact_id: 'art-markdown',
  textbook_id: 'textbook-1',
  textbook_title: 'Reading Explorer 3',
  source_filename: 'lesson.pdf',
  source_completed_at: '2026-09-16T12:00:00Z',
  structure_status: 'ready',
  materials: { ready: 4, total: 7 },
  updated_at: '2026-10-02T12:00:00Z',
  ...overrides,
});

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/documents/doc-1']} future={{ v7_startTransition: true }}>
      <Routes>
        <Route path="/documents/:documentId" element={<DocumentDetailPage />} />
        <Route
          path="/textbooks/:textbookId"
          element={<output data-testid="textbook-route">textbook detail route</output>}
        />
      </Routes>
    </MemoryRouter>,
  );
}

beforeAll(async () => {
  await i18n.changeLanguage('zh-CN');
});

afterAll(async () => {
  await i18n.changeLanguage('en-US');
});

beforeEach(() => {
  vi.clearAllMocks();
  state.document = { data: document, isLoading: false, isError: false, refetch: vi.fn() };
  state.jobs = { data: [{ job_id: 'job-1', status: 'completed' }], isLoading: false, isError: false };
  state.artifacts = {
    data: [
      {
        artifact_id: 'art-markdown',
        producer_job_id: 'job-1',
        artifact_kind: 'primary_document',
        format: 'markdown',
        media_type: 'text/markdown',
        relative_path: 'lesson.md',
      },
      {
        artifact_id: 'art-image',
        producer_job_id: 'job-1',
        artifact_kind: 'embedded_image',
        format: 'png',
        media_type: 'image/png',
        relative_path: 'figure.png',
      },
    ],
    isLoading: false,
    isError: false,
  };
  state.teachingUsage = { data: [], isLoading: false, isError: false, refetch: vi.fn() };
  state.fetchArtifactText.mockResolvedValue('# Lesson');
  state.sourceDialogOpen = false;
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true,
    arrayBuffer: async () => new ArrayBuffer(8),
  }));
});

describe('DocumentDetailPage', () => {
  it('renders the independent document route with three sections', async () => {
    renderPage();

    expect(screen.getByRole('heading', { name: 'lesson.pdf' })).toBeInTheDocument();
    expect(screen.getByText('已完成')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '原文' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: '解析结果' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '教材资产' })).toBeInTheDocument();
    expect(await screen.findByTestId('preview-viewer')).toBeInTheDocument();
    expect(screen.getByTestId('preview-viewer')).toHaveAttribute('data-dragging', 'false');
  });

  it('opens the shared source picker for a completed document', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('button', { name: '用作教材' }));

    expect(screen.getByRole('dialog', { name: '教材来源' })).toBeInTheDocument();
    expect(state.sourceDialogOpen).toBe(true);
  });

  it('shows parsed Markdown with artifact-backed images', async () => {
    state.fetchArtifactText.mockResolvedValue('![figure](figure.png)');
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('tab', { name: '解析结果' }));

    expect(await screen.findByText(/api\/v1\/document-artifacts\/art-image\/download/)).toBeInTheDocument();
    expect(state.fetchArtifactText).toHaveBeenCalledWith('art-markdown');
  });

  it('shows fixed sources and committed material counts with workbench links', async () => {
    state.teachingUsage = {
      data: [
        usage(),
        usage({
          textbook_id: 'textbook-2',
          textbook_title: 'Active Reader',
          parse_job_id: 'job-2',
          primary_artifact_id: 'art-published',
          structure_status: 'running',
          materials: { ready: 1, total: 5 },
        }),
      ],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    };
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('tab', { name: '教材资产' }));

    expect(screen.getByRole('link', { name: 'Reading Explorer 3' })).toHaveAttribute(
      'href',
      '/textbooks/textbook-1',
    );
    expect(screen.getByRole('link', { name: 'Active Reader' })).toHaveAttribute(
      'href',
      '/textbooks/textbook-2',
    );
    expect(screen.getByText('结构已就绪')).toBeInTheDocument();
    expect(screen.getByText('正在分析结构')).toBeInTheDocument();
    expect(screen.getByText('讲义 4 / 7')).toBeInTheDocument();
    expect(screen.getByText('讲义 1 / 5')).toBeInTheDocument();
    expect(screen.getByText('解析产物 art-markdown')).toBeInTheDocument();
    expect(screen.getByText('解析任务 job-1')).toBeInTheDocument();
    expect(screen.getByText('解析产物 art-published')).toBeInTheDocument();
    expect(screen.getByText('解析任务 job-2')).toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: '打开教材' })).toHaveLength(2);

    await user.click(screen.getByRole('link', { name: 'Reading Explorer 3' }));
    expect(screen.getByTestId('textbook-route')).toBeInTheDocument();
  });

  it('shows failed and queued structure states without publication language', async () => {
    state.teachingUsage = {
      data: [
        usage({
          textbook_id: 'textbook-failed',
          textbook_title: 'Failed Reader',
          structure_status: 'failed',
        }),
        usage({
          textbook_id: 'textbook-queued',
          textbook_title: 'Queued Reader',
          structure_status: 'queued',
        }),
      ],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    };
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('tab', { name: '教材资产' }));

    expect(screen.getByText('结构加工失败')).toBeInTheDocument();
    expect(screen.getByText('等待结构分析')).toBeInTheDocument();
    expect(screen.queryByText(/版本|发布|知识包/)).not.toBeInTheDocument();
  });

  it('does not render storage keys, snapshots, sandbox paths, or object URLs', async () => {
    state.teachingUsage = {
      data: [
        usage({
          storage_key: 'education/private/secret.pdf',
          snapshot_prefix: 'education/household/source-bundles/private/',
          sandbox_path: '/managed/textbook-job/private',
          object_url: 'https://minio.invalid/education/private/secret.pdf',
        }),
      ],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    };
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('tab', { name: '教材资产' }));

    expect(screen.getByText('解析产物 art-markdown')).toBeInTheDocument();
    expect(screen.getByText('解析任务 job-1')).toBeInTheDocument();
    expect(screen.queryByText(/education\/private|source-bundles|\/managed\/|minio\.invalid/i)).not.toBeInTheDocument();
  });

  it('supports arrow, Home, and End keyboard navigation across detail tabs', async () => {
    const user = userEvent.setup();
    renderPage();

    const sourceTab = screen.getByRole('tab', { name: '原文' });
    const parsedTab = screen.getByRole('tab', { name: '解析结果' });
    const teachingTab = screen.getByRole('tab', { name: '教材资产' });

    sourceTab.focus();
    await user.keyboard('{ArrowRight}');
    expect(parsedTab).toHaveFocus();
    expect(parsedTab).toHaveAttribute('aria-selected', 'true');

    await user.keyboard('{End}');
    expect(teachingTab).toHaveFocus();
    expect(teachingTab).toHaveAttribute('aria-selected', 'true');

    await user.keyboard('{Home}');
    expect(sourceTab).toHaveFocus();
    expect(sourceTab).toHaveAttribute('aria-selected', 'true');

    await user.keyboard('{ArrowLeft}');
    expect(teachingTab).toHaveFocus();
    expect(teachingTab).toHaveAttribute('aria-selected', 'true');
  });

  it('shows the document loading state', () => {
    state.document = { data: undefined, isLoading: true, isError: false, refetch: vi.fn() };

    renderPage();

    expect(screen.getByRole('status')).toHaveTextContent('正在加载文档');
  });

  it('shows a retryable document error state', async () => {
    const refetch = vi.fn();
    state.document = { data: undefined, isLoading: false, isError: true, refetch };
    const user = userEvent.setup();
    renderPage();

    expect(screen.getByRole('alert')).toHaveTextContent('无法加载文档');
    await user.click(screen.getByRole('button', { name: '重试' }));
    expect(refetch).toHaveBeenCalledOnce();
  });

  it('shows an empty teaching usage state', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('tab', { name: '教材资产' }));

    expect(screen.getByText('这份文档尚未用于教材加工。')).toBeInTheDocument();
  });

  it('shows a teaching usage loading state', async () => {
    state.teachingUsage = { data: undefined, isLoading: true, isError: false, refetch: vi.fn() };
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('tab', { name: '教材资产' }));

    expect(screen.getByRole('status')).toHaveTextContent('正在加载教材使用情况');
  });

  it('shows a retryable teaching usage error state', async () => {
    const refetch = vi.fn();
    state.teachingUsage = { data: undefined, isLoading: false, isError: true, refetch };
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('tab', { name: '教材资产' }));

    expect(screen.getByRole('alert')).toHaveTextContent('无法加载教材使用情况');
    await user.click(screen.getByRole('button', { name: '重试' }));
    expect(refetch).toHaveBeenCalledOnce();
  });

  it('shows a parsed empty state when no Markdown artifact exists', async () => {
    state.artifacts = { data: [], isLoading: false, isError: false };
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('tab', { name: '解析结果' }));

    expect(screen.getByText('这份文档还没有可预览的 Markdown 解析产物。')).toBeInTheDocument();
  });
});
