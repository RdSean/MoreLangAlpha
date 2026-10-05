import React, { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import { ChevronLeft, ChevronRight, Minus, Plus } from 'lucide-react';
import { useTranslation } from 'react-i18next';
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
  fitWidth?: boolean;
}

export default function PdfViewer({ data, viewMode = 'single', pageNumber: controlledPageNumber, onPageChange, onNumPagesChange, fitWidth = false }: PdfViewerProps) {
  const { t } = useTranslation();
  const [numPages, setNumPages] = useState<number | null>(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [zoomIndex, setZoomIndex] = useState(DEFAULT_ZOOM_INDEX);
  const [error, setError] = useState<Error | null>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const [pageWidth, setPageWidth] = useState<number>();
  useEffect(() => {
    const viewport = viewportRef.current;
    if (!fitWidth || !viewport) return;
    const resize = () => {
      if (viewport.clientWidth > 24) setPageWidth(Math.min(612, viewport.clientWidth - 24));
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(viewport);
    return () => observer.disconnect();
  }, [fitWidth]);

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
          <button onClick={goToPrev} disabled={viewMode !== 'single' || currentPage <= 1} className="pdf-btn" aria-label={t('documents.preview.previousPage')} title={t('documents.preview.previousPage')}>
            <ChevronLeft size={14} aria-hidden="true" />
          </button>
          <span className="pdf-page-info">
            {currentPage} / {numPages ?? '...'}
          </span>
          <button onClick={goToNext} disabled={viewMode !== 'single' || currentPage >= (numPages || 1)} className="pdf-btn" aria-label={t('documents.preview.nextPage')} title={t('documents.preview.nextPage')}>
            <ChevronRight size={14} aria-hidden="true" />
          </button>
        </div>
        <div className="pdf-zoom">
          <button onClick={zoomOut} disabled={zoomIndex <= 0} className="pdf-btn" aria-label={t('documents.preview.zoomOut')} title={t('documents.preview.zoomOut')}>
            <Minus size={14} aria-hidden="true" />
          </button>
          <span className="pdf-zoom-info">{Math.round(scale * 100)}%</span>
          <button onClick={zoomIn} disabled={zoomIndex >= ZOOM_STEPS.length - 1} className="pdf-btn" aria-label={t('documents.preview.zoomIn')} title={t('documents.preview.zoomIn')}>
            <Plus size={14} aria-hidden="true" />
          </button>
        </div>
      </div>

      {/* Document */}
      <div ref={viewportRef} className={`pdf-document-wrapper${fitWidth ? ' fit-width' : ''}`}>
        <Document
          file={fileData}
          onLoadSuccess={onDocumentLoadSuccess}
          onLoadError={(err: Error) => setError(err)}
          loading={
              <div className="pdf-loading">{t('common.loading')}</div>
          }
        >
          {viewMode === 'continuous' && numPages
            ? Array.from({ length: numPages }, (_, index) => (
              <Page key={index + 1} pageNumber={index + 1} width={fitWidth ? pageWidth : undefined} scale={scale} loading={<div className="pdf-loading">{t('common.loading')}</div>} />
            ))
            : <Page pageNumber={currentPage} width={fitWidth ? pageWidth : undefined} scale={scale} loading={<div className="pdf-loading">{t('common.loading')}</div>} />}
        </Document>
      </div>
    </div>
  );
}
