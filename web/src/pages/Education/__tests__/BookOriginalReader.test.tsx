import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/i18n';
import { BookOriginalReader } from '../components/BookOriginalReader';
import { firstJsonPage } from '../components/bookOriginalLocation';

const state = vi.hoisted(() => ({
  page: null as number | null,
  error: false,
  refetch: vi.fn(),
  data: new ArrayBuffer(8),
}));
vi.mock('../queries', () => ({
  useManagedBookOriginal: () => ({ data: { bytes: state.data, mediaType: 'application/pdf' }, isLoading: false, isError: state.error, refetch: state.refetch }),
  useManagedBookOriginalLocation: () => ({ data: { page: state.page }, isError: false }),
}));
vi.mock('@/pages/ChatAgent/components/viewers/PdfViewer', () => ({ default: ({ pageNumber, onPageChange, onNumPagesChange }: { pageNumber: number; onPageChange: (page: number) => void; onNumPagesChange: (count: number) => void }) => (
  <div><p>PDF page {pageNumber}</p><button onClick={() => onPageChange(pageNumber + 1)}>next PDF page</button><button onClick={() => onNumPagesChange(20)}>loaded PDF</button></div>
) }));

beforeEach(() => { state.page = null; state.error = false; state.refetch.mockClear(); void i18n.changeLanguage('zh-CN'); });

describe('BookOriginalReader', () => {
  it('uses the earliest valid JSON start page across associated nodes', () => {
    expect(firstJsonPage([{ page_range: { start: 15, label: 'PDF pages' } }, { page_range: { start: 12, label: 'PDF页码' } }, { page_range: null }])).toBe(12);
    expect(firstJsonPage([{ page_range: { start: -1 } }, { page_range: { start: '12' } }])).toBeUndefined();
    expect(firstJsonPage([{ page_range: { start: 12, source: 'printed' } }, { page_range: { start: 15, source: 'derived' } }])).toBeUndefined();
  });
  it('opens the file at its first page without location data', async () => {
    render(<BookOriginalReader textbookId="book" startLine={300} />);
    expect(await screen.findByText('PDF page 1')).toBeInTheDocument();
  });
  it('prefers parser location to JSON and permits manual page navigation', async () => {
    state.page = 12;
    const onPageChange = vi.fn();
    render(<BookOriginalReader textbookId="book" startLine={300} jsonPage={15} onPageChange={onPageChange} />);
    expect(await screen.findByText('PDF page 12')).toBeInTheDocument();
    fireEvent.click(screen.getByText('next PDF page'));
    expect(screen.getByText('PDF page 13')).toBeInTheDocument();
    expect(onPageChange).toHaveBeenCalledWith(13);
  });
  it('uses JSON if no marker exists and falls back when the page exceeds the PDF', async () => {
    render(<BookOriginalReader textbookId="book" startLine={300} jsonPage={300} />);
    expect(await screen.findByText('PDF page 300')).toBeInTheDocument();
    fireEvent.click(screen.getByText('loaded PDF'));
    expect(screen.getByText('PDF page 1')).toBeInTheDocument();
  });
  it('restores a manually selected page on refresh', async () => {
    state.page = 12;
    render(<BookOriginalReader textbookId="book" startLine={300} restoredPage={17} />);
    expect(await screen.findByText('PDF page 17')).toBeInTheDocument();
  });
  it('shows a retry when the original file is unavailable', () => {
    state.error = true;
    render(<BookOriginalReader textbookId="book" />);
    expect(screen.getByRole('alert')).toHaveTextContent('原文件暂不可读');
    fireEvent.click(screen.getByRole('button', { name: '重试' }));
    expect(state.refetch).toHaveBeenCalledTimes(1);
  });
});
