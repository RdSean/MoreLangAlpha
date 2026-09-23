import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import TextbooksPage from '../TextbooksPage';

const state = vi.hoisted(() => ({
  textbooks: [] as Array<Record<string, unknown>>,
  members: [] as Array<{ user_id: string; name: string; role: 'parent' | 'student' }>,
  create: vi.fn(),
  start: vi.fn(),
  run: vi.fn(),
  publish: vi.fn(),
  assign: vi.fn(),
}));

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ member: { user_id: 'parent-1', name: '家长', role: 'parent' } }),
}));

vi.mock('../queries', () => ({
  useEducationMembers: () => ({ data: state.members }),
  useTextbookLibrary: () => ({ data: state.textbooks, isLoading: false }),
  useTextbookMutations: () => ({
    create: { mutateAsync: state.create, isPending: false },
    start: { mutateAsync: state.start, isPending: false },
    run: { mutateAsync: state.run, isPending: false },
    publish: { mutateAsync: state.publish, isPending: false },
    assign: { mutateAsync: state.assign, isPending: false },
  }),
}));

beforeEach(() => {
  state.textbooks = [{
    textbook_id: 'textbook-1',
    title: '英语第二册',
    latest_version_sequence: 1,
    latest_version_status: 'review',
    chapter_count: 1,
    assignment_count: 0,
  }];
  state.members = [{ user_id: 'student-1', name: '学生', role: 'student' }];
  state.create.mockReset().mockResolvedValue({ textbook_id: 'textbook-2' });
  state.start.mockReset().mockResolvedValue({ job_id: 'job-1' });
  state.run.mockReset().mockResolvedValue(undefined);
  state.publish.mockReset().mockResolvedValue({ publication_id: 'publication-1' });
  state.assign.mockReset().mockResolvedValue(undefined);
});

describe('TextbooksPage', () => {
  it('lets a parent create a reusable family textbook from the library', async () => {
    function LocationProbe() {
      return <output data-testid="location">{useLocation().pathname}</output>;
    }
    render(<MemoryRouter initialEntries={['/textbooks']}><Routes><Route path="/textbooks" element={<TextbooksPage />} /><Route path="*" element={<LocationProbe />} /></Routes></MemoryRouter>);

    expect(screen.getByRole('heading', { name: '教材加工' })).toBeInTheDocument();
    expect(screen.getByText('英语第二册')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '新建教材' }));
    fireEvent.change(screen.getByLabelText('教材名称'), { target: { value: '语文上册' } });
    fireEvent.click(screen.getByRole('button', { name: '创建教材' }));

    await waitFor(() => expect(state.create).toHaveBeenCalledWith({ title: '语文上册' }));
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/textbooks/textbook-2'));
  });

  it('uses a compact table that exposes the current version state', () => {
    render(<MemoryRouter><TextbooksPage /></MemoryRouter>);

    expect(screen.getByRole('columnheader', { name: '教材' })).toBeInTheDocument();
    expect(screen.getByText('待审阅')).toBeInTheDocument();
    expect(screen.getByText('1 章')).toBeInTheDocument();
  });

  it('shows the latest book-pipeline job state instead of the review fallback', () => {
    state.textbooks = [{
      ...state.textbooks[0],
      latest_processing_job_id: 'book-job-1',
      latest_processing_job_status: 'failed',
      latest_processing_error: 'invalid package',
    }];
    render(<MemoryRouter><TextbooksPage /></MemoryRouter>);

    expect(screen.getByText('加工失败')).toBeInTheDocument();
    expect(screen.queryByText('待审阅')).not.toBeInTheDocument();
  });
});
