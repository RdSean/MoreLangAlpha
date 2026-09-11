import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const fetchArtifactText = vi.fn();
const useDocument = vi.fn();
const useDocumentJobs = vi.fn();
const useDocumentArtifacts = vi.fn();
// A viewer can fail on data it cannot read (a buffer pdf.js already detached,
// a malformed file). The drawer has to survive that.
const previewViewerState = vi.hoisted(() => ({ shouldThrow: false }));

vi.mock('../hooks', () => ({
  useDocument: (...args: unknown[]) => useDocument(...args),
  useDocumentJobs: (...args: unknown[]) => useDocumentJobs(...args),
  useDocumentArtifacts: (...args: unknown[]) => useDocumentArtifacts(...args),
}));
vi.mock('../api', () => ({
  documentSourceUrl: (id: string) => `/api/v1/documents/${id}/source`,
  fetchArtifactText: (...args: unknown[]) => fetchArtifactText(...args),
}));
vi.mock('@/pages/ChatAgent/components/Markdown', () => ({ default: ({ content }: { content: string }) => <div>{content}</div> }));
vi.mock('@/pages/ChatAgent/components/viewers/PdfViewer', () => ({ default: () => <div data-testid="pdf-viewer">PDF viewer</div> }));
vi.mock('@/pages/ChatAgent/components/viewers/PreviewViewer', () => ({
  default: ({ documentData, documentViewMode }: { documentData?: ArrayBuffer; documentViewMode?: string }) => {
    if (previewViewerState.shouldThrow) throw new Error('detached ArrayBuffer');
    return (
      <div data-testid="preview-viewer" data-has-document-data={String(Boolean(documentData))} data-document-mode={documentViewMode}>Preview viewer</div>
    );
  },
}));

import DocumentPreviewDrawer from '../components/DocumentPreviewDrawer';

describe('DocumentPreviewDrawer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    previewViewerState.shouldThrow = false;
    useDocument.mockReturnValue({ data: { original_filename: 'lesson.pdf', parse_status: 'completed' } });
    useDocumentJobs.mockReturnValue({ data: [{ job_id: 'job-1', status: 'completed' }] });
    useDocumentArtifacts.mockReturnValue({ data: [{ artifact_id: 'art-1', producer_job_id: 'job-1', artifact_kind: 'primary_document', format: 'markdown', media_type: 'text/markdown' }] });
    fetchArtifactText.mockResolvedValue('# Lesson');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, arrayBuffer: async () => new ArrayBuffer(8) }));
  });

  it('defaults to the original tab and can switch to the parsed Markdown tab', async () => {
    const user = userEvent.setup();
    render(<DocumentPreviewDrawer open documentId="doc-1" onOpenChange={vi.fn()} />);
    expect(screen.getByRole('tablist', { name: 'Document content' })).toHaveClass('documents-preview-segmented');
    expect(screen.getByRole('tab', { name: 'Original file' })).toHaveAttribute('aria-selected', 'true');
    await user.click(screen.getByRole('tab', { name: 'Parsed file' }));
    expect(await screen.findByText('# Lesson')).toBeInTheDocument();
    expect(fetchArtifactText).toHaveBeenCalledWith('art-1');
  });

  it('shows an empty state and parser action when no Markdown artifact exists', async () => {
    useDocumentArtifacts.mockReturnValue({ data: [] });
    const onOpenParser = vi.fn();
    const user = userEvent.setup();
    render(<DocumentPreviewDrawer open documentId="doc-1" onOpenChange={vi.fn()} onOpenParser={onOpenParser} />);
    await user.click(screen.getByRole('tab', { name: 'Parsed file' }));
    await user.click(screen.getByRole('button', { name: 'Start parsing' }));
    expect(onOpenParser).toHaveBeenCalledWith('doc-1');
  });

  it('supports continuous and single-page source controls plus fullscreen', async () => {
    const user = userEvent.setup();
    render(<DocumentPreviewDrawer open documentId="doc-1" onOpenChange={vi.fn()} />);

    expect(screen.getByRole('separator', { name: 'Resize preview' })).toHaveClass('chat-split-divider');
    expect(await screen.findByTestId('preview-viewer')).toBeInTheDocument();
    expect(screen.getByTestId('preview-viewer')).toHaveAttribute('data-has-document-data', 'true');
    expect(screen.getByRole('tab', { name: 'Continuous' })).toHaveAttribute('aria-selected', 'true');
    await user.click(screen.getByRole('tab', { name: 'Single page' }));
    expect(screen.getByRole('tab', { name: 'Single page' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('button', { name: 'Next page' })).toBeEnabled();
    await user.click(screen.getByRole('button', { name: 'Next page' }));
    expect(screen.getByText('2')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'View full screen' }));
    expect(screen.getByRole('button', { name: 'Exit full screen' })).toBeInTheDocument();
  });

  it('contains a viewer failure instead of blanking the page', async () => {
    // Regression: a render-phase throw from the viewer used to escape the
    // drawer entirely — the app unmounted and the user got a blank page, which
    // is what a remount with a pdf.js-detached buffer produced.
    previewViewerState.shouldThrow = true;
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});

    render(<DocumentPreviewDrawer open documentId="doc-1" onOpenChange={vi.fn()} />);

    expect(await screen.findByText('The original file could not be loaded.')).toBeInTheDocument();
    // The drawer is still mounted — the failure stayed local to the viewer.
    expect(screen.getByRole('tab', { name: 'Original file' })).toBeInTheDocument();
    spy.mockRestore();
  });
});
