import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { LearningAssignment } from '../types';
import StudentTextbooksPage from '../StudentTextbooksPage';

const state = vi.hoisted(() => ({
  role: 'student' as 'student' | 'parent',
  data: [] as LearningAssignment[],
  isLoading: false,
  isError: false,
  enabled: vi.fn(),
  refetch: vi.fn(),
}));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ member: { role: state.role } }) }));
vi.mock('../queries', () => ({ useLearningAssignments: (enabled: boolean) => {
  state.enabled(enabled);
  return state;
} }));

function renderPage() {
  return render(<MemoryRouter initialEntries={['/education/learn']}><Routes>
    <Route path="/education/learn" element={<StudentTextbooksPage />} />
    <Route path="/textbooks" element={<p>家长教材管理</p>} />
  </Routes></MemoryRouter>);
}

beforeEach(() => {
  state.role = 'student';
  state.data = [];
  state.isLoading = false;
  state.isError = false;
  vi.clearAllMocks();
});

describe('StudentTextbooksPage', () => {
  it('shows assigned textbooks with progress and a student learning link', () => {
    state.data = [{ assignment_id: 'assignment-1', textbook_id: 'book-1', textbook_title: 'Reading Explorer 3', structure_id: 'structure-1', knowledge_point_count: 10, completed_knowledge_point_count: 3 }];
    renderPage();
    expect(state.enabled).toHaveBeenCalledWith(true);
    expect(screen.getByRole('link', { name: '继续学习 Reading Explorer 3' })).toHaveAttribute('href', '/education/learn/assignment-1');
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '3');
    expect(screen.getByText('3/10 个知识点已学习')).toBeInTheDocument();
  });
  it('shows the loading state', () => {
    state.isLoading = true;
    renderPage();
    expect(screen.getByRole('status')).toHaveTextContent('正在加载教材');
  });
  it('retries a failed request', () => {
    state.isError = true;
    renderPage();
    expect(screen.getByRole('alert')).toHaveTextContent('教材加载失败');
    fireEvent.click(screen.getByRole('button', { name: '重试' }));
    expect(state.refetch).toHaveBeenCalledOnce();
  });
  it('shows the unassigned state', () => {
    renderPage();
    expect(screen.getByText('暂未分配教材。')).toBeInTheDocument();
  });
  it('sends parents to textbook management without fetching student assignments', () => {
    state.role = 'parent';
    renderPage();
    expect(state.enabled).toHaveBeenCalledWith(false);
    expect(screen.getByText('家长教材管理')).toBeInTheDocument();
  });
});
