import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../components/DatasetGrid', () => ({ default: () => <div data-testid="dataset-grid" /> }));
vi.mock('../components/DocumentTable', () => ({ default: () => <div data-testid="document-table" /> }));
vi.mock('../components/DocumentWizard', () => ({ default: () => null }));
vi.mock('../components/DocumentPreviewDrawer', () => ({
  default: ({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) => (
    open ? <button type="button" aria-label="Close preview" onClick={() => onOpenChange(false)}>Close preview</button> : null
  ),
}));

import DocumentsPage from '../DocumentsPage';

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location-search">{location.search}</output>;
}

function renderPage(initialEntry = '/documents') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]} future={{ v7_startTransition: true }}>
      <Routes>
        <Route path="/documents" element={<><DocumentsPage /><LocationProbe /></>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('DocumentsPage', () => {
  it('opens with Dataset and All Documents tabs', () => {
    renderPage();

    expect(screen.getByRole('heading', { name: 'Knowledge Library' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Datasets' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'All documents' })).toHaveAttribute('aria-selected', 'false');
    expect(screen.getByRole('tabpanel', { name: 'Datasets' })).toBeInTheDocument();
  });

  it('preserves independent search and page state when switching tabs', async () => {
    const user = userEvent.setup();
    renderPage('/documents?tab=datasets&datasets_q=math&datasets_page=2&documents_q=report&documents_page=4');

    await user.click(screen.getByRole('tab', { name: 'All documents' }));
    let params = new URLSearchParams(screen.getByTestId('location-search').textContent ?? '');
    expect(Object.fromEntries(params)).toMatchObject({
      tab: 'documents',
      datasets_q: 'math',
      datasets_page: '2',
      documents_q: 'report',
      documents_page: '4',
    });

    await user.click(screen.getByRole('tab', { name: 'Datasets' }));
    params = new URLSearchParams(screen.getByTestId('location-search').textContent ?? '');
    expect(Object.fromEntries(params)).toMatchObject({
      tab: 'datasets',
      datasets_q: 'math',
      datasets_page: '2',
      documents_q: 'report',
      documents_page: '4',
    });
  });

  it('closes the preview without navigating away from the current document URL', async () => {
    const user = userEvent.setup();
    renderPage('/documents?document=doc-1');

    await user.click(screen.getByRole('button', { name: 'Close preview' }));
    expect(screen.getByTestId('location-search')).toHaveTextContent('document=doc-1');
    expect(screen.queryByRole('button', { name: 'Close preview' })).not.toBeInTheDocument();
  });
});
