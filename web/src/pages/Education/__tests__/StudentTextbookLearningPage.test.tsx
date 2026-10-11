import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import StudentTextbookLearningPage from '../StudentTextbookLearningPage';

vi.mock('../components/EducationMarkdown', () => ({
  default: ({ content }: { content: string }) => <div data-testid="student-markdown">{content}</div>,
}));

vi.mock('../components/LessonConversation', () => ({
  default: ({ children }: { children: React.ReactNode | ((state: { questionsBusy: boolean }) => React.ReactNode) }) => (
    <div>{typeof children === 'function' ? children({ questionsBusy: false }) : children}<div>追问组件</div></div>
  ),
}));

vi.mock('../queries', () => ({
  useBookReadingState: () => ({ data: {} }),
  useStudentTextbookStructure: () => ({
    data: {
      assignment_id: 'assignment-1',
      textbook_id: 'textbook-1',
      textbook_title: 'Reading Explorer 3',
      structure_id: 'structure-1',
      schema_version: '2.1.0',
      warnings: [],
      structure: {
        schema_version: '2.1.0',
        book: { title: 'Reading Explorer 3' },
        source: { path: 'source.md', total_lines: 100 },
        coverage: {},
        nodes: [
          {
            id: 'unit-1',
            title: 'Unit 1: Sports and Fitness',
            anchor: { start_line: 1, end_line: 80 },
            children: [],
          },
        ],
      },
      knowledge_points: [
        {
          knowledge_point_id: 'kp-db-1',
          skill_kp_id: 'world-game',
          position: 1,
          title: '世界运动',
          unit_skill_node_id: 'unit-1',
          node_skill_ids: [],
          start_line: 10,
          end_line: 20,
          content_file: 'materials/kp-db-1.md',
          material_available: true,
        },
      ],
    },
    isLoading: false,
  }),
  useStudentKnowledgePointMaterial: () => ({
    data: {
      assignment_id: 'assignment-1',
      textbook_id: 'textbook-1',
      knowledge_point_id: 'kp-db-1',
      skill_kp_id: 'world-game',
      material_available: true,
      markdown: '# 世界运动\n',
      generated_at: '2026-10-02T08:00:00Z',
      depth: 'lesson',
      requirements: null,
      content_sha256: 'a'.repeat(64),
    },
    isLoading: false,
  }),
  useManagedBookSourceSlice: () => ({
    data: {
      textbook_id: 'textbook-1',
      start_line: 1,
      end_line: 32,
      total_lines: 100,
      markdown: '# Unit 1: Sports and Fitness\n\nOriginal text.',
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
      </Routes>
    </MemoryRouter>,
  );
}

describe('StudentTextbookLearningPage', () => {
  it('collapses and restores the directory without remounting the lesson', () => {
    renderAt('/education/learn/assignment-1?kp=world-game&view=material');
    const lesson = screen.getByTestId('student-markdown');
    expect(screen.getByRole('link', { name: '返回我的教材' })).toHaveAttribute('href', '/education/learn');
    fireEvent.click(screen.getByRole('button', { name: '收起教材目录' }));
    expect(screen.queryByRole('button', { name: '收起教材目录' })).not.toBeInTheDocument();
    expect(screen.getByTestId('student-markdown')).toBe(lesson);
    fireEvent.click(screen.getByRole('button', { name: '展开教材目录' }));
    expect(screen.getByRole('button', { name: '收起教材目录' })).toBeInTheDocument();
    expect(screen.getByTestId('student-markdown')).toBe(lesson);
  });

  it('reads a source node by its Skill node ID', () => {
    renderAt('/education/learn/assignment-1?node=unit-1&view=source');

    expect(screen.getByRole('heading', { level: 1, name: 'Unit 1: Sports and Fitness' })).toBeInTheDocument();
    expect(screen.getByTestId('student-markdown')).toHaveTextContent('Original text.');
    expect(screen.queryByText(/结构 v|已发布/)).not.toBeInTheDocument();
  });

  it('maps a Skill KP URL to the current material and database KP UUID', () => {
    renderAt('/education/learn/assignment-1?kp=world-game&view=material');

    expect(screen.getByRole('heading', { name: '世界运动' })).toBeInTheDocument();
    expect(screen.getByTestId('student-markdown')).toHaveTextContent('# 世界运动');
    expect(screen.getByText('追问组件')).toBeInTheDocument();
  });
});
