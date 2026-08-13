import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import TextbookDetailPage from '../TextbookDetailPage';

const state = vi.hoisted(() => ({
  textbook: null as Record<string, unknown> | null,
  assets: [] as Array<Record<string, unknown>>,
  upload: vi.fn(),
  start: vi.fn(),
  run: vi.fn(),
  retry: vi.fn(),
  createTeaching: vi.fn(),
  cancelTeaching: vi.fn(),
  resumeTeaching: vi.fn(),
  teachingJob: null as Record<string, unknown> | null,
  publish: vi.fn(),
  assign: vi.fn(),
}));

vi.mock('../api', () => ({
  uploadEducationAsset: state.upload,
}));

vi.mock('../queries', () => ({
  useEducationAssets: () => ({ data: state.assets, isLoading: false }),
  useEducationMembers: () => ({ data: [] }),
  useParentLearningRecords: () => ({ data: { records: [] }, isLoading: false }),
  useParentLearningTranscript: () => ({ data: { messages: [] }, isLoading: false }),
  useTextbook: () => ({ data: state.textbook, isLoading: false }),
  useTeachingJob: () => ({ data: state.teachingJob }),
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
  state.textbook = {
    textbook_id: 'textbook-1',
    household_id: 'household-1',
    title: '英语第二册',
    slug: 'english-2',
    versions: [],
  };
  state.assets = [
    { asset_id: 'asset-1', original_filename: 'body.pdf', content_type: 'application/pdf', size_bytes: 1024, created_at: '2026-08-13T00:00:00Z' },
    { asset_id: 'asset-2', original_filename: 'workbook.pdf', content_type: 'application/pdf', size_bytes: 2048, created_at: '2026-08-13T00:01:00Z' },
  ];
  state.upload.mockReset();
  state.start.mockReset().mockResolvedValue({ job_id: 'job-1' });
  state.run.mockReset();
  state.retry.mockReset();
  state.createTeaching.mockReset();
  state.cancelTeaching.mockReset();
  state.resumeTeaching.mockReset();
  state.teachingJob = null;
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

    expect(screen.getByRole('heading', { name: '下一步：添加教材资料' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '开始加工' })).toBeInTheDocument();
  });

  it('submits the selected existing sources explicitly', async () => {
    render(
      <MemoryRouter initialEntries={['/education/textbooks/textbook-1']}>
        <Routes><Route path="/education/textbooks/:textbookId" element={<TextbookDetailPage />} /></Routes>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', { name: '开始加工' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'body.pdf' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'workbook.pdf' }));
    fireEvent.click(screen.getByRole('button', { name: '创建加工任务' }));

    await waitFor(() => expect(state.start).toHaveBeenCalledWith({
      textbookId: 'textbook-1',
      sourceAssetIds: ['asset-1', 'asset-2'],
    }));
  });

  it('separates frozen source, content, teaching, and student review information', () => {
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
        sources: [{ asset_id: 'asset-1', original_filename: 'body.pdf', content_type: 'application/pdf', size_bytes: 1024 }],
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

    expect(screen.getByText('body.pdf')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: '内容' }));
    expect(screen.getByText('第 1-10 页')).toBeInTheDocument();
    expect(screen.getByText(/原始提取内容。/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: '教学' }));
    expect(screen.getByText(/完成阅读。/)).toBeInTheDocument();
    expect(screen.getByText(/完成阅读后做什么？/)).toBeInTheDocument();
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
});
