import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import TextbooksPage from '../TextbooksPage';
vi.mock('../components/BookAssignmentDialog', () => ({ BookAssignmentDialog: ({ textbookId }: { textbookId: string }) => <div role="dialog" aria-label="给学生使用">{textbookId}</div> }));

const state = vi.hoisted(() => ({
  textbooks: [] as Array<Record<string, unknown>>,
  role: 'parent',
  remove: vi.fn(),
  uploadCover: vi.fn(),
  removeCover: vi.fn(),
}));

vi.mock('../queries', () => ({
  useManagedTextbookLibrary: () => ({ data: state.textbooks, isLoading: false }),
  useDeleteManagedTextbook: () => ({ mutateAsync: state.remove, isPending: false }),
  useUploadTextbookCover: () => ({ mutateAsync: state.uploadCover, isPending: false }),
  useDeleteTextbookCover: () => ({ mutateAsync: state.removeCover, isPending: false }),
}));

vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ member: { role: state.role } }) }));

beforeEach(() => {
  state.role = 'parent';
  state.remove.mockReset().mockResolvedValue(undefined);
  state.uploadCover.mockReset().mockResolvedValue({ cover_available: true });
  state.removeCover.mockReset().mockResolvedValue({ cover_available: false });
  state.textbooks = [{
    textbook_id: 'textbook-1',
    title: '英语第二册',
    structure_status: 'ready',
    materials: { ready: 7, total: 12 },
    current_job: null,
    updated_at: '2026-10-02T06:00:00Z',
    cover_available: false,
    cover_updated_at: null,
  }];
});

describe('TextbooksPage', () => {
  it('assigns students and manages the cover from the textbook more menu', async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><TextbooksPage /></MemoryRouter>);
    await user.click(screen.getByRole('button', { name: '英语第二册 更多' }));
    await user.click(screen.getByRole('menuitem', { name: '给学生使用' }));
    expect(screen.getByRole('dialog', { name: '给学生使用' })).toHaveTextContent('textbook-1');

    await user.click(screen.getByRole('button', { name: '英语第二册 更多' }));
    expect(screen.getByRole('menuitem', { name: '设置封面' })).toBeInTheDocument();
  });

  it('uploads a selected image and renders an existing cover', async () => {
    state.textbooks[0].cover_available = true;
    const user = userEvent.setup();
    const { rerender } = render(<MemoryRouter><TextbooksPage /></MemoryRouter>);
    expect(screen.getByRole('img', { name: '英语第二册封面' })).toHaveAttribute(
      'src',
      '/api/v1/education/textbooks/textbook-1/cover',
    );

    await user.click(screen.getByRole('button', { name: '英语第二册 更多' }));
    await user.click(screen.getByRole('menuitem', { name: '更换封面' }));
    const file = new File(['image'], 'cover.png', { type: 'image/png' });
    await user.upload(screen.getByLabelText('选择英语第二册封面'), file);
    expect(state.uploadCover).toHaveBeenCalledWith({ textbookId: 'textbook-1', file });
    rerender(<MemoryRouter><TextbooksPage /></MemoryRouter>);
  });

  it('removes an existing cover from the card menu', async () => {
    state.textbooks[0].cover_available = true;
    const user = userEvent.setup();
    render(<MemoryRouter><TextbooksPage /></MemoryRouter>);

    await user.click(screen.getByRole('button', { name: '英语第二册 更多' }));
    await user.click(screen.getByRole('menuitem', { name: '移除封面' }));

    expect(state.removeCover).toHaveBeenCalledWith('textbook-1');
  });

  it('explains when a selected cover file has an unsupported type', () => {
    render(<MemoryRouter><TextbooksPage /></MemoryRouter>);
    const file = new File(['text'], 'cover.svg', { type: 'image/svg+xml' });

    fireEvent.change(screen.getByLabelText('选择英语第二册封面'), { target: { files: [file] } });

    expect(screen.getByRole('alert')).toHaveTextContent('封面仅支持 PNG、JPEG 或 WebP 图片');
    expect(state.uploadCover).not.toHaveBeenCalled();
  });

  it('does not expose cover controls to students', async () => {
    state.role = 'student';
    const user = userEvent.setup();
    render(<MemoryRouter><TextbooksPage /></MemoryRouter>);
    expect(screen.queryByRole('button', { name: '英语第二册 更多' })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('选择英语第二册封面')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: '打开 英语第二册' })).toBeInTheDocument();
    expect(user).toBeDefined();
  });
  it('requires confirmation and preserves the library source', async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><TextbooksPage /></MemoryRouter>);
    await user.click(screen.getByRole('button', { name: '英语第二册 更多' }));
    await user.click(screen.getByRole('menuitem', { name: '删除教材' }));
    expect(screen.getByRole('dialog')).toHaveTextContent('图书馆原文件及解析产物会保留');
    expect(state.remove).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: '取消' }));
    expect(state.remove).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: '英语第二册 更多' }));
    await user.click(screen.getByRole('menuitem', { name: '删除教材' }));
    await user.click(screen.getByRole('button', { name: '永久删除' }));
    expect(state.remove).toHaveBeenCalledWith('textbook-1');
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('does not expose deletion to students', () => {
    state.role = 'student';
    render(<MemoryRouter><TextbooksPage /></MemoryRouter>);
    expect(screen.queryByRole('button', { name: '英语第二册 更多' })).not.toBeInTheDocument();
  });

  it('keeps the confirmation open and shows a failed deletion', async () => {
    state.remove.mockRejectedValue({ response: { data: { detail: '教材正在被修改，请稍后重试' } } });
    const user = userEvent.setup();
    render(<MemoryRouter><TextbooksPage /></MemoryRouter>);
    await user.click(screen.getByRole('button', { name: '英语第二册 更多' }));
    await user.click(screen.getByRole('menuitem', { name: '删除教材' }));
    await user.click(screen.getByRole('button', { name: '永久删除' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('教材正在被修改');
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('disables deletion while a task is active', async () => {
    state.textbooks[0].current_job = { job_id: 'active', status: 'running' };
    render(<MemoryRouter><TextbooksPage /></MemoryRouter>);
    await userEvent.setup().click(screen.getByRole('button', { name: '英语第二册 更多' }));
    expect(screen.getByRole('menuitem', { name: '删除教材' })).toHaveAttribute('aria-disabled', 'true');
  });
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

  it('opens the textbook when clicking a non-action area of its card', async () => {
    const user = userEvent.setup();
    function LocationProbe() {
      return <output data-testid="location">{useLocation().pathname}</output>;
    }
    render(<MemoryRouter initialEntries={['/textbooks']}><Routes><Route path="/textbooks" element={<TextbooksPage />} /><Route path="*" element={<LocationProbe />} /></Routes></MemoryRouter>);

    await user.click(screen.getByText('结构已就绪'));

    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/textbooks/textbook-1'));
  });

  it('shows a card with structure and committed lesson counts without versions or review state', () => {
    render(<MemoryRouter><TextbooksPage /></MemoryRouter>);

    expect(screen.getByRole('article', { name: '英语第二册' })).toBeInTheDocument();
    expect(screen.getByText('结构已就绪')).toBeInTheDocument();
    expect(screen.getByText('讲义 7 / 12')).toBeInTheDocument();
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
