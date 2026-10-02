import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import TextbooksPage from '../TextbooksPage';

const state = vi.hoisted(() => ({
  textbooks: [] as Array<Record<string, unknown>>,
}));

vi.mock('../queries', () => ({
  useManagedTextbookLibrary: () => ({ data: state.textbooks, isLoading: false }),
}));

beforeEach(() => {
  state.textbooks = [{
    textbook_id: 'textbook-1',
    title: '英语第二册',
    structure_status: 'ready',
    materials: { ready: 7, total: 12 },
    current_job: null,
    updated_at: '2026-10-02T06:00:00Z',
  }];
});

describe('TextbooksPage', () => {
  it('opens a textbook directly in its workbench', async () => {
    const user = userEvent.setup();
    function LocationProbe() {
      return <output data-testid="location">{useLocation().pathname}</output>;
    }
    render(<MemoryRouter initialEntries={['/textbooks']}><Routes><Route path="/textbooks" element={<TextbooksPage />} /><Route path="*" element={<LocationProbe />} /></Routes></MemoryRouter>);

    expect(screen.getByRole('heading', { name: '教材' })).toBeInTheDocument();
    expect(screen.getByText('英语第二册')).toBeInTheDocument();
    await user.click(screen.getByRole('link', { name: '打开 英语第二册' }));
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/textbooks/textbook-1'));
  });

  it('shows structure and committed lesson counts without versions or review state', () => {
    render(<MemoryRouter><TextbooksPage /></MemoryRouter>);

    expect(screen.getByRole('columnheader', { name: '教材' })).toBeInTheDocument();
    expect(screen.getByText('结构已就绪')).toBeInTheDocument();
    expect(screen.getByText('7 / 12')).toBeInTheDocument();
    expect(screen.queryByText(/版本|待审阅|发布/)).not.toBeInTheDocument();
  });

  it('links the current job to the workbench activity panel', () => {
    state.textbooks = [{
      ...state.textbooks[0],
      current_job: {
        job_id: 'book-job-1',
        kind: 'materials',
        status: 'running',
        total_items: 5,
        succeeded_items: 2,
        failed_items: 0,
        cancelled_items: 0,
        not_run_items: 0,
        high_water_seq: 8,
        activity_status: 'available',
        created_at: '2026-10-02T06:00:00Z',
        started_at: '2026-10-02T06:00:01Z',
        finished_at: null,
        safe_error: null,
      },
    }];
    render(<MemoryRouter><TextbooksPage /></MemoryRouter>);

    expect(screen.getByRole('link', { name: '查看 英语第二册 的处理活动' })).toHaveAttribute(
      'href',
      '/textbooks/textbook-1?activity=book-job-1',
    );
  });

  it('sends new textbook creation to the library source flow', () => {
    render(<MemoryRouter><TextbooksPage /></MemoryRouter>);

    expect(screen.getByRole('link', { name: '从图书馆添加' })).toHaveAttribute(
      'href',
      '/documents?useAsTextbook=1',
    );
  });
});
