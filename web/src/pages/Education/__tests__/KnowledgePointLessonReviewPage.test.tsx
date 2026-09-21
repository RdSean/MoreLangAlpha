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
let structureStatus = 'accepted';

vi.mock('../components/EducationMarkdown', () => ({
  default: ({ content }: { content: string }) => <div data-testid="education-markdown">{content}</div>,
}));

vi.mock('../queries', () => ({
  useKnowledgePointLessonByPoint: () => ({
    data: lessonData,
    isLoading: false,
    refetch,
  }),
  useLatestTextbookStructure: () => ({
    data: { structure_id: 'structure-1', status: structureStatus },
    isLoading: false,
    isPending: false,
    refetch,
  }),
  useStructureGenerationJob: () => ({ data: undefined }),
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
    structureStatus = 'accepted';
  });

  it('generates a new lesson with the auto-grading option', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('checkbox', { name: '自动判题' }));
    await user.click(screen.getByRole('button', { name: '生成课程' }));

    await waitFor(() => expect(generateLesson).toHaveBeenCalledWith({
      knowledgePointId: 'kp-1',
      autoGrading: true,
    }));
  });

  it('blocks lesson generation until the structure is accepted', () => {
    structureStatus = 'review';
    renderPage();

    expect(screen.getByText('先接受教材结构，再生成课程')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '生成课程' })).not.toBeInTheDocument();
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
