import { useEffect, type ReactNode } from 'react';
import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import DocumentErrorBoundary from '../DocumentErrorBoundary';
import PdfViewer from '../PdfViewer';

type Failure = 'source' | 'document' | 'page' | 'render';
const state = vi.hoisted(() => ({ failure: 'source' as Failure }));
type ErrorProps = { onLoadError?: (error: Error) => void; onSourceError?: (error: Error) => void; onRenderError?: (error: Error) => void };
vi.mock('react-pdf', () => ({
  pdfjs: { GlobalWorkerOptions: {} },
  Document: ({ children, onSourceError, onLoadError, onLoadSuccess }: ErrorProps & { children: ReactNode; onLoadSuccess: (document: { numPages: number }) => void }) => {
    useEffect(() => {
      if (state.failure === 'source') onSourceError?.(new Error('Source failed'));
      if (state.failure === 'document') onLoadError?.(new Error('Document failed'));
      if (state.failure === 'page' || state.failure === 'render') onLoadSuccess({ numPages: 3 });
    }, [onSourceError, onLoadError, onLoadSuccess]);
    return <div>{children}</div>;
  },
  Page: ({ onLoadError, onRenderError }: ErrorProps) => {
    useEffect(() => {
      if (state.failure === 'page') onLoadError?.(new Error('Page failed'));
      if (state.failure === 'render') onRenderError?.(new Error('Canvas failed'));
    }, [onLoadError, onRenderError]);
    return <div>Loading page</div>;
  },
}));
vi.mock('@/pdfjsWorker.ts?worker&url', () => ({ default: 'worker.js' }));
afterEach(() => vi.restoreAllMocks());

describe('PDF failure feedback', () => {
  for (const failure of ['source', 'document', 'page', 'render'] as const) {
    it(`replaces loading with the enclosing retry state when ${failure} fails`, async () => {
      state.failure = failure;
      vi.spyOn(console, 'error').mockImplementation(() => {});
      render(<DocumentErrorBoundary fallback={<div role="alert">Retry original</div>}>
        <PdfViewer data={new Uint8Array([1, 2, 3])} />
      </DocumentErrorBoundary>);
      expect(await screen.findByRole('alert')).toHaveTextContent('Retry original');
      expect(screen.queryByText('Loading page')).not.toBeInTheDocument();
    });
  }
});
