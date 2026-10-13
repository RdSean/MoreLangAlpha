import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/i18n';
import StudentTextbookLearningPage from '../StudentTextbookLearningPage';

const state = vi.hoisted(() => ({ materialAvailable: true, sourceRequest: vi.fn() }));

beforeEach(() => {
  void i18n.changeLanguage('zh-CN');
  state.materialAvailable = true;
  state.sourceRequest.mockClear();
});

vi.mock('../components/EducationMarkdown', () => ({
  default: ({ content }: { content: string }) => <div data-testid="student-markdown">{content}</div>,
}));

vi.mock('../components/LessonConversation', () => ({
  default: ({ children }: { children: React.ReactNode | ((state: { questionsBusy: boolean }) => React.ReactNode) }) => (
    <div>{typeof children === 'function' ? children({ questionsBusy: false }) : children}<div>追问组件</div></div>
  ),
}));

vi.mock('../components/BookOriginalReader', () => ({
  BookOriginalReader: ({ textbookId, startLine, jsonPage, restoredPage, onPageChange }: {
    textbookId: string; startLine?: number; jsonPage?: number; restoredPage?: number;
    onPageChange?: (page: number) => void;
  }) => <div data-testid="student-original" data-textbook={textbookId} data-start-line={startLine} data-json-page={jsonPage}>
    PDF page {restoredPage ?? jsonPage ?? 1}
    <button onClick={() => onPageChange?.(9)}>下一 PDF 页</button>
  </div>,
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
            page_range: { start: 7, end: 10, source: 'derived', label: 'PDF pages' },
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
          node_skill_ids: ['unit-1'],
          start_line: 10,
          end_line: 20,
          content_file: 'materials/kp-db-1.md',
          material_available: state.materialAvailable,
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
      material_available: state.materialAvailable,
      markdown: '# 世界运动\n',
      generated_at: '2026-10-02T08:00:00Z',
      depth: 'lesson',
      requirements: null,
      content_sha256: 'a'.repeat(64),
    },
    isLoading: false,
  }),
  useManagedBookSourceSlice: (...args: unknown[]) => {
    state.sourceRequest(...args);
    return {
    data: {
      textbook_id: 'textbook-1',
      start_line: 1,
      end_line: 32,
      total_lines: 100,
      markdown: '# Unit 1: Sports and Fitness\n\nOriginal text.',
    },
    isLoading: false,
    };
  },
  useStudentLearningItems: () => ({ data: [], isLoading: false }),
  useLearningAssetMutations: () => ({
    add: { mutateAsync: vi.fn(), isPending: false },
    progress: { mutateAsync: vi.fn(), isPending: false },
  }),
}));

function Location() {
  const location = useLocation();
  return <output data-testid="location">{location.search}</output>;
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/education/learn/:assignmentId" element={<StudentTextbookLearningPage />} />
      </Routes>
      <Location />
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

  it('opens PDF from the original textbook tab and keeps Markdown under text contents', () => {
    renderAt('/education/learn/assignment-1?kp=world-game&view=material');
    fireEvent.click(screen.getAllByRole('tab', { name: /原始教材|Source Contents/ })[0]);
    expect(screen.getByTestId('student-original')).toHaveAttribute('data-start-line', '10');
    expect(screen.getByTestId('student-original')).toHaveAttribute('data-json-page', '7');
    expect(screen.getByTestId('location')).toHaveTextContent('view=original');
    expect(screen.queryByText('追问组件')).not.toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('button', { name: '打开 Unit 1: Sports and Fitness' })[0]);
    expect(screen.getByTestId('student-original')).toHaveAttribute('data-start-line', '1');
    fireEvent.click(screen.getAllByRole('tab', { name: /文字目录|Text Contents/ })[0]);
    expect(screen.getByTestId('student-markdown')).toHaveTextContent('Original text.');
    expect(screen.queryByTestId('student-original')).not.toBeInTheDocument();
    expect(screen.getByTestId('location')).toHaveTextContent('view=source');
  });

  it('restores PDF page from the URL and updates it when turning pages', async () => {
    renderAt('/education/learn/assignment-1?node=unit-1&view=original&nav=source&pdfPage=8');
    await waitFor(() => expect(screen.getByTestId('student-original')).toHaveTextContent('PDF page 8'));
    fireEvent.click(screen.getByRole('button', { name: '下一 PDF 页' }));
    expect(screen.getByTestId('location')).toHaveTextContent('pdfPage=9');
    expect(screen.getByTestId('student-original')).toHaveTextContent('PDF page 9');
    expect(screen.getAllByRole('tab', { name: /原始教材|Source Contents/ })[0]).toHaveAttribute('aria-selected', 'true');
  });

  it('returns to a generated knowledge point and clears a stale PDF page', () => {
    renderAt('/education/learn/assignment-1?node=unit-1&view=original&nav=source&pdfPage=8');
    fireEvent.click(screen.getAllByRole('tab', { name: /知识点|Knowledge Points/ })[0]);
    expect(screen.getByText('追问组件')).toBeInTheDocument();
    expect(screen.getByTestId('location')).toHaveTextContent('view=material');
    expect(screen.getByTestId('location')).not.toHaveTextContent('pdfPage');
    expect(screen.getByTestId('location')).not.toHaveTextContent('node=');
  });

  it('preserves old Markdown links as text contents and ignores invalid PDF pages', () => {
    const { unmount } = renderAt('/education/learn/assignment-1?node=unit-1&view=source');
    expect(screen.getByTestId('student-markdown')).toHaveTextContent('Original text.');
    expect(screen.getAllByRole('tab', { name: /文字目录|Text Contents/ })[0]).toHaveAttribute('aria-selected', 'true');
    unmount();
    renderAt('/education/learn/assignment-1?node=unit-1&view=original&pdfPage=-1');
    expect(screen.getByTestId('student-original')).toHaveTextContent('PDF page 7');
  });

  it('keeps a direct original URL when selecting the first knowledge point automatically', async () => {
    renderAt('/education/learn/assignment-1?view=original&pdfPage=8');
    await waitFor(() => expect(screen.getByTestId('student-original')).toHaveTextContent('PDF page 8'));
    expect(screen.getByTestId('location')).toHaveTextContent('kp=world-game');
    expect(screen.getAllByRole('tab', { name: /原始教材|Source Contents/ })[0]).toHaveAttribute('aria-selected', 'true');
    expect(state.sourceRequest.mock.lastCall?.[3]).toBe(false);
  });

  it('reads original PDF before a lecture has been generated', () => {
    state.materialAvailable = false;
    renderAt('/education/learn/assignment-1?kp=world-game&view=source&nav=knowledge');
    expect(screen.queryByText('追问组件')).not.toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('tab', { name: /原始教材|Source Contents/ })[0]);
    expect(screen.getByTestId('student-original')).toHaveTextContent('PDF page 7');
    expect(state.sourceRequest.mock.lastCall?.[3]).toBe(false);
  });
});
