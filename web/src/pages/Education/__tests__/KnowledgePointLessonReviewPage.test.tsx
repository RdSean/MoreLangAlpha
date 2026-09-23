import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import KnowledgePointLessonReviewPage from '../KnowledgePointLessonReviewPage';

const generateLesson = vi.fn().mockResolvedValue({ generation_job_id: 'generation-1' });
const saveLessonRevision = vi.fn().mockResolvedValue({});
const approveLesson = vi.fn().mockResolvedValue({});
const publish = vi.fn().mockResolvedValue({ publication_id: 'publication-1' });
const refetch = vi.fn().mockResolvedValue({});
let lessonData: Record<string, unknown> | null = null;
let lessonLoading = false;
let structureStatus = 'accepted';
let generationJobData: Record<string, unknown> | undefined;
let lessonGenerationPending = false;
let lessonGenerationStatus: Record<string, unknown> = {
  knowledge_point_id: 'kp-1',
  generating: false,
  generation_job_id: null,
  status: null,
  attempt_count: 0,
  auto_grading: false,
  prompt: '',
  error_code: null,
  error_message: null,
  source_kind: 'legacy_reading',
  candidate_status: 'accepted',
  content_node_id: null,
  content_node_title: null,
  content_asset_available: true,
};

vi.mock('../components/EducationMarkdown', () => ({
  default: ({ content }: { content: string }) => <div data-testid="education-markdown">{content}</div>,
}));

vi.mock('../queries', () => ({
  useKnowledgePointLessonByPoint: () => ({
    data: lessonData,
    isLoading: lessonLoading,
    refetch,
  }),
  useLatestTextbookStructure: () => ({
    data: { structure_id: 'structure-1', status: structureStatus },
    isLoading: false,
    isPending: false,
    refetch,
  }),
  useStructureGenerationJob: () => ({ data: generationJobData }),
  useLessonGenerationStatus: () => ({
    data: lessonGenerationStatus,
    isPending: lessonGenerationPending,
  }),
  useStructureMutations: () => ({
    generateLesson: { mutateAsync: generateLesson, isPending: false },
    saveLessonRevision: { mutateAsync: saveLessonRevision, isPending: false },
    approveLesson: { mutateAsync: approveLesson, isPending: false },
    publish: { mutateAsync: publish, isPending: false },
  }),
}));

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/textbooks/textbook-1/versions/version-1/knowledge/kp-1']}>
      <Routes>
        <Route
          path="/textbooks/:textbookId/versions/:versionId/knowledge/:knowledgePointId"
          element={<KnowledgePointLessonReviewPage />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe('KnowledgePointLessonReviewPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    lessonData = null;
    lessonLoading = false;
    structureStatus = 'accepted';
    generationJobData = undefined;
    lessonGenerationPending = false;
    lessonGenerationStatus = {
      knowledge_point_id: 'kp-1',
      generating: false,
      generation_job_id: null,
      status: null,
      attempt_count: 0,
      auto_grading: false,
      prompt: '',
      error_code: null,
      error_message: null,
      source_kind: 'legacy_reading',
      candidate_status: 'accepted',
      content_node_id: null,
      content_node_title: null,
      content_asset_available: true,
    };
  });

  it('generates a new lesson with trimmed guidance and auto-grading', async () => {
    const user = userEvent.setup();
    renderPage();

    const prompt = screen.getByRole('textbox', { name: '课程生成要求（可选）' });
    await user.type(prompt, '  使用中文讲解，保留英文术语。  ');
    await user.click(screen.getByRole('checkbox', { name: '自动判题' }));
    await user.click(screen.getByRole('button', { name: '生成课程' }));

    await waitFor(() => expect(generateLesson).toHaveBeenCalledWith({
      knowledgePointId: 'kp-1',
      autoGrading: true,
      prompt: '使用中文讲解，保留英文术语。',
    }));
  });

  it('blocks lesson generation until the structure is accepted', () => {
    structureStatus = 'review';
    renderPage();

    expect(screen.getByText('先接受教材结构，再生成课程')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '生成课程' })).not.toBeInTheDocument();
  });

  it('disables generation for a pending generic candidate', async () => {
    structureStatus = 'review';
    lessonGenerationStatus = {
      ...lessonGenerationStatus,
      source_kind: 'content_node',
      candidate_status: 'pending',
      content_node_id: 'node-1',
      content_node_title: 'The World Game',
      content_asset_available: true,
    };
    const user = userEvent.setup();
    renderPage();

    const button = screen.getByRole('button', { name: '生成课程' });
    expect(button).toBeDisabled();
    expect(screen.getByText('请先在知识点候选审阅中接受该知识点，再生成课程。')).toHaveAttribute('aria-live', 'polite');

    await user.click(button);
    expect(generateLesson).not.toHaveBeenCalled();
  });

  it('disables generation when the accepted generic node asset is missing', () => {
    structureStatus = 'review';
    lessonGenerationStatus = {
      ...lessonGenerationStatus,
      source_kind: 'content_node',
      candidate_status: 'accepted',
      content_node_id: 'node-1',
      content_node_title: 'The World Game',
      content_asset_available: false,
    };
    renderPage();

    expect(screen.getByRole('button', { name: '生成课程' })).toBeDisabled();
    expect(screen.getByText('该知识点尚未绑定可用的内容资产，暂时无法生成课程。')).toHaveAttribute('aria-live', 'polite');
  });

  it('generates a lesson for an accepted generic node without structure acceptance', async () => {
    structureStatus = 'review';
    lessonGenerationStatus = {
      ...lessonGenerationStatus,
      source_kind: 'content_node',
      candidate_status: 'accepted',
      content_node_id: 'node-1',
      content_node_title: 'The World Game',
      content_asset_available: true,
    };
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('button', { name: '生成课程' }));

    await waitFor(() => expect(generateLesson).toHaveBeenCalledWith({
      knowledgePointId: 'kp-1',
      autoGrading: false,
      prompt: '',
    }));
  });

  it('restores persisted guidance when reopening the generation entry', () => {
    lessonGenerationStatus = {
      ...lessonGenerationStatus,
      prompt: '使用中文讲解，保留英文术语。',
    };
    renderPage();

    expect(
      screen.getByRole('textbox', { name: '课程生成要求（可选）' }),
    ).toHaveValue('使用中文讲解，保留英文术语。');
  });

  it('keeps entered guidance when generation conflicts with an active job', async () => {
    generateLesson.mockRejectedValueOnce(
      new Error('活动课程已使用其他生成要求，请先取消当前任务。'),
    );
    const user = userEvent.setup();
    renderPage();

    const prompt = screen.getByRole('textbox', { name: '课程生成要求（可选）' });
    await user.type(prompt, '改用英文讲解。');
    await user.click(screen.getByRole('button', { name: '生成课程' }));

    await waitFor(() => expect(generateLesson).toHaveBeenCalled());
    expect(prompt).toHaveValue('改用英文讲解。');
  });

  it('shows active lesson generation status and prevents an accidental retry', async () => {
    generationJobData = { status: 'running' };
    const user = userEvent.setup();
    renderPage();

    const button = screen.getByRole('button', { name: '正在生成课程' });
    expect(button).toBeDisabled();
    expect(screen.getByText('正在生成课程', { selector: 'p' })).toHaveAttribute('aria-live', 'polite');

    await user.click(button);
    expect(generateLesson).not.toHaveBeenCalled();
  });

  it('keeps generation frozen while lesson detail or status is loading', async () => {
    lessonData = {
      lesson_id: 'lesson-1',
      status: 'review',
      latest_revision_id: 'revision-1',
      knowledge_point_id: 'kp-1',
      knowledge_point_title: '世界运动',
      structure_id: 'structure-1',
      unit_id: 'unit-1',
      unit_title: 'Unit 1',
      content_markdown: '# 世界运动\n',
      revisions: [],
    };
    lessonLoading = true;
    lessonGenerationPending = true;
    const user = userEvent.setup();
    renderPage();

    const button = screen.getByRole('button', { name: '重新生成' });
    expect(button).toBeDisabled();
    await user.click(button);
    expect(generateLesson).not.toHaveBeenCalled();
  });

  it('keeps generation frozen when the status query reports an active job', async () => {
    lessonGenerationStatus = {
      ...lessonGenerationStatus,
      generating: true,
      generation_job_id: 'generation-active',
    };
    const user = userEvent.setup();
    renderPage();

    const button = screen.getByRole('button', { name: '正在生成课程' });
    expect(button).toBeDisabled();
    expect(screen.getByText('正在生成课程', { selector: 'p' })).toHaveAttribute('aria-live', 'polite');

    await user.click(button);
    expect(generateLesson).not.toHaveBeenCalled();
  });

  it('announces course generation failures politely', () => {
    generationJobData = {
      status: 'failed',
      error_message: '课程生成失败，请重试。',
    };
    renderPage();

    expect(screen.getByText('课程生成失败，请重试。')).toHaveAttribute('aria-live', 'polite');
  });

  it('renders Markdown, saves revisions, approves, and publishes', async () => {
    lessonData = {
      lesson_id: 'lesson-1',
      status: 'review',
      latest_revision_id: 'revision-1',
      knowledge_point_id: 'kp-1',
      knowledge_point_title: '世界运动',
      structure_id: 'structure-1',
      unit_id: 'unit-1',
      unit_title: 'Unit 1',
      content_markdown: '# 世界运动\n',
      revisions: [{
        revision_id: 'revision-1',
        revision: 1,
        format: 'markdown',
        content_sha256: 'a'.repeat(64),
        size_bytes: 10,
        processing_profile_sha256: 'b'.repeat(64),
      }],
    };
    const user = userEvent.setup();
    renderPage();

    expect(screen.getByTestId('education-markdown')).toHaveTextContent('# 世界运动');
    expect(
      screen.getByRole('textbox', { name: '课程生成要求（可选）' }),
    ).toHaveValue('');

    await user.click(screen.getByRole('button', { name: '编辑 Markdown' }));
    const editor = screen.getByRole('textbox', { name: '课程 Markdown' });
    await user.clear(editor);
    await user.type(editor, '# 修订版\n');
    await user.click(screen.getByRole('button', { name: '保存为新 revision' }));
    await waitFor(() => expect(saveLessonRevision).toHaveBeenCalledWith({
      lessonId: 'lesson-1',
      contentMarkdown: '# 修订版\n',
    }));

    await user.click(screen.getByRole('button', { name: '通过当前版本' }));
    await waitFor(() => expect(approveLesson).toHaveBeenCalledWith({
      lessonId: 'lesson-1',
      revisionId: 'revision-1',
    }));

    await user.click(screen.getByRole('button', { name: '发布结构教材' }));
    await waitFor(() => expect(publish).toHaveBeenCalledWith({
      versionId: 'version-1',
      structureId: 'structure-1',
    }));
  });
});
