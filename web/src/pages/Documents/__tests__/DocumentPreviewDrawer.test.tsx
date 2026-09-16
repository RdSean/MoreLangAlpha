import { act, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
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
  artifactDownloadUrl: (id: string) => `/api/v1/document-artifacts/${id}/download`,
  fetchArtifactText: (...args: unknown[]) => fetchArtifactText(...args),
}));
vi.mock('@/pages/ChatAgent/components/Markdown', () => ({ default: ({ content }: { content: string }) => <div>{content}</div> }));
vi.mock('@/pages/ChatAgent/components/viewers/PdfViewer', () => ({ default: () => <div data-testid="pdf-viewer">PDF viewer</div> }));
vi.mock('@/pages/ChatAgent/components/viewers/PreviewViewer', () => ({
  default: ({ documentData, documentViewMode, isDragging }: { documentData?: ArrayBuffer; documentViewMode?: string; isDragging?: boolean }) => {
    if (previewViewerState.shouldThrow) throw new Error('detached ArrayBuffer');
    return (
      <div data-testid="preview-viewer" data-has-document-data={String(Boolean(documentData))} data-document-mode={documentViewMode} data-dragging={String(Boolean(isDragging))}>
        Preview viewer
        {isDragging && <div data-testid="preview-drag-overlay" />}
      </div>
    );
  },
}));

import DocumentPreviewDrawer from '../components/DocumentPreviewDrawer';

interface DrawerProps {
  open?: boolean;
  documentId?: string;
  onOpenChange?: (open: boolean) => void;
  onOpenParser?: (documentId: string) => void;
}

function drawerTree(props: DrawerProps = {}) {
  return (
    <MemoryRouter initialEntries={['/documents']}>
      <Routes>
        <Route
          path="/documents"
          element={
            <DocumentPreviewDrawer
              open={props.open ?? true}
              documentId={props.documentId ?? 'doc-1'}
              onOpenChange={props.onOpenChange ?? vi.fn()}
              onOpenParser={props.onOpenParser}
            />
          }
        />
        <Route
          path="/documents/:documentId"
          element={<output data-testid="document-detail-route">document detail route</output>}
        />
      </Routes>
    </MemoryRouter>
  );
}

function renderDrawer(props: DrawerProps = {}) {
  return render(drawerTree(props));
}

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
    renderDrawer();
    expect(screen.getByRole('tablist', { name: 'Document content' })).toHaveClass('documents-preview-segmented');
    expect(screen.getByRole('tab', { name: 'Original file' })).toHaveAttribute('aria-selected', 'true');
    await user.click(screen.getByRole('tab', { name: 'Parsed file' }));
    expect(await screen.findByText('# Lesson')).toBeInTheDocument();
    expect(fetchArtifactText).toHaveBeenCalledWith('art-1');
  });

  it('points the parsed tab at the stored images', async () => {
    // The markdown references images by bare filename and the bytes live in
    // artifacts, so what reaches the renderer has to be the artifact URL.
    useDocumentArtifacts.mockReturnValue({
      data: [
        { artifact_id: 'art-1', producer_job_id: 'job-1', artifact_kind: 'primary_document', format: 'markdown', media_type: 'text/markdown' },
        { artifact_id: 'art-img', producer_job_id: 'job-1', artifact_kind: 'embedded_image', format: 'jpeg', media_type: 'image/jpeg', relative_path: 'a_img.jpg' },
      ],
    });
    fetchArtifactText.mockResolvedValue('![a picture](a_img.jpg)');

    const user = userEvent.setup();
    renderDrawer();
    await user.click(screen.getByRole('tab', { name: 'Parsed file' }));

    expect(
      await screen.findByText(/api\/v1\/document-artifacts\/art-img\/download/),
    ).toBeInTheDocument();
  });

  it('carries one sliding pill between the two file tabs', async () => {
    // The pill is what animates; exactly one exists, and the tab it belongs to
    // is the selected one. `layoutId` is what makes it travel (see AnimatedTabs).
    const user = userEvent.setup();
    const { container } = renderDrawer();

    const pills = () => container.querySelectorAll('.documents-preview-tab-pill');
    expect(pills()).toHaveLength(1);
    expect(screen.getByRole('tab', { name: 'Original file' }).contains(pills()[0])).toBe(true);

    await user.click(screen.getByRole('tab', { name: 'Parsed file' }));

    expect(pills()).toHaveLength(1);
    expect(screen.getByRole('tab', { name: 'Parsed file' }).contains(pills()[0])).toBe(true);
  });

  it('shows an empty state and parser action when no Markdown artifact exists', async () => {
    useDocumentArtifacts.mockReturnValue({ data: [] });
    const onOpenParser = vi.fn();
    const user = userEvent.setup();
    renderDrawer({ onOpenParser });
    await user.click(screen.getByRole('tab', { name: 'Parsed file' }));
    await user.click(screen.getByRole('button', { name: 'Start parsing' }));
    expect(onOpenParser).toHaveBeenCalledWith('doc-1');
  });

  it('supports continuous and single-page source controls plus fullscreen', async () => {
    const user = userEvent.setup();
    renderDrawer();

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

  it('keeps the viewer in drag mode until the divider drag ends', async () => {
    renderDrawer();

    const viewer = await screen.findByTestId('preview-viewer');
    const divider = screen.getByRole('separator', { name: 'Resize preview' });
    expect(viewer).toHaveAttribute('data-dragging', 'false');
    expect(screen.queryByTestId('preview-drag-overlay')).not.toBeInTheDocument();

    fireEvent.mouseDown(divider, { clientX: 900 });

    expect(viewer).toHaveAttribute('data-dragging', 'true');
    expect(screen.getByTestId('preview-drag-overlay')).toBeInTheDocument();
    expect(document.body.style.userSelect).toBe('none');

    fireEvent.mouseMove(window, { clientX: 820 });
    expect(viewer).toHaveAttribute('data-dragging', 'true');

    fireEvent.mouseUp(window);

    expect(viewer).toHaveAttribute('data-dragging', 'false');
    expect(screen.queryByTestId('preview-drag-overlay')).not.toBeInTheDocument();
    expect(document.body.style.userSelect).toBe('');
  });

  it('resizes from the rendered drawer width on first keyboard interaction', async () => {
    const user = userEvent.setup();
    renderDrawer();

    const drawer = screen.getByRole('complementary', { name: 'Document preview' });
    const divider = screen.getByRole('separator', { name: 'Resize preview' });
    expect(divider).toHaveAttribute('tabindex', '0');
    expect(divider).toHaveAttribute('aria-valuemin', '420');
    expect(divider).toHaveAttribute('aria-valuemax', '1100');
    expect(divider).toHaveAttribute('aria-valuenow', '680');

    const rect = vi.spyOn(drawer, 'getBoundingClientRect').mockReturnValue({
      x: 0,
      y: 0,
      width: 430,
      height: 800,
      top: 0,
      right: 430,
      bottom: 800,
      left: 0,
      toJSON: () => ({}),
    });
    try {
      act(() => divider.focus());
      expect(divider).toHaveAttribute('aria-valuenow', '430');

      await user.keyboard('{ArrowLeft}');
      expect(divider).toHaveAttribute('aria-valuenow', '420');

      await user.keyboard('{ArrowRight}');
      expect(divider).toHaveAttribute('aria-valuenow', '440');
    } finally {
      rect.mockRestore();
    }
  });

  it('removes measured inline dimensions when the drawer closes', () => {
    const view = renderDrawer();
    const drawer = screen.getByRole('complementary', { name: 'Document preview' });
    const divider = screen.getByRole('separator', { name: 'Resize preview' });
    const panel = drawer.parentElement;
    expect(panel).not.toBeNull();
    const rect = vi.spyOn(drawer, 'getBoundingClientRect').mockReturnValue({
      x: 0,
      y: 0,
      width: 430,
      height: 800,
      top: 0,
      right: 430,
      bottom: 800,
      left: 0,
      toJSON: () => ({}),
    });
    try {
      act(() => divider.focus());
      expect(panel).toHaveStyle({ width: '430px', flexBasis: '430px' });
      fireEvent.mouseDown(divider, { clientX: 900 });
      fireEvent.mouseMove(window, { clientX: 820 });
      fireEvent.mouseUp(window);

      view.rerender(drawerTree({ open: false }));

      expect(screen.queryByRole('complementary', { name: 'Document preview' })).not.toBeInTheDocument();
      expect(screen.getByRole('complementary', { name: 'Document preview', hidden: true })).toBe(drawer);
      expect(panel).not.toHaveClass('is-open');
      expect(panel).toHaveAttribute('aria-hidden', 'true');
      expect(panel).toHaveAttribute('inert');
      expect(panel?.style.width).toBe('');
      expect(panel?.style.flexBasis).toBe('');
    } finally {
      rect.mockRestore();
    }
  });

  it('keeps closed drawer controls out of the keyboard tab order', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/documents']}>
        <button type="button">Before drawer</button>
        <DocumentPreviewDrawer
          open={false}
          documentId="doc-1"
          onOpenChange={vi.fn()}
        />
        <button type="button">After drawer</button>
      </MemoryRouter>,
    );

    const before = screen.getByRole('button', { name: 'Before drawer' });
    const after = screen.getByRole('button', { name: 'After drawer' });
    before.focus();
    await user.tab();
    expect(after).toHaveFocus();
    await user.tab({ shift: true });
    expect(before).toHaveFocus();
  });

  it('links to the independent document detail page', async () => {
    const user = userEvent.setup();
    renderDrawer();

    await user.click(screen.getByRole('link', { name: 'View details' }));

    expect(screen.getByTestId('document-detail-route')).toBeInTheDocument();
  });

  it('contains a viewer failure instead of blanking the page', async () => {
    // Regression: a render-phase throw from the viewer used to escape the
    // drawer entirely — the app unmounted and the user got a blank page, which
    // is what a remount with a pdf.js-detached buffer produced.
    previewViewerState.shouldThrow = true;
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});

    renderDrawer();

    expect(await screen.findByText('The original file could not be loaded.')).toBeInTheDocument();
    // The drawer is still mounted — the failure stayed local to the viewer.
    expect(screen.getByRole('tab', { name: 'Original file' })).toBeInTheDocument();
    spy.mockRestore();
  });
});
