import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import StudentTextbookLearningPage from '../StudentTextbookLearningPage';

vi.mock('../components/EducationMarkdown', () => ({
  default: ({ content }: { content: string }) => <div data-testid="student-markdown">{content}</div>,
}));

vi.mock('../components/StudentLessonFollowUp', () => ({
  default: () => <div>追问组件</div>,
}));

vi.mock('../queries', () => ({
  useStudentTextbookStructure: () => ({
    data: {
      assignment_id: 'assignment-1',
      publication_id: 'publication-1',
      textbook_id: 'textbook-1',
      textbook_title: 'Reading Explorer 3',
      textbook_slug: 're3',
      version_sequence: 1,
      structure_id: 'structure-1',
      structure_sequence: 1,
      units: [
        {
          unit_id: 'unit-1',
          position: 1,
          slug: 'unit-1',
          title: 'Unit 1: Sports and Fitness',
          summary: 'Sports and fitness',
          unit_type: 'teaching',
          knowledge_points: [
            {
              knowledge_point_id: 'kp-1',
              position: 1,
              slug: 'world-game',
              title: '世界运动',
              summary: '',
              has_lesson: true,
            },
          ],
        },
      ],
    },
    isLoading: false,
  }),
  useStudentKnowledgePointLesson: () => ({
    data: {
      assignment_id: 'assignment-1',
      knowledge_point_id: 'kp-1',
      knowledge_point_title: '世界运动',
      unit_id: 'unit-1',
      unit_title: 'Unit 1',
      revision_id: 'revision-1',
      revision: 1,
      format: 'markdown',
      content_sha256: 'a'.repeat(64),
      size_bytes: 20,
      content_markdown: '# 世界运动\n',
    },
    isLoading: false,
  }),
  useStudentLearningItems: () => ({ data: [], isLoading: false }),
  useLearningAssetMutations: () => ({
    add: { mutateAsync: vi.fn(), isPending: false },
    progress: { mutateAsync: vi.fn(), isPending: false },
  }),
}));

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/education/learn/:assignmentId" element={<StudentTextbookLearningPage />} />
        <Route path="/education/learn/:assignmentId/units/:unitId" element={<StudentTextbookLearningPage />} />
        <Route path="/education/learn/:assignmentId/knowledge/:knowledgePointId" element={<StudentTextbookLearningPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('StudentTextbookLearningPage', () => {
  it('renders Unit overview and knowledge-point links', () => {
    renderAt('/education/learn/assignment-1/units/unit-1');

    expect(screen.getByRole('heading', { name: 'Unit 1: Sports and Fitness' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '1. 世界运动已发布' })).toBeInTheDocument();
  });

  it('renders a published lesson and follow-up composer', () => {
    renderAt('/education/learn/assignment-1/knowledge/kp-1');

    expect(screen.getByRole('heading', { name: '世界运动' })).toBeInTheDocument();
    expect(screen.getByTestId('student-markdown')).toHaveTextContent('# 世界运动');
    expect(screen.getByText('追问组件')).toBeInTheDocument();
  });
});
