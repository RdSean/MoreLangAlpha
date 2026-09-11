import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';
import React from 'react';

/**
 * pdf.js takes ownership of the bytes it is given.
 *
 * `pdf.mjs` posts the document to its worker as a transferable —
 * `sendWithPromise("GetDocRequest", params, [data.buffer])` — which detaches the
 * ArrayBuffer on this side. Callers hold a buffer of their own across mounts
 * (the documents drawer keeps one and remounts this viewer every time the user
 * switches back to the original file), so the viewer has to hand pdf.js a copy.
 *
 * The fake Document below performs the same transfer for real, so the assertion
 * is about the detach itself rather than about a stubbed call shape.
 */

const seen: Array<{ byteLength: number; first: number }> = [];

vi.mock('react-pdf', () => ({
  pdfjs: { GlobalWorkerOptions: {} },
  Document: ({ file }: { file: { data: Uint8Array } | null }) => {
    if (file?.data) {
      seen.push({ byteLength: file.data.byteLength, first: file.data[0] });
      // Exactly what the worker hop does: transferring detaches the source.
      structuredClone(file.data.buffer, { transfer: [file.data.buffer] });
    }
    return <div data-testid="pdf-document" />;
  },
  Page: () => <div data-testid="pdf-page" />,
}));

vi.mock('pdfjs-dist/build/pdf.worker.min.mjs?url', () => ({ default: 'worker.js' }));

import PdfViewer from '../PdfViewer';

describe('PdfViewer buffer ownership', () => {
  beforeEach(() => {
    seen.length = 0;
  });

  it('leaves the caller’s buffer intact and still usable on a remount', () => {
    const buffer = new Uint8Array([7, 8, 9]).buffer;

    const first = render(<PdfViewer data={buffer} />);
    // The viewer handed pdf.js a copy, so the caller's bytes are untouched.
    expect(buffer.byteLength).toBe(3);
    first.unmount();

    // A tab switch back to the original file remounts with that same buffer.
    render(<PdfViewer data={buffer} />);

    expect(seen).toHaveLength(2);
    expect(seen[1]).toEqual({ byteLength: 3, first: 7 });
  });

  it('accepts a typed array without detaching it', () => {
    const bytes = new Uint8Array([1, 2, 3, 4]);

    render(<PdfViewer data={bytes} />);

    expect(bytes.byteLength).toBe(4);
    expect(seen[0]).toEqual({ byteLength: 4, first: 1 });
  });
});
