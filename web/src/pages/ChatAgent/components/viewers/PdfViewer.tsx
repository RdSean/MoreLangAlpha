import React, { useState, useCallback, useMemo } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';
import './PdfViewer.css';

// Vite-native ?url import resolves correctly in both dev and build
import pdfjsWorkerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
pdfjs.GlobalWorkerOptions.workerSrc = pdfjsWorkerUrl;

const ZOOM_STEPS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0];
const DEFAULT_ZOOM_INDEX = 2; // 1.0

interface PdfViewerProps {
  data: ArrayBuffer | Uint8Array;
  viewMode?: 'continuous' | 'single';
  pageNumber?: number;
  onPageChange?: (page: number) => void;
  onNumPagesChange?: (pages: number) => void;
}

export default function PdfViewer({ data, viewMode = 'single', pageNumber: controlledPageNumber, onPageChange, onNumPagesChange }: PdfViewerProps) {
  const [numPages, setNumPages] = useState<number | null>(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [zoomIndex, setZoomIndex] = useState(DEFAULT_ZOOM_INDEX);
  const [error, setError] = useState<Error | null>(null);

  const scale = ZOOM_STEPS[zoomIndex];

  const onDocumentLoadSuccess = useCallback(({ numPages: n }: { numPages: number }) => {
    setNumPages(n);
    setPageNumber(1);
    onNumPagesChange?.(n);
  }, [onNumPagesChange]);

  const currentPage = controlledPageNumber ?? pageNumber;
  const changePage = (nextPage: number) => {
    const boundedPage = Math.max(1, Math.min(numPages || nextPage, nextPage));
    setPageNumber(boundedPage);
    onPageChange?.(boundedPage);
  };
  const goToPrev = () => changePage(currentPage - 1);
  const goToNext = () => changePage(currentPage + 1);
  const zoomIn = () => setZoomIndex((i) => Math.min(ZOOM_STEPS.length - 1, i + 1));
  const zoomOut = () => setZoomIndex((i) => Math.max(0, i - 1));

  // pdf.js posts the bytes to its worker as a transferable — `sendWithPromise(
  // "GetDocRequest", params, [data.buffer])` in pdf.mjs — which DETACHES the
  // buffer it was handed. Callers keep their own copy for as long as the viewer
  // is on screen (the documents drawer refetches only when the document or the
  // drawer changes, so switching tabs back to the original file remounts this
  // component with the same buffer), so pdf.js gets a COPY and theirs survives.
  // A view — `new Uint8Array(data)` — would be detached along with it, and the
  // next mount would fail to load a zero-byte buffer.
  const fileData = useMemo(() => {
    if (!data) return null;
    // Both branches copy: ArrayBuffer.prototype.slice makes a new buffer, and
    // the Uint8Array constructor copies when handed another typed array.
    const bytes = data instanceof ArrayBuffer ? new Uint8Array(data.slice(0)) : new Uint8Array(data);
    return { data: bytes };
  }, [data]);

  // Bubble errors to the error boundary via render-phase throw
  if (error) throw error;

  return (
    <div className="pdf-viewer">
      {/* Controls */}
      <div className="pdf-controls">
        <div className="pdf-nav">
          <button onClick={goToPrev} disabled={viewMode !== 'single' || currentPage <= 1} className="pdf-btn">
            Prev
          </button>
          <span className="pdf-page-info">
            {currentPage} / {numPages ?? '...'}
          </span>
          <button onClick={goToNext} disabled={viewMode !== 'single' || currentPage >= (numPages || 1)} className="pdf-btn">
            Next
          </button>
        </div>
        <div className="pdf-zoom">
          <button onClick={zoomOut} disabled={zoomIndex <= 0} className="pdf-btn">
            −
          </button>
          <span className="pdf-zoom-info">{Math.round(scale * 100)}%</span>
          <button onClick={zoomIn} disabled={zoomIndex >= ZOOM_STEPS.length - 1} className="pdf-btn">
            +
          </button>
        </div>
      </div>

      {/* Document */}
      <div className="pdf-document-wrapper">
        <Document
          file={fileData}
          onLoadSuccess={onDocumentLoadSuccess}
          onLoadError={(err: Error) => setError(err)}
          loading={
            <div className="pdf-loading">Loading PDF...</div>
          }
        >
          {viewMode === 'continuous' && numPages
            ? Array.from({ length: numPages }, (_, index) => (
              <Page key={index + 1} pageNumber={index + 1} scale={scale} loading={<div className="pdf-loading">Rendering page...</div>} />
            ))
            : <Page pageNumber={currentPage} scale={scale} loading={<div className="pdf-loading">Rendering page...</div>} />}
        </Document>
      </div>
    </div>
  );
}
