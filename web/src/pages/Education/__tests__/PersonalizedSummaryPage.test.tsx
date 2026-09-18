import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import PersonalizedSummaryPage from '../PersonalizedSummaryPage';

const summarize = vi.fn().mockResolvedValue({});

vi.mock('../components/EducationMarkdown', () => ({
  default: ({ content }: { content: string }) => <div data-testid="summary-markdown">{content}</div>,
}));

vi.mock('../queries', () => ({
  useStudentTextbookStructure: () => ({
    data: {
      units: [
        {
          unit_id: 'unit-1',
          title: 'Unit 1',
          knowledge_points: [
            { knowledge_point_id: 'kp-1', title: '世界运动' },
          ],
        },
      ],
    },
    isLoading: false,
  }),
  useStudentLearningItems: () => ({
    data: [
      {
        item_id: 'item-1',
        kind: 'highlight',
        knowledge_point_id: 'kp-1',
        content: 'It is a simple game.',
      },
      {
        item_id: 'item-2',
        kind: 'note',
        knowledge_point_id: 'kp-1',
        content: '简单是核心原因。',
      },
      {
        item_id: 'summary-1',
        kind: 'summary',
        knowledge_point_id: null,
        content: '# Unit 1 总结',
      },
    ],
    isLoading: false,
  }),
  useLearningAssetMutations: () => ({
    summarize: { mutateAsync: summarize, isPending: false },
  }),
}));

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/education/learn/assignment-1/summary?unit=unit-1']}>
      <Routes>
        <Route path="/education/learn/:assignmentId/summary" element={<PersonalizedSummaryPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('PersonalizedSummaryPage', () => {
  beforeEach(() => vi.clearAllMocks());

  it('groups learning items and renders the latest summary', () => {
    renderPage();

    expect(screen.getByTestId('summary-markdown')).toHaveTextContent('# Unit 1 总结');
    expect(screen.getByText(/It is a simple game/)).toBeInTheDocument();
    expect(screen.getByText(/简单是核心原因/)).toBeInTheDocument();
  });

  it('generates a Unit summary', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole('button', { name: '生成个性化总结' }));

    await waitFor(() => expect(summarize).toHaveBeenCalledWith({
      assignmentId: 'assignment-1',
      unitId: 'unit-1',
    }));
  });
});
