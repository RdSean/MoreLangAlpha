import { act, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { DocumentSummary } from '../types';

const useDocuments = vi.fn();
const useDocumentDatasets = vi.fn();
const useDocumentTags = vi.fn();
const deleteDocument = { mutateAsync: vi.fn(), isPending: false };
const updateDocument = { mutateAsync: vi.fn(), isPending: false };

vi.mock('../hooks', () => ({
  useDocuments: (...args: unknown[]) => useDocuments(...args),
  useDocumentDatasets: (...args: unknown[]) => useDocumentDatasets(...args),
  useDocumentTags: (...args: unknown[]) => useDocumentTags(...args),
  useDocumentMutations: () => ({ deleteDocument, updateDocument }),
}));

import DocumentTable, { type DocumentTableFilters } from '../components/DocumentTable';

const document: DocumentSummary = {
  document_id: 'doc-A1b2C3d4E5f6',
  original_filename: 'Algebra handbook.pdf',
  media_type: 'application/pdf',
  document_format: 'pdf',
  source_size_bytes: 1_572_864,
  source_sha256: 'abc',
  datasets: [{ dataset_id: 'dts-A1b2C3d4E5f6', name: 'Mathematics' }],
  tags: [{ tag_id: 'tag-A1b2C3d4E5f6', name: 'Reference' }],
  classification: 'text_based',
  parse_status: 'completed',
  updated_at: '2026-09-05T08:00:00Z',
};

const filters: DocumentTableFilters = {
  query: '',
  datasetId: '',
  tagIds: [],
  mediaType: '',
  classification: '',
  parseStatus: '',
};

describe('DocumentTable', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useDocuments.mockReturnValue({
      data: { items: [document], total: 61, limit: 20, offset: 40 },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    useDocumentDatasets.mockReturnValue({
      data: { items: document.datasets, total: 1, limit: 100, offset: 0 },
    });
    useDocumentTags.mockReturnValue({ data: document.tags });
  });

  it('requests a bounded server page and renders the returned document without local filtering', () => {
    render(
      <DocumentTable
        datasetId="dts-A1b2C3d4E5f6"
        filters={{ ...filters, query: 'does-not-match-row' }}
        page={3}
        onFiltersChange={vi.fn()}
        onPageChange={vi.fn()}
        onOpenDocument={vi.fn()}
      />,
    );

    expect(useDocuments).toHaveBeenCalledWith(expect.objectContaining({
      query: 'does-not-match-row',
      dataset_id: 'dts-A1b2C3d4E5f6',
      limit: 20,
      offset: 40,
    }));
    expect(screen.getByText('Algebra handbook.pdf')).toBeInTheDocument();
    expect(screen.getByText('Mathematics')).toBeInTheDocument();
    expect(screen.getByText('Reference')).toBeInTheDocument();
    expect(screen.getByText('1.5 MB')).toBeInTheDocument();
  });

  it('debounces filename search and resets pagination when a filter changes', () => {
    vi.useFakeTimers();
    const onFiltersChange = vi.fn();
    render(
      <DocumentTable
        filters={filters}
        page={3}
        onFiltersChange={onFiltersChange}
        onPageChange={vi.fn()}
        onOpenDocument={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText('Search filename'), { target: { value: 'report' } });
    expect(onFiltersChange).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(300));
    expect(onFiltersChange).toHaveBeenCalledWith({ ...filters, query: 'report' }, true);

    fireEvent.change(screen.getByLabelText('Classification'), { target: { value: 'mixed' } });
    expect(onFiltersChange).toHaveBeenLastCalledWith({ ...filters, classification: 'mixed' }, true);
    vi.useRealTimers();
  });

  it('opens a returned document and advances using server pagination', async () => {
    const onOpenDocument = vi.fn();
    const onPageChange = vi.fn();
    const user = userEvent.setup();
    render(
      <DocumentTable
        filters={filters}
        page={3}
        onFiltersChange={vi.fn()}
        onPageChange={onPageChange}
        onOpenDocument={onOpenDocument}
      />,
    );

    await user.click(screen.getByRole('button', { name: 'Open Algebra handbook.pdf' }));
    expect(onOpenDocument).toHaveBeenCalledWith(document);
    await user.click(screen.getByRole('button', { name: 'Next page' }));
    expect(onPageChange).toHaveBeenCalledWith(4);
  });
});
