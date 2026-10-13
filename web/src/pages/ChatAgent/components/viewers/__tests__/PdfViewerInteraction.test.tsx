import { useEffect, useState } from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import PdfViewer from '../PdfViewer';

const state = vi.hoisted(() => ({ width: 1200, height: 480, resize: () => {} }));
vi.mock('react-pdf', () => ({
  pdfjs: { GlobalWorkerOptions: {} },
  Document: ({ children, onLoadSuccess }: { children: React.ReactNode; onLoadSuccess: (doc: { numPages: number }) => void }) => {
    useEffect(() => { onLoadSuccess({ numPages: 3 }); }, [onLoadSuccess]);
    return <div>{children}</div>;
  },
  Page: ({ pageNumber, width, scale, onLoadSuccess }: {
    pageNumber: number; width?: number; scale: number;
    onLoadSuccess?: (page: { getViewport: () => { width: number; height: number } }) => void;
  }) => {
    useEffect(() => { onLoadSuccess?.({ getViewport: () => pageNumber === 3 ? { width: 800, height: 600 } : { width: 600, height: 800 } }); }, [pageNumber, onLoadSuccess]);
    return <div data-testid="pdf-page" data-width={width} data-scale={scale}>Page {pageNumber}</div>;
  },
}));
vi.mock('@/pdfjsWorker.ts?worker&url', () => ({ default: 'worker.js' }));

const bytes = new Uint8Array([1, 2, 3]);
function Reader({ keyboardScope = 'document' }: { keyboardScope?: 'document' | 'viewer' }) {
  const [page, setPage] = useState(1);
  return <><textarea aria-label="Chat draft" /><PdfViewer data={bytes} fitPage pageNavigation keyboardScope={keyboardScope} pageNumber={page} onPageChange={setPage} /></>;
}

beforeEach(() => {
  state.width = 1200; state.height = 480;
  vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockImplementation(function (this: HTMLElement) { return this.classList.contains('pdf-document-wrapper') ? state.width : 0; });
  vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockImplementation(function (this: HTMLElement) { return this.classList.contains('pdf-document-wrapper') ? state.height : 0; });
  vi.stubGlobal('ResizeObserver', class {
    constructor(callback: () => void) { state.resize = callback; }
    observe() {} disconnect() {}
  });
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); });

describe('PDF textbook reading', () => {
  it('fits the actual page ratio to remaining height and updates on resize', () => {
    render(<Reader />);
    expect(Number(screen.getByTestId('pdf-page').dataset.width)).toBeCloseTo(342);
    state.width = 400; state.height = 800;
    act(() => state.resize());
    expect(Number(screen.getByTestId('pdf-page').dataset.width)).toBeCloseTo(376);
  });

  it('recalculates fitting for a landscape page and bounds keyboard navigation', () => {
    render(<Reader />);
    fireEvent.keyDown(document.body, { key: 'PageDown' });
    expect(screen.getByTestId('pdf-page')).toHaveTextContent('Page 2');
    fireEvent.keyDown(document.body, { key: 'PageDown' });
    expect(screen.getByTestId('pdf-page')).toHaveTextContent('Page 3');
    expect(Number(screen.getByTestId('pdf-page').dataset.width)).toBeCloseTo(608);
    fireEvent.keyDown(document.body, { key: 'PageDown' });
    expect(screen.getByTestId('pdf-page')).toHaveTextContent('Page 3');
    fireEvent.keyDown(document.body, { key: 'PageUp' });
    expect(screen.getByTestId('pdf-page')).toHaveTextContent('Page 2');
  });

  it('does not intercept Chat inputs or keys outside the focused comparison viewer', () => {
    const { container } = render(<Reader keyboardScope="viewer" />);
    fireEvent.keyDown(screen.getByRole('textbox'), { key: 'PageDown' });
    fireEvent.keyDown(document.body, { key: 'PageDown' });
    expect(screen.getByTestId('pdf-page')).toHaveTextContent('Page 1');
    const viewport = container.querySelector('.pdf-document-wrapper')!;
    fireEvent.keyDown(viewport, { key: 'PageDown' });
    expect(screen.getByTestId('pdf-page')).toHaveTextContent('Page 2');
  });

  it('ignores editable controls and an open modal even in original view', () => {
    render(<Reader />);
    fireEvent.keyDown(screen.getByRole('textbox'), { key: 'PageDown' });
    const dialog = document.createElement('div');
    dialog.setAttribute('role', 'dialog');
    document.body.append(dialog);
    fireEvent.keyDown(document.body, { key: 'PageDown' });
    expect(screen.getByTestId('pdf-page')).toHaveTextContent('Page 1');
    dialog.remove();
  });

  it('turns just one page for a wheel gesture and uses Ctrl wheel for PDF zoom', () => {
    vi.useFakeTimers();
    const { container } = render(<Reader />);
    const viewport = container.querySelector('.pdf-document-wrapper')!;
    fireEvent.wheel(viewport, { deltaY: 100 });
    fireEvent.wheel(viewport, { deltaY: 100 });
    expect(screen.getByTestId('pdf-page')).toHaveTextContent('Page 2');
    act(() => vi.advanceTimersByTime(350));
    fireEvent.wheel(viewport, { deltaY: -100 });
    expect(screen.getByTestId('pdf-page')).toHaveTextContent('Page 1');
    act(() => vi.advanceTimersByTime(350));
    fireEvent.wheel(viewport, { deltaY: -100, ctrlKey: true });
    expect(screen.getByTestId('pdf-page')).toHaveAttribute('data-scale', '1.25');
    expect(screen.getByTestId('pdf-page')).toHaveTextContent('Page 1');
  });

  it('scrolls inside a zoomed page before turning at the bottom boundary', () => {
    const { container } = render(<Reader />);
    const viewport = container.querySelector('.pdf-document-wrapper') as HTMLElement;
    Object.defineProperty(viewport, 'scrollHeight', { configurable: true, value: 1000 });
    viewport.scrollTop = 100;
    fireEvent.wheel(viewport, { deltaY: 100 });
    expect(screen.getByTestId('pdf-page')).toHaveTextContent('Page 1');
    viewport.scrollTop = 520;
    fireEvent.wheel(viewport, { deltaY: 100 });
    expect(screen.getByTestId('pdf-page')).toHaveTextContent('Page 2');
    expect(viewport.scrollTop).toBe(0);
  });

  it('leaves non-textbook viewer navigation unchanged', () => {
    const { container } = render(<PdfViewer data={bytes} />);
    fireEvent.keyDown(document.body, { key: 'PageDown' });
    fireEvent.wheel(container.querySelector('.pdf-document-wrapper')!, { deltaY: 100 });
    expect(screen.getByTestId('pdf-page')).toHaveTextContent('Page 1');
  });
});
