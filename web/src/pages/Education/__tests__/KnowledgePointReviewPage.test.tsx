import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import KnowledgePointReviewPage from '../KnowledgePointReviewPage';

const acceptCandidates = vi.fn().mockResolvedValue({});
const rejectCandidates = vi.fn().mockResolvedValue({});
const mergeCandidates = vi.fn().mockResolvedValue({});
const splitCandidate = vi.fn().mockResolvedValue({});
const updateCandidate = vi.fn().mockResolvedValue({});
const candidateReviewState = vi.hoisted(() => ({
  data: undefined as Record<string, unknown> | undefined,
}));

vi.mock('../queries', () => ({
  useLatestTextbookStructure: () => ({
    data: {
      structure_id: 'structure-1',
      version_id: 'version-1',
      status: 'review',
    },
    isLoading: false,
    isPending: false,
  }),
  useKnowledgePointCandidateReview: () => ({
    data: candidateReviewState.data,
    isLoading: false,
    isError: false,
  }),
  useKnowledgePointCandidateMutations: () => ({
    accept: { mutateAsync: acceptCandidates, isPending: false },
    reject: { mutateAsync: rejectCandidates, isPending: false },
    merge: { mutateAsync: mergeCandidates, isPending: false },
    split: { mutateAsync: splitCandidate, isPending: false },
    update: { mutateAsync: updateCandidate, isPending: false },
  }),
}));

function pageTree() {
  return (
    <MemoryRouter initialEntries={['/textbooks/textbook-1/versions/version-1/candidates']}>
      <Routes>
        <Route
          path="/textbooks/:textbookId/versions/:versionId/candidates"
          element={<KnowledgePointReviewPage />}
        />
      </Routes>
    </MemoryRouter>
  );
}

function renderPage() {
  return render(pageTree());
}

describe('KnowledgePointReviewPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    candidateReviewState.data = {
      structure_id: 'structure-1',
      version_id: 'version-1',
      nodes: [
        {
          node_id: 'node-1',
          parent_node_id: null,
          node_key: 'unit-1',
          node_type: 'unit',
          label: null,
          position: 1,
          slug: 'unit-1',
          title: 'Unit 1',
          summary: '',
          source_refs: [],
          candidates: [
            {
              knowledge_point_id: 'kp-1',
              content_structure_id: 'structure-1',
              content_node_id: 'node-1',
              candidate_key: 'unit-1-kp-1',
              point_type: 'concept',
              origin: 'generated',
              candidate_status: 'pending',
              position: 1,
              slug: 'world-game',
              title: '世界运动',
              summary: '足球成为全球运动的原因',
              source_refs: [],
              confidence: 0.9,
              status: 'review',
              created_at: null,
            },
            {
              knowledge_point_id: 'kp-2',
              content_structure_id: 'structure-1',
              content_node_id: 'node-1',
              candidate_key: 'unit-1-kp-2',
              point_type: 'vocabulary',
              origin: 'generated',
              candidate_status: 'pending',
              position: 2,
              slug: 'prefix-uni',
              title: '前缀 uni-',
              summary: '',
              source_refs: [],
              confidence: 0.88,
              status: 'review',
              created_at: null,
            },
          ],
        },
      ],
    };
  });

  it('renders the generic tree and keeps generated candidates pending', () => {
    renderPage();

    expect(screen.getByText('Unit 1')).toBeInTheDocument();
    expect(screen.getByText('世界运动')).toBeInTheDocument();
    expect(screen.getByText('前缀 uni-')).toBeInTheDocument();
    expect(screen.getAllByText('待确认')).toHaveLength(2);
    expect(acceptCandidates).not.toHaveBeenCalled();
  });

  it('links back to the textbook detail for the generic candidate flow', () => {
    renderPage();

    expect(screen.getByRole('link', { name: '返回教材' })).toHaveAttribute(
      'href',
      '/textbooks/textbook-1',
    );
  });

  it('links accepted candidates directly to lesson production', () => {
    candidateReviewState.data = {
      ...candidateReviewState.data,
      nodes: [
        {
          ...(candidateReviewState.data?.nodes as Array<Record<string, unknown>>)[0],
          candidates: [
            {
              ...(candidateReviewState.data?.nodes as Array<{ candidates: Array<Record<string, unknown>> }>)[0].candidates[0],
              candidate_status: 'accepted',
              status: 'accepted',
            },
            (candidateReviewState.data?.nodes as Array<{ candidates: Array<Record<string, unknown>> }>)[0].candidates[1],
          ],
        },
      ],
    };
    renderPage();

    expect(
      screen.getByRole('link', { name: '制作课程 世界运动' }),
    ).toHaveAttribute(
      'href',
      '/textbooks/textbook-1/versions/version-1/knowledge/kp-1',
    );
    expect(
      screen.queryByRole('link', { name: '制作课程 前缀 uni-' }),
    ).not.toBeInTheDocument();
  });

  it('accepts only explicitly selected candidates', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('checkbox', { name: '选择知识点 世界运动' }));
    await user.click(screen.getByRole('button', { name: '接受所选' }));

    await waitFor(() =>
      expect(acceptCandidates).toHaveBeenCalledWith({
        candidateIds: ['kp-1'],
      }),
    );
  });

  it('renames a candidate through the edit dialog', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('button', { name: '编辑 世界运动' }));
    const title = screen.getByRole('textbox', { name: '知识点标题' });
    await user.clear(title);
    await user.type(title, '足球运动');
    await user.click(screen.getByRole('button', { name: '保存修改' }));

    await waitFor(() =>
      expect(updateCandidate).toHaveBeenCalledWith({
        candidateId: 'kp-1',
        title: '足球运动',
        summary: '足球成为全球运动的原因',
        point_type: 'concept',
      }),
    );
  });

  it('rejects the explicitly selected candidates', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('checkbox', { name: '选择知识点 世界运动' }));
    await user.click(screen.getByRole('checkbox', { name: '选择知识点 前缀 uni-' }));
    await user.click(screen.getByRole('button', { name: '拒绝所选' }));

    await waitFor(() =>
      expect(rejectCandidates).toHaveBeenCalledWith({
        candidateIds: ['kp-1', 'kp-2'],
      }),
    );
  });

  it('selects and submits only pending candidates', async () => {
    candidateReviewState.data = {
      ...candidateReviewState.data,
      nodes: [
        {
          ...(candidateReviewState.data?.nodes as Array<Record<string, unknown>>)[0],
          candidates: [
            (candidateReviewState.data?.nodes as Array<{ candidates: Array<Record<string, unknown>> }>)[0].candidates[0],
            {
              ...(candidateReviewState.data?.nodes as Array<{ candidates: Array<Record<string, unknown>> }>)[0].candidates[1],
              candidate_status: 'accepted',
              status: 'accepted',
            },
          ],
        },
      ],
    };
    renderPage();

    const accepted = screen.getByRole('checkbox', { name: '选择知识点 前缀 uni-' });
    expect(accepted).toBeDisabled();
    fireEvent.click(accepted);
    fireEvent.click(screen.getByRole('checkbox', { name: '选择知识点 世界运动' }));
    fireEvent.click(screen.getByRole('button', { name: '接受所选' }));

    await waitFor(() =>
      expect(acceptCandidates).toHaveBeenCalledWith({
        candidateIds: ['kp-1'],
      }),
    );
  });

  it('drops a selected candidate when a refresh makes it non-pending', async () => {
    const view = renderPage();
    fireEvent.click(screen.getByRole('checkbox', { name: '选择知识点 世界运动' }));
    expect(screen.getByRole('button', { name: '接受所选' })).toBeEnabled();

    candidateReviewState.data = {
      ...candidateReviewState.data,
      nodes: [
        {
          ...(candidateReviewState.data?.nodes as Array<Record<string, unknown>>)[0],
          candidates: [
            {
              ...(candidateReviewState.data?.nodes as Array<{ candidates: Array<Record<string, unknown>> }>)[0].candidates[0],
              candidate_status: 'accepted',
              status: 'accepted',
            },
            (candidateReviewState.data?.nodes as Array<{ candidates: Array<Record<string, unknown>> }>)[0].candidates[1],
          ],
        },
      ],
    };
    view.rerender(pageTree());

    await waitFor(() =>
      expect(
        screen.getByRole('checkbox', { name: '选择知识点 世界运动' }),
      ).toBeDisabled(),
    );
    expect(screen.getByRole('button', { name: '接受所选' })).toBeDisabled();
  });

  it('merges selected candidates into an explicitly chosen target', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('checkbox', { name: '选择知识点 世界运动' }));
    await user.click(screen.getByRole('checkbox', { name: '选择知识点 前缀 uni-' }));
    await user.click(screen.getByRole('button', { name: '合并所选' }));
    await user.click(screen.getByRole('button', { name: '确认合并' }));

    await waitFor(() =>
      expect(mergeCandidates).toHaveBeenCalledWith({
        source_ids: ['kp-1', 'kp-2'],
        target_id: 'kp-1',
        title: '世界运动',
        summary: '足球成为全球运动的原因',
        point_type: 'concept',
        accept: false,
      }),
    );
  });

  it('splits one candidate into pending items', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('button', { name: '拆分 世界运动' }));
    await user.click(screen.getByRole('button', { name: '确认拆分' }));

    await waitFor(() =>
      expect(splitCandidate).toHaveBeenCalledWith({
        candidate_id: 'kp-1',
        items: [
          { title: '世界运动（一）', summary: '', point_type: 'concept' },
          { title: '世界运动（二）', summary: '', point_type: 'concept' },
        ],
      }),
    );
  });

  it('keeps split items between two and one hundred', async () => {
    renderPage();
    fireEvent.click(screen.getByRole('button', { name: '拆分 世界运动' }));

    let deleteButtons = screen.getAllByRole('button', {
      name: /删除拆分项/,
    });
    expect(deleteButtons).toHaveLength(2);
    expect(deleteButtons[0]).toBeDisabled();
    expect(deleteButtons[1]).toBeDisabled();

    const add = screen.getByRole('button', { name: '增加拆分项' });
    for (let index = 2; index < 100; index += 1) {
      fireEvent.click(add);
    }

    expect(
      screen.getAllByRole('button', { name: /删除拆分项/ }),
    ).toHaveLength(100);
    expect(add).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: '删除拆分项 1' }));
    expect(
      screen.getAllByRole('button', { name: /删除拆分项/ }),
    ).toHaveLength(99);
    expect(add).toBeEnabled();
  });

  it('caps explicit selection at 100 candidates', async () => {
    candidateReviewState.data = {
      structure_id: 'structure-1',
      version_id: 'version-1',
      nodes: [
        {
          node_id: 'node-1',
          parent_node_id: null,
          node_key: 'unit-1',
          node_type: 'unit',
          label: null,
          position: 1,
          slug: 'unit-1',
          title: 'Unit 1',
          summary: '',
          source_refs: [],
          candidates: Array.from({ length: 101 }, (_, index) => ({
            knowledge_point_id: `kp-${index + 1}`,
            content_structure_id: 'structure-1',
            content_node_id: 'node-1',
            candidate_key: `unit-1-kp-${index + 1}`,
            point_type: 'concept',
            origin: 'generated',
            candidate_status: 'pending',
            position: index + 1,
            slug: `candidate-${index + 1}`,
            title: `候选 ${index + 1}`,
            summary: '',
            source_refs: [],
            confidence: 0.9,
            status: 'review',
            created_at: null,
          })),
        },
      ],
    };
    renderPage();

    const checkboxes = screen.getAllByRole('checkbox');
    for (const checkbox of checkboxes.slice(0, 100)) {
      fireEvent.click(checkbox);
    }

    expect(screen.getByText(/最多选择 100 个知识点/)).toBeInTheDocument();
    expect(checkboxes[100]).toBeDisabled();
    fireEvent.click(checkboxes[100]);
    const accept = screen.getByRole('button', { name: '接受所选' });
    expect(accept).toBeEnabled();
    fireEvent.click(accept);

    await waitFor(() => expect(acceptCandidates).toHaveBeenCalledTimes(1));
    expect(acceptCandidates.mock.calls[0][0].candidateIds).toHaveLength(100);
    expect(acceptCandidates.mock.calls[0][0].candidateIds).not.toContain('kp-101');
  });
});
