import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { DatasetSummary } from '../types';

const useDocumentDatasets = vi.fn();
const createDataset = { mutateAsync: vi.fn(), isPending: false };
const updateDataset = { mutateAsync: vi.fn(), isPending: false };
const deleteDataset = { mutateAsync: vi.fn(), isPending: false };

vi.mock('../hooks', () => ({
  useDocumentDatasets: (...args: unknown[]) => useDocumentDatasets(...args),
  useDocumentMutations: () => ({ createDataset, updateDataset, deleteDataset }),
}));

import DatasetGrid from '../components/DatasetGrid';

const dataset: DatasetSummary = {
  dataset_id: 'dts-A1b2C3d4E5f6',
  name: 'Mathematics',
  description: 'Algebra and geometry references',
  document_count: 3,
  updated_at: '2026-09-05T08:00:00Z',
};

describe('DatasetGrid', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useDocumentDatasets.mockReturnValue({
      data: { items: [dataset], total: 13, limit: 12, offset: 12 },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
  });

  it('requests a bounded server page and renders compact Dataset cards', async () => {
    const onOpenDataset = vi.fn();
    const user = userEvent.setup();
    render(
      <DatasetGrid
        query="math"
        page={2}
        onQueryChange={vi.fn()}
        onPageChange={vi.fn()}
        onOpenDataset={onOpenDataset}
      />,
    );

    expect(useDocumentDatasets).toHaveBeenCalledWith({ query: 'math', limit: 12, offset: 12 });
    expect(screen.getByText('Mathematics')).toBeInTheDocument();
    expect(screen.getByText('Algebra and geometry references')).toBeInTheDocument();
    expect(screen.getByText('3 documents')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Open Mathematics' }));
    expect(onOpenDataset).toHaveBeenCalledWith(dataset);
  });

  it('creates a Dataset from the toolbar dialog', async () => {
    createDataset.mutateAsync.mockResolvedValue({ ...dataset, name: 'Science' });
    const user = userEvent.setup();
    render(
      <DatasetGrid
        query=""
        page={1}
        onQueryChange={vi.fn()}
        onPageChange={vi.fn()}
        onOpenDataset={vi.fn()}
      />,
    );

    await user.click(screen.getByRole('button', { name: 'Create dataset' }));
    await user.type(screen.getByLabelText('Name'), 'Science');
    await user.type(screen.getByLabelText('Description'), 'Reusable science files');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    expect(createDataset.mutateAsync).toHaveBeenCalledWith({
      name: 'Science',
      description: 'Reusable science files',
    });
  });
});
