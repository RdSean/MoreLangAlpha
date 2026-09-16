import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import TextbookDetailPage from '../TextbookDetailPage';

const defaultMatchMedia = window.matchMedia;

function setViewport(width: number) {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: width });
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: query === '(max-width: 767px)' ? width < 768 : false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })) as typeof window.matchMedia;
}

const state = vi.hoisted(() => ({
  textbook: null as Record<string, unknown> | null,
  parseJobs: [] as Array<Record<string, unknown>>,
  getAssetUrl: vi.fn(),
  start: vi.fn(),
  run: vi.fn(),
  retry: vi.fn(),
  createTeaching: vi.fn(),
  cancelTeaching: vi.fn(),
  resumeTeaching: vi.fn(),
  teachingJob: null as Record<string, unknown> | null,
  teachingAssets: null as Record<string, unknown> | null,
  teachingAsset: null as Record<string, unknown> | null,
  publish: vi.fn(),
  assign: vi.fn(),
}));

vi.mock('../api', () => ({
  uploadEducationAsset: vi.fn(),
  getEducationAssetDownloadUrl: state.getAssetUrl,
}));

vi.mock('../queries', () => ({
  useCompletedParseJobs: () => ({ data: state.parseJobs, isLoading: false }),
  useEducationMembers: () => ({ data: [] }),
  useParentLearningRecords: () => ({ data: { records: [] }, isLoading: false }),
  useParentLearningTranscript: () => ({ data: { messages: [] }, isLoading: false }),
  useTextbook: () => ({ data: state.textbook, isLoading: false }),
  useTeachingJob: () => ({ data: state.teachingJob }),
  useTeachingPackageAssets: () => ({ data: state.teachingAssets, isLoading: false }),
  useTeachingChapterAsset: () => ({ data: state.teachingAsset, isLoading: false }),
  useTextbookMutations: () => ({
    start: { mutateAsync: state.start, isPending: false },
    run: { mutateAsync: state.run, isPending: false },
    retry: { mutateAsync: state.retry, isPending: false },
    createTeaching: { mutateAsync: state.createTeaching, isPending: false },
    cancelTeaching: { mutateAsync: state.cancelTeaching, isPending: false },
    resumeTeaching: { mutateAsync: state.resumeTeaching, isPending: false },
    publish: { mutateAsync: state.publish, isPending: false },
    assign: { mutateAsync: state.assign, isPending: false },
  }),
}));

beforeEach(() => {
  window.matchMedia = defaultMatchMedia;
  state.textbook = {
    textbook_id: 'textbook-1',
    household_id: 'household-1',
    title: '英语第二册',
    slug: 'english-2',
    versions: [],
  };
  state.parseJobs = [
    { producer_job_id: 'job-parse-1', document_id: 'doc-1', primary_artifact_id: 'art-1', filename: 'body.pdf', media_type: 'application/pdf', format: 'pdf', parser_id: 'datalab', parser_name: 'Datalab', parser_version: '2', parse_completed_at: '2026-08-13T00:00:00Z', size_bytes: 1024, artifact_count: 3 },
    { producer_job_id: 'job-parse-2', document_id: 'doc-2', primary_artifact_id: 'art-2', filename: 'workbook.pdf', media_type: 'application/pdf', format: 'pdf', parser_id: 'datalab', parser_name: 'Datalab', parser_version: '2', parse_completed_at: '2026-08-13T00:01:00Z', size_bytes: 2048, artifact_count: 5 },
  ];
  state.start.mockReset().mockResolvedValue({ job_id: 'job-1' });
  state.getAssetUrl.mockReset().mockResolvedValue('https://storage.test/legacy.pdf');
  state.run.mockReset();
  state.retry.mockReset();
  state.createTeaching.mockReset();
  state.cancelTeaching.mockReset();
  state.resumeTeaching.mockReset();
  state.teachingJob = null;
  state.teachingAssets = null;
  state.teachingAsset = null;
  state.publish.mockReset();
  state.assign.mockReset();
});

describe('TextbookDetailPage', () => {
  it('shows the first source and processing action for a newly created draft', () => {
    render(
      <MemoryRouter initialEntries={['/education/textbooks/textbook-1']}>
        <Routes><Route path="/education/textbooks/:textbookId" element={<TextbookDetailPage />} /></Routes>
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading', { name: '下一步：从图书馆选择来源' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '开始加工' })).toBeInTheDocument();
  });

  it('lists completed parse jobs and submits their parse job IDs', async () => {
    render(
      <MemoryRouter initialEntries={['/education/textbooks/textbook-1']}>
        <Routes><Route path="/education/textbooks/:textbookId" element={<TextbookDetailPage />} /></Routes>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', { name: '开始加工' }));
    expect(screen.getByText('从图书馆选择来源')).toBeInTheDocument();
    expect(screen.getByText(/body.pdf/)).toBeInTheDocument();
    expect(screen.getAllByText(/Datalab/)).toHaveLength(2);
    fireEvent.click(screen.getByRole('checkbox', { name: 'body.pdf' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'workbook.pdf' }));
    fireEvent.click(screen.getByRole('button', { name: '创建加工任务' }));

    await waitFor(() => expect(state.start).toHaveBeenCalledWith({
      textbookId: 'textbook-1',
      sourceParseJobIds: ['job-parse-1', 'job-parse-2'],
    }));
  });

  it('shows artifact and legacy sources truthfully in the source tab', () => {
    state.textbook = {
      textbook_id: 'textbook-1',
      household_id: 'household-1',
      title: '英语第二册',
      slug: 'english-2',
      versions: [{
        version_id: 'version-1',
        sequence: 1,
        status: 'review',
        chapter_count: 1,
        is_published: false,
        sources: [
          {
            legacy: false,
            position: 1,
            document_id: 'doc-1',
            producer_job_id: 'job-parse-1',
            primary_artifact_id: 'art-1',
            filename: 'body.pdf',
            media_type: 'application/pdf',
            format: 'pdf',
            parser_id: 'datalab',
            parser_name: 'Datalab',
            parser_version: '2',
            parse_completed_at: '2026-09-16T10:00:00Z',
            primary_sha256: 'abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890',
            document_deleted: false,
            document_accessible: true,
            snapshot_prefix: 'education/private/secret/',
          },
          {
            legacy: false,
            position: 2,
            document_id: 'doc-deleted',
            producer_job_id: 'job-parse-2',
            primary_artifact_id: 'art-2',
            filename: 'deleted.pdf',
            media_type: 'application/pdf',
            format: 'pdf',
            parser_id: 'datalab',
            parser_name: 'Datalab',
            parser_version: '2',
            parse_completed_at: '2026-09-16T10:01:00Z',
            primary_sha256: 'fedcba0987654321fedcba0987654321fedcba0987654321fedcba0987654321',
            document_deleted: true,
            document_accessible: false,
            storage_key: 'documents/private/deleted.md',
          },
          {
            legacy: false,
            position: 3,
            document_id: 'doc-restricted',
            producer_job_id: 'job-parse-3',
            primary_artifact_id: 'art-3',
            filename: 'restricted.pdf',
            media_type: 'application/pdf',
            format: 'pdf',
            parser_id: 'datalab',
            parser_name: 'Datalab',
            parser_version: '2',
            parse_completed_at: '2026-09-16T10:02:00Z',
            primary_sha256: '1'.repeat(64),
            document_deleted: false,
            document_accessible: false,
          },
          {
            legacy: true,
            position: 4,
            asset_id: 'asset-1',
            original_filename: 'legacy.pdf',
            content_type: 'application/pdf',
            size_bytes: 1024,
          },
        ],
        assignments: [],
        chapters: [{
          chapter_id: 'chapter-1',
          position: 1,
          slug: 'introduction',
          title: '导读',
          page_start: 1,
          page_end: 10,
          markdown: '# 导读\n\n原始提取内容。',
          teaching_material: '# 学习目标\n\n完成阅读。',
          questions: [{ question_id: 'question-1', position: 1, prompt: '完成阅读后做什么？', options: { A: '知识检查' }, correct_option: 'A', explanation: '需要检查', knowledge_point: '学习证据' }],
        }],
      }],
    };

    render(
      <MemoryRouter initialEntries={['/education/textbooks/textbook-1']}>
        <Routes><Route path="/education/textbooks/:textbookId" element={<TextbookDetailPage />} /></Routes>
      </MemoryRouter>,
    );

    expect(screen.queryByRole('tab', { name: '内容' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: '来源' }));
    expect(screen.getByRole('link', { name: '查看 body.pdf' })).toHaveAttribute('href', '/documents/doc-1');
    expect(screen.getAllByText(/Datalab/)).toHaveLength(3);
    expect(screen.getByText(/abcdef123456/)).toBeInTheDocument();
    expect(screen.getByText('原文档已删除')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '查看 deleted.pdf' })).not.toBeInTheDocument();
    expect(screen.getByText('原文档不可访问')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '查看 restricted.pdf' })).not.toBeInTheDocument();
    expect(screen.getByText('legacy.pdf')).toBeInTheDocument();
    expect(screen.getByText('旧版资料')).toBeInTheDocument();
    expect(screen.queryByText(/education\/private|documents\/private|storage_key|snapshot_prefix/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: '教学' }));
    expect(screen.getByText(/完成阅读。/)).toBeInTheDocument();
    expect(screen.getByText(/完成阅读后做什么？/)).toBeInTheDocument();
  });

  it('keeps frozen sources and library links visible after a run failure', () => {
    state.textbook = {
      textbook_id: 'textbook-1',
      household_id: 'household-1',
      title: '英语第二册',
      slug: 'english-2',
      versions: [{
        version_id: 'version-1',
        sequence: 1,
        status: 'failed',
        processing_error: '本地加工失败，未找到 sandbox。',
        processing_job_status: 'failed',
        chapter_count: 0,
        is_published: false,
        sources: [{
          legacy: false,
          position: 1,
          document_id: 'doc-1',
          producer_job_id: 'job-parse-1',
          primary_artifact_id: 'art-1',
          filename: 'body.pdf',
          media_type: 'application/pdf',
          format: 'pdf',
          parser_id: 'datalab',
          parser_name: 'Datalab',
          parser_version: '2',
          parse_completed_at: '2026-09-16T10:00:00Z',
          primary_sha256: 'a'.repeat(64),
          document_deleted: false,
          document_accessible: true,
        }],
        assignments: [],
        teaching_packages: [],
        chapters: [],
      }],
    };

    render(
      <MemoryRouter initialEntries={['/education/textbooks/textbook-1']}>
        <Routes><Route path="/education/textbooks/:textbookId" element={<TextbookDetailPage />} /></Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText(/本地加工失败/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: '来源' }));
    expect(screen.getByRole('link', { name: '查看 body.pdf' })).toHaveAttribute('href', '/documents/doc-1');
  });

  it('opens legacy sources through the existing download action', async () => {
    state.textbook = {
      textbook_id: 'textbook-1',
      household_id: 'household-1',
      title: '英语第二册',
      slug: 'english-2',
      versions: [{
        version_id: 'version-1',
        sequence: 1,
        status: 'review',
        chapter_count: 1,
        is_published: false,
        sources: [{
          legacy: true,
          position: 1,
          asset_id: 'asset-legacy-1',
          original_filename: 'legacy.pdf',
          content_type: 'application/pdf',
          size_bytes: 1024,
        }],
        assignments: [],
        teaching_packages: [],
        chapters: [],
      }],
    };
    const open = vi.spyOn(window, 'open').mockReturnValue(null);
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={['/education/textbooks/textbook-1']}>
        <Routes><Route path="/education/textbooks/:textbookId" element={<TextbookDetailPage />} /></Routes>
      </MemoryRouter>,
    );

    await user.click(screen.getByRole('tab', { name: '来源' }));
    await user.click(screen.getByRole('button', { name: '打开 legacy.pdf' }));

    await waitFor(() => expect(state.getAssetUrl).toHaveBeenCalledWith('asset-legacy-1'));
    expect(open).toHaveBeenCalledWith('https://storage.test/legacy.pdf', '_blank', 'noopener,noreferrer');
    open.mockRestore();
  });

  it('provides complete tab semantics and keyboard navigation', async () => {
    state.textbook = {
      textbook_id: 'textbook-1',
      household_id: 'household-1',
      title: '英语第二册',
      slug: 'english-2',
      versions: [{
        version_id: 'version-1',
        sequence: 1,
        status: 'review',
        chapter_count: 1,
        is_published: false,
        sources: [],
        assignments: [],
        teaching_packages: [],
        chapters: [],
      }],
    };
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={['/education/textbooks/textbook-1']}>
        <Routes><Route path="/education/textbooks/:textbookId" element={<TextbookDetailPage />} /></Routes>
      </MemoryRouter>,
    );

    const overviewTab = screen.getByRole('tab', { name: '概览' });
    const sourcesTab = screen.getByRole('tab', { name: '来源' });
    const teachingTab = screen.getByRole('tab', { name: '教学' });
    const studentsTab = screen.getByRole('tab', { name: '学生' });
    const overviewPanel = screen.getByRole('tabpanel', { name: '概览' });

    expect(overviewTab).toHaveAttribute('aria-controls', overviewPanel.id);
    expect(overviewPanel).toHaveAttribute('aria-labelledby', overviewTab.id);
    expect(overviewTab).toHaveAttribute('tabindex', '0');
    expect(sourcesTab).toHaveAttribute('tabindex', '-1');
    for (const tab of [overviewTab, sourcesTab, teachingTab, screen.getByRole('tab', { name: '知识资产' }), studentsTab]) {
      const controlledPanel = document.getElementById(tab.getAttribute('aria-controls') ?? '');
      expect(controlledPanel).not.toBeNull();
      expect(controlledPanel).toHaveAttribute('aria-labelledby', tab.id);
    }
    expect(overviewPanel).not.toHaveAttribute('hidden');
    expect(document.getElementById(sourcesTab.getAttribute('aria-controls') ?? '')).toHaveAttribute('hidden');

    overviewTab.focus();
    await user.keyboard('{ArrowRight}');
    expect(sourcesTab).toHaveFocus();
    expect(sourcesTab).toHaveAttribute('aria-selected', 'true');
    expect(overviewTab).toHaveAttribute('tabindex', '-1');
    expect(screen.getByRole('tabpanel', { name: '来源' })).toHaveAttribute('aria-labelledby', sourcesTab.id);

    await user.keyboard('{ArrowRight}');
    expect(teachingTab).toHaveFocus();
    expect(teachingTab).toHaveAttribute('aria-selected', 'true');

    await user.keyboard('{End}');
    expect(studentsTab).toHaveFocus();
    expect(studentsTab).toHaveAttribute('aria-selected', 'true');

    await user.keyboard('{Home}');
    expect(overviewTab).toHaveFocus();
    expect(overviewTab).toHaveAttribute('aria-selected', 'true');

    await user.keyboard('{ArrowLeft}');
    expect(studentsTab).toHaveFocus();
    expect(studentsTab).toHaveAttribute('aria-selected', 'true');
  });

  it.each([
    { label: 'mobile', width: 375 },
    { label: 'desktop', width: 1280 },
  ])('keeps source structure accessible without horizontal overflow on $label', ({ width }) => {
    setViewport(width);
    state.textbook = {
      textbook_id: 'textbook-1',
      household_id: 'household-1',
      title: '英语第二册',
      slug: 'english-2',
      versions: [{
        version_id: 'version-1',
        sequence: 1,
        status: 'review',
        chapter_count: 1,
        is_published: false,
        sources: [{
          legacy: false,
          position: 1,
          document_id: 'doc-1',
          producer_job_id: 'job-parse-1',
          primary_artifact_id: 'art-1',
          filename: 'a-very-long-textbook-filename-that-must-wrap-instead-of-overflowing.pdf',
          media_type: 'application/pdf',
          format: 'pdf',
          parser_id: 'datalab',
          parser_name: 'Datalab',
          parser_version: '2',
          parse_completed_at: '2026-09-16T10:00:00Z',
          primary_sha256: 'a'.repeat(64),
          document_deleted: false,
          document_accessible: true,
        }],
        assignments: [],
        teaching_packages: [],
        chapters: [],
      }],
    };

    render(
      <MemoryRouter initialEntries={['/education/textbooks/textbook-1']}>
        <Routes><Route path="/education/textbooks/:textbookId" element={<TextbookDetailPage />} /></Routes>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('tab', { name: '来源' }));
    const panel = screen.getByTestId('textbook-sources-panel');
    const list = screen.getByRole('list', { name: '冻结来源' });
    const row = screen.getAllByRole('listitem')[0];

    expect(panel).toHaveClass('min-w-0');
    expect(panel).not.toHaveClass('overflow-x-auto');
    expect(list).toHaveClass('grid-cols-1');
    expect(row).toHaveClass('min-w-0', 'grid-cols-1', 'sm:grid-cols-[minmax(0,1fr)_auto]');
    expect(screen.getByText(/a-very-long-textbook-filename/)).toHaveClass('break-words');
    expect(screen.getByRole('link', { name: /查看 a-very-long-textbook-filename/ })).toBeInTheDocument();
  });

  it('starts a teaching package only after content extraction is reviewable', async () => {
    state.textbook = {
      textbook_id: 'textbook-1',
      household_id: 'household-1',
      title: '英语第二册',
      slug: 'english-2',
      versions: [{
        version_id: 'version-1',
        sequence: 1,
        status: 'review',
        chapter_count: 1,
        is_published: false,
        sources: [],
        assignments: [],
        teaching_packages: [],
        chapters: [{ chapter_id: 'chapter-1', position: 1, slug: 'overview', title: '导读', markdown: '# 导读', questions: [] }],
      }],
    };
    state.createTeaching.mockResolvedValue({ job_id: 'teaching-job-1' });

    render(
      <MemoryRouter initialEntries={['/education/textbooks/textbook-1']}>
        <Routes><Route path="/education/textbooks/:textbookId" element={<TextbookDetailPage />} /></Routes>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', { name: '生成教学包' }));

    await waitFor(() => expect(state.createTeaching).toHaveBeenCalledWith('version-1'));
  });

  it('reviews complete knowledge assets without rendering storage details', () => {
    state.textbook = {
      textbook_id: 'textbook-1', household_id: 'household-1', title: '英语第二册', slug: 'english-2',
      versions: [{
        version_id: 'version-1', sequence: 1, status: 'review', chapter_count: 1, is_published: false,
        sources: [], assignments: [],
        teaching_packages: [{
          teaching_package_id: 'package-1', job_id: 'job-1', sequence: 1, status: 'review', job_status: 'completed', chapter_count: 1, question_count: 2,
        }],
        chapters: [{ chapter_id: 'chapter-1', position: 1, slug: 'overview', title: '导读', markdown: '# 导读', questions: [] }],
      }],
    };
    state.teachingAssets = {
      teaching_package_id: 'package-1', format: 'langalpha-family-teaching-assets/v2',
      concept_index: { size_bytes: 120, concept_count: 3 },
      coverage_audit: { size_bytes: 80, status: 'complete' },
      chapters: [{
        chapter_id: 'chapter-1', position: 1, title: '导读', coverage_status: 'complete', concept_count: 3,
        assets: [{ kind: 'knowledge', size_bytes: 20 }, { kind: 'toolkit', size_bytes: 30 }, { kind: 'practice', size_bytes: 40 }],
      }],
      storage_key: 'education/private/manifest.json',
    };
    state.teachingAsset = {
      teaching_package_id: 'package-1', chapter_id: 'chapter-1', kind: 'toolkit', content: '# 导读工具包',
      managed_path: '/managed/textbook-job/private',
    };

    render(
      <MemoryRouter initialEntries={['/education/textbooks/textbook-1']}>
        <Routes><Route path="/education/textbooks/:textbookId" element={<TextbookDetailPage />} /></Routes>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('tab', { name: '知识资产' }));
    expect(screen.getByText('覆盖审计通过')).toBeInTheDocument();
    expect(screen.getByText('3 个概念')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '查看工具包' }));
    expect(screen.getByText('# 导读工具包')).toBeInTheDocument();
    expect(screen.queryByText(/storage_key|education\/private|\/managed\//i)).not.toBeInTheDocument();
  });
});
