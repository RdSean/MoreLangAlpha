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
  producer_job_id: 'job-1',
  primary_artifact_id: 'art-markdown',
  textbook_id: 'textbook-1',
  textbook_title: 'Reading Explorer 3',
  content_version_id: 'version-1',
  content_version_sequence: 2,
  artifact_position: 1,
  teaching_package_id: 'package-1',
  teaching_package_sequence: 1,
  status: 'review',
  publication_id: null,
  is_published: false,
  has_asset_manifest: true,
  created_at: '2026-09-16T12:00:00Z',
  ...overrides,
});

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/documents/doc-1']} future={{ v7_startTransition: true }}>
      <Routes>
        <Route path="/documents/:documentId" element={<DocumentDetailPage />} />
        <Route
          path="/education/textbooks/:textbookId"
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

  it('shows parsed Markdown with artifact-backed images', async () => {
    state.fetchArtifactText.mockResolvedValue('![figure](figure.png)');
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('tab', { name: '解析结果' }));

    expect(await screen.findByText(/api\/v1\/document-artifacts\/art-image\/download/)).toBeInTheDocument();
    expect(state.fetchArtifactText).toHaveBeenCalledWith('art-markdown');
  });

  it('shows review and publication-backed published usages and links formal assets to textbook detail', async () => {
    state.teachingUsage = {
      data: [
        usage(),
        usage({
          textbook_id: 'textbook-2',
          textbook_title: 'Published Reader',
          content_version_id: 'version-2',
          content_version_sequence: 3,
          producer_job_id: 'job-2',
          primary_artifact_id: 'art-published',
          teaching_package_id: 'package-2',
          teaching_package_sequence: 2,
          status: 'review',
          publication_id: 'publication-2',
          is_published: true,
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
      '/education/textbooks/textbook-1',
    );
    expect(screen.getByRole('link', { name: 'Published Reader' })).toHaveAttribute(
      'href',
      '/education/textbooks/textbook-2',
    );
    expect(screen.getByText('内容版本 v2')).toBeInTheDocument();
    expect(screen.getByText('内容版本 v3')).toBeInTheDocument();
    expect(screen.getByText('教学包 #1')).toBeInTheDocument();
    expect(screen.getByText('教学包 #2')).toBeInTheDocument();
    expect(screen.getByText('等待审阅')).toBeInTheDocument();
    expect(screen.getByText('已发布')).toBeInTheDocument();
    expect(screen.getByText('解析产物 art-markdown')).toBeInTheDocument();
    expect(screen.getByText('解析任务 job-1')).toBeInTheDocument();
    expect(screen.getByText('解析产物 art-published')).toBeInTheDocument();
    expect(screen.getByText('解析任务 job-2')).toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: '查看正式教材资产' })).toHaveLength(2);

    await user.click(screen.getByRole('link', { name: 'Reading Explorer 3' }));
    expect(screen.getByTestId('textbook-route')).toBeInTheDocument();
  });

  it('shows unpackaged, failed, and cancelled usages without asset links', async () => {
    state.teachingUsage = {
      data: [
        usage({
          teaching_package_id: null,
          teaching_package_sequence: null,
          status: null,
          has_asset_manifest: false,
        }),
        usage({
          textbook_id: 'textbook-failed',
          textbook_title: 'Failed Reader',
          teaching_package_id: 'package-failed',
          status: 'failed',
          has_asset_manifest: true,
        }),
        usage({
          textbook_id: 'textbook-cancelled',
          textbook_title: 'Cancelled Reader',
          teaching_package_id: 'package-cancelled',
          status: 'cancelled',
          has_asset_manifest: true,
        }),
      ],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    };
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('tab', { name: '教材资产' }));

    expect(screen.getByText('尚未生成教学包')).toBeInTheDocument();
    expect(screen.getByText('教学包加工失败')).toBeInTheDocument();
    expect(screen.getByText('教学包加工已取消')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '查看正式教材资产' })).not.toBeInTheDocument();
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
