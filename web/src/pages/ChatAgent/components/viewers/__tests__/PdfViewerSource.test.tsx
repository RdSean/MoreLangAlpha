import { render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import PdfViewer from '../PdfViewer';

const state = vi.hoisted(() => ({ files: [] as unknown[] }));
vi.mock('react-pdf', () => ({
  pdfjs: { GlobalWorkerOptions: {} },
  Document: ({ file }: { file: unknown }) => { state.files.push(file); return <div>PDF</div>; },
  Page: () => <div>Page</div>,
}));
vi.mock('@/pdfjsWorker.ts?worker&url', () => ({ default: 'worker.js' }));

describe('PDF authenticated URL source', () => {
  beforeEach(() => { state.files.length = 0; });
  it('lets PDF.js load the URL with cookies and preserves the source across rerenders', () => {
    const source = { url: '/api/v1/education/textbooks/book/original', withCredentials: true as const };
    const view = render(<PdfViewer source={source} />);
    expect(state.files[0]).toEqual(source);
    view.rerender(<PdfViewer source={{ ...source }} pageNumber={2} />);
    expect(state.files.at(-1)).toBe(state.files[0]);
  });
});
