import '@/lib/pdfCompatibility';
import React, { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import { ChevronLeft, ChevronRight, Minus, Plus } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Document, Page, pdfjs } from 'react-pdf';
// Load after PDF.js: its ArrayBuffer transfer shim must detect the native
// structuredClone capability, otherwise the two transfer polyfills recurse.
import 'core-js/actual/structured-clone';
import type { PDFPageProxy } from 'pdfjs-dist';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';
import './PdfViewer.css';

// Bundle the worker too: ?url alone serves unsupported syntax unchanged.
import pdfjsWorkerUrl from '@/pdfjsWorker.ts?worker&url';
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
  fitPage?: boolean;
  pageNavigation?: boolean;
  keyboardScope?: 'document' | 'viewer';
}

export default function PdfViewer({ data, viewMode = 'single', pageNumber: controlledPageNumber, onPageChange, onNumPagesChange, fitWidth = false, fitPage = false, pageNavigation = false, keyboardScope = 'document' }: PdfViewerProps) {
  const { t } = useTranslation();
  const [numPages, setNumPages] = useState<number | null>(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [zoomIndex, setZoomIndex] = useState(DEFAULT_ZOOM_INDEX);
  const [error, setError] = useState<Error | null>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<HTMLDivElement>(null);
  const gestureRef = useRef({ time: -Infinity, delta: 0, locked: false, zoom: false });
  const [pageWidth, setPageWidth] = useState<number>();
  const [viewportSize, setViewportSize] = useState({ width: 0, height: 0 });
  const [pageSize, setPageSize] = useState({ width: 612, height: 792 });
  useEffect(() => {
    const viewport = viewportRef.current;
    if ((!fitWidth && !fitPage) || !viewport) return;
    const resize = () => {
      if (viewport.clientWidth > 24) setPageWidth(Math.min(612, viewport.clientWidth - 24));
      setViewportSize({ width: viewport.clientWidth, height: viewport.clientHeight });
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(viewport);
    return () => observer.disconnect();
  }, [fitWidth, fitPage]);

  const scale = ZOOM_STEPS[zoomIndex];
  const fittedWidth = viewportSize.width > 24 && viewportSize.height > 24
    ? Math.min(viewportSize.width - 24, (viewportSize.height - 24) * pageSize.width / pageSize.height)
    : undefined;
  const renderWidth = fitPage ? fittedWidth : fitWidth ? pageWidth : undefined;
  const onPageLoadSuccess = useCallback((page: PDFPageProxy) => {
    const { width, height } = page.getViewport({ scale: 1 });
    setPageSize((previous) => previous.width === width && previous.height === height ? previous : { width, height });
  }, []);

  const onDocumentLoadSuccess = useCallback(({ numPages: n }: { numPages: number }) => {
    setNumPages(n);
    setPageNumber(1);
    onNumPagesChange?.(n);
  }, [onNumPagesChange]);

  const currentPage = controlledPageNumber ?? pageNumber;
  const changePage = useCallback((nextPage: number) => {
    const boundedPage = Math.max(1, Math.min(numPages || nextPage, nextPage));
    if (boundedPage === currentPage) return;
    setPageNumber(boundedPage);
    onPageChange?.(boundedPage);
    if (viewportRef.current) viewportRef.current.scrollTop = 0;
  }, [numPages, currentPage, onPageChange]);
  const goToPrev = () => changePage(currentPage - 1);
  const goToNext = () => changePage(currentPage + 1);
  const zoomIn = () => setZoomIndex((i) => Math.min(ZOOM_STEPS.length - 1, i + 1));
  const zoomOut = () => setZoomIndex((i) => Math.max(0, i - 1));

  useEffect(() => {
    const viewport = viewportRef.current;
    const viewer = viewerRef.current;
    if (!pageNavigation || viewMode !== 'single' || !viewport || !viewer) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey || !numPages) return;
      if (event.key !== 'PageUp' && event.key !== 'PageDown') return;
      const target = event.target;
      if (target instanceof Element && target.closest('input, textarea, select, [contenteditable]:not([contenteditable="false"]), [role="textbox"], [role="dialog"]')) return;
      if (document.querySelector('[role="dialog"], [role="alertdialog"]')) return;
      if (keyboardScope === 'viewer' && (!(target instanceof Node) || !viewer.contains(target))) return;
      event.preventDefault();
      changePage(currentPage + (event.key === 'PageDown' ? 1 : -1));
    };
    const onWheel = (event: WheelEvent) => {
      if (!numPages || !event.deltaY || Math.abs(event.deltaX) > Math.abs(event.deltaY)) return;
      const now = Date.now();
      const gesture = gestureRef.current;
      if (now - gesture.time > 180 || gesture.zoom !== event.ctrlKey) {
        gesture.delta = 0;
        gesture.locked = false;
      }
      gesture.time = now;
      gesture.zoom = event.ctrlKey;
      const delta = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? viewport.clientHeight : 1);
      if (!event.ctrlKey) {
        const canScroll = delta > 0
          ? viewport.scrollTop + viewport.clientHeight < viewport.scrollHeight - 1
          : viewport.scrollTop > 1;
        if (canScroll && !gesture.locked) { gesture.delta = 0; return; }
      }
      event.preventDefault();
      if (gesture.locked) return;
      gesture.delta += delta;
      if (Math.abs(gesture.delta) < (event.ctrlKey ? 8 : 60)) return;
      gesture.locked = true;
      if (event.ctrlKey) {
        const direction = gesture.delta < 0 ? 1 : -1;
        setZoomIndex((index) => Math.max(0, Math.min(ZOOM_STEPS.length - 1, index + direction)));
      } else {
        changePage(currentPage + (gesture.delta > 0 ? 1 : -1));
      }
    };
    document.addEventListener('keydown', onKeyDown);
    // A passive wheel listener cannot stop browser zoom or page scroll.
    viewport.addEventListener('wheel', onWheel, { passive: false });
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      viewport.removeEventListener('wheel', onWheel);
    };
  }, [pageNavigation, viewMode, keyboardScope, numPages, currentPage, changePage]);

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
    <div ref={viewerRef} className="pdf-viewer">
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
      <div ref={viewportRef} tabIndex={pageNavigation ? 0 : undefined} role={pageNavigation ? 'region' : undefined} aria-label={pageNavigation ? 'PDF' : undefined} className={`pdf-document-wrapper${fitWidth || fitPage ? ' fit-width' : ''}`}>
        <Document
          file={fileData}
          onLoadSuccess={onDocumentLoadSuccess}
          onSourceError={(err: Error) => setError(err)}
          onLoadError={(err: Error) => setError(err)}
          loading={
              <div className="pdf-loading">{t('common.loading')}</div>
          }
        >
          {numPages && (viewMode === 'continuous'
            ? Array.from({ length: numPages }, (_, index) => (
              <Page key={index + 1} pageNumber={index + 1} width={renderWidth} scale={scale} onLoadError={(err: Error) => setError(err)} onRenderError={(err: Error) => setError(err)} loading={<div className="pdf-loading">{t('common.loading')}</div>} />
            ))
            : <Page pageNumber={currentPage > numPages ? 1 : currentPage} width={renderWidth} scale={scale} onLoadSuccess={fitPage ? onPageLoadSuccess : undefined} onLoadError={(err: Error) => setError(err)} onRenderError={(err: Error) => setError(err)} loading={<div className="pdf-loading">{t('common.loading')}</div>} />)}
        </Document>
      </div>
    </div>
  );
}
