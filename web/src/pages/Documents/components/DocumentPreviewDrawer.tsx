import { Suspense, lazy, useEffect, useMemo, useRef, useState } from 'react';
import type { MouseEvent as ReactMouseEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronLeft, ChevronRight, FileText, Loader2, Maximize2, Minimize2, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import Markdown from '@/pages/ChatAgent/components/Markdown';
import { fetchArtifactText, documentSourceUrl } from '../api';
import { useDocument, useDocumentArtifacts, useDocumentJobs } from '../hooks';
import type { Artifact } from '../types';
import './DocumentPreviewDrawer.css';
import '../../ChatAgent/components/FilePanel.css';

const PreviewViewer = lazy(() => import('@/pages/ChatAgent/components/viewers/PreviewViewer'));
type PreviewTab = 'source' | 'parsed';
type SourceViewMode = 'continuous' | 'single';

interface DocumentPreviewDrawerProps {
  open: boolean;
  documentId?: string;
  onOpenChange: (open: boolean) => void;
  onOpenParser?: (documentId: string) => void;
}

export default function DocumentPreviewDrawer({
  open,
  documentId,
  onOpenChange,
  onOpenParser,
}: DocumentPreviewDrawerProps) {
  const { t } = useTranslation();
  const documentRecord = useDocument(documentId);
  const jobs = useDocumentJobs(documentId);
  const artifacts = useDocumentArtifacts(documentId);
  const [tab, setTab] = useState<PreviewTab>('source');
  const [source, setSource] = useState<ArrayBuffer>();
  const [sourceLoading, setSourceLoading] = useState(false);
  const [sourceError, setSourceError] = useState(false);
  const [markdown, setMarkdown] = useState<string>();
  const [markdownLoading, setMarkdownLoading] = useState(false);
  const [markdownError, setMarkdownError] = useState(false);
  const [sourceUrl, setSourceUrl] = useState<string>();
  const [sourceViewMode, setSourceViewMode] = useState<SourceViewMode>('continuous');
  const [sourcePage, setSourcePage] = useState(1);
  const [sourcePageCount, setSourcePageCount] = useState<number>();
  const [panelWidth, setPanelWidth] = useState<number>();
  const [isDragging, setIsDragging] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const drawerRef = useRef<HTMLElement>(null);

  const latestCompletedJobId = useMemo(
    () => (jobs.data ?? []).find((job) => job.status === 'completed')?.job_id,
    [jobs.data],
  );
  const markdownArtifact = useMemo<Artifact | undefined>(() => {
    return (artifacts.data ?? []).find((artifact) => (
      artifact.producer_job_id === latestCompletedJobId
      && artifact.artifact_kind === 'primary_document'
      && (artifact.format === 'markdown' || artifact.media_type === 'text/markdown')
    ));
  }, [artifacts.data, latestCompletedJobId]);

  useEffect(() => {
    if (!open || !documentId) return;
    setTab('source');
    setSource(undefined);
    setSourceUrl(undefined);
    setSourceError(false);
    setSourceLoading(true);
    setSourceViewMode('continuous');
    setSourcePage(1);
    setSourcePageCount(undefined);
    let cancelled = false;
    fetch(documentSourceUrl(documentId), { credentials: 'include' })
      .then(async (response) => {
        if (!response.ok) throw new Error('source unavailable');
        return response.arrayBuffer();
      })
      .then((value) => {
        if (!cancelled) {
          setSource(value);
          setSourceUrl(documentSourceUrl(documentId));
        }
      })
      .catch(() => { if (!cancelled) setSourceError(true); })
      .finally(() => { if (!cancelled) setSourceLoading(false); });
    return () => { cancelled = true; };
  }, [documentId, open]);

  useEffect(() => {
    if (!open || tab !== 'parsed' || !markdownArtifact) return;
    setMarkdown(undefined);
    setMarkdownError(false);
    setMarkdownLoading(true);
    let cancelled = false;
    fetchArtifactText(markdownArtifact.artifact_id)
      .then((value) => { if (!cancelled) setMarkdown(value); })
      .catch(() => { if (!cancelled) setMarkdownError(true); })
      .finally(() => { if (!cancelled) setMarkdownLoading(false); });
    return () => { cancelled = true; };
  }, [markdownArtifact, open, tab]);

  useEffect(() => {
    if (!isDragging) return;
    const onMouseMove = (event: MouseEvent) => {
      const maxWidth = Math.min(window.innerWidth - 24, 1100);
      const minWidth = Math.min(420, window.innerWidth - 24);
      setPanelWidth(Math.max(minWidth, Math.min(maxWidth, window.innerWidth - event.clientX)));
    };
    const onMouseUp = () => setIsDragging(false);
    document.body.style.userSelect = 'none';
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
    return () => {
      document.body.style.userSelect = '';
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };
  }, [isDragging]);

  useEffect(() => {
    const onFullscreenChange = () => setIsFullscreen(document.fullscreenElement === drawerRef.current);
    document.addEventListener('fullscreenchange', onFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', onFullscreenChange);
  }, []);

  const handleDividerMouseDown = (event: ReactMouseEvent<HTMLDivElement>) => {
    event.preventDefault();
    const width = drawerRef.current?.getBoundingClientRect().width ?? panelWidth ?? 760;
    setPanelWidth(width);
    setIsDragging(true);
  };

  const toggleFullscreen = async () => {
    if (document.fullscreenElement === drawerRef.current) {
      await document.exitFullscreen?.();
      return;
    }
    try {
      if (!drawerRef.current?.requestFullscreen) {
        setIsFullscreen(true);
        return;
      }
      await drawerRef.current.requestFullscreen();
    } catch {
      setIsFullscreen(true);
    }
  };

  const filename = documentRecord.data?.original_filename ?? t('documents.preview.titleFallback');
  const isPdfSource = documentRecord.data?.media_type?.includes('pdf') || filename.toLowerCase().endsWith('.pdf');

  const sourcePreviewUrl = sourceUrl && sourceViewMode === 'single'
    ? `${sourceUrl}#page=${sourcePage}`
    : sourceUrl;

  return (
    <div aria-hidden={!open}>
      <div className={`documents-preview-overlay${open ? ' is-open' : ''}`} onClick={() => onOpenChange(false)} />
      <aside
        ref={drawerRef}
        className={`documents-preview-drawer${open ? ' is-open' : ''}${isFullscreen ? ' is-fullscreen' : ''}`}
        style={panelWidth ? { width: `${panelWidth}px` } : undefined}
        aria-label={t('documents.preview.title')}
      >
        <div
          className={`chat-split-divider documents-preview-divider${isDragging ? ' dragging' : ''}`}
          onMouseDown={handleDividerMouseDown}
          role="separator"
          aria-orientation="vertical"
          aria-label={t('documents.preview.resize')}
        />
        <header className="documents-preview-header">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <FileText className="h-4 w-4 shrink-0" aria-hidden="true" />
              <h2 className="truncate">{filename}</h2>
              {documentRecord.data?.parse_status && <Badge variant="muted">{t(`documents.status.${documentRecord.data.parse_status}`)}</Badge>}
            </div>
          </div>
          <div className="documents-preview-header-actions">
            <button type="button" className="file-panel-icon-btn" onClick={() => void toggleFullscreen()} aria-label={isFullscreen ? t('documents.preview.exitFullscreen') : t('documents.preview.fullscreen')} title={isFullscreen ? t('documents.preview.exitFullscreen') : t('documents.preview.fullscreen')}>
              {isFullscreen ? <Minimize2 className="h-4 w-4" aria-hidden="true" /> : <Maximize2 className="h-4 w-4" aria-hidden="true" />}
            </button>
            <button type="button" className="file-panel-icon-btn" onClick={() => onOpenChange(false)} aria-label={t('documents.preview.close')}>
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
        </header>
        <div className="documents-preview-tabs documents-preview-segmented" role="tablist" aria-label={t('documents.preview.tabsLabel')}>
          <button type="button" role="tab" aria-selected={tab === 'source'} onClick={() => setTab('source')}>
            {t('documents.preview.sourceTab')}
          </button>
          <button type="button" role="tab" aria-selected={tab === 'parsed'} onClick={() => setTab('parsed')}>
            {t('documents.preview.parsedTab')}
          </button>
        </div>
        <div className="documents-preview-body">
          <div className="documents-preview-content file-panel-content">
          {tab === 'source' && (
            sourceLoading ? <PreviewLoading />
              : sourceError ? <PreviewEmpty message={t('documents.preview.sourceError')} />
                : source && sourcePreviewUrl ? (
                  <div className="documents-preview-source">
                    <div className="documents-preview-source-controls file-panel-item">
                      <div className="documents-preview-mode-switch" role="tablist" aria-label={t('documents.preview.viewModeLabel')}>
                        <button type="button" role="tab" aria-selected={sourceViewMode === 'continuous'} onClick={() => setSourceViewMode('continuous')}>
                          {t('documents.preview.continuousMode')}
                        </button>
                        <button type="button" role="tab" aria-selected={sourceViewMode === 'single'} onClick={() => setSourceViewMode('single')}>
                          {t('documents.preview.singlePageMode')}
                        </button>
                      </div>
                      <div className="documents-preview-page-controls" aria-label={t('documents.preview.pageControls')}>
                        <button type="button" className="file-panel-icon-btn" disabled={sourceViewMode !== 'single' || sourcePage <= 1} onClick={() => setSourcePage((page) => Math.max(1, page - 1))} aria-label={t('documents.preview.previousPage')} title={t('documents.preview.previousPage')}>
                          <ChevronLeft className="h-4 w-4" aria-hidden="true" />
                        </button>
                        <span className="documents-preview-page-number">{sourceViewMode === 'single' ? sourcePage : '∞'}</span>
                        <button type="button" className="file-panel-icon-btn" disabled={sourceViewMode !== 'single' || (sourcePageCount !== undefined && sourcePage >= sourcePageCount)} onClick={() => setSourcePage((page) => Math.min(sourcePageCount ?? page + 1, page + 1))} aria-label={t('documents.preview.nextPage')} title={t('documents.preview.nextPage')}>
                          <ChevronRight className="h-4 w-4" aria-hidden="true" />
                        </button>
                      </div>
                    </div>
                    <div className="documents-preview-source-viewer">
                      <Suspense fallback={<PreviewLoading />}>
                        <PreviewViewer
                          url={sourcePreviewUrl}
                          port={0}
                          title={filename}
                          loading={false}
                          error={false}
                          onClose={() => onOpenChange(false)}
                          isDragging={isDragging}
                          reloadToken={sourcePage}
                          documentData={isPdfSource ? source : undefined}
                          documentViewMode={sourceViewMode}
                          documentPage={sourcePage}
                          onDocumentPageChange={setSourcePage}
                          onDocumentPageCount={setSourcePageCount}
                          sandbox={isPdfSource ? null : undefined}
                        />
                      </Suspense>
                    </div>
                  </div>
                )
                  : <PreviewLoading />
          )}
          {tab === 'parsed' && (
            markdownLoading ? <PreviewLoading />
              : markdownError ? <PreviewEmpty message={t('documents.preview.parsedError')} />
                : markdown !== undefined ? <div className="documents-preview-markdown"><Markdown variant="panel" content={markdown} /></div>
                  : <PreviewEmpty message={t('documents.preview.noParsed')} action={onOpenParser && documentId ? { label: t('documents.preview.openParser'), onClick: () => onOpenParser(documentId) } : undefined} />
          )}
          </div>
        </div>
      </aside>
    </div>
  );
}

function PreviewLoading() {
  return <div className="documents-preview-state"><Loader2 className="h-5 w-5 animate-spin" aria-label="Loading" /></div>;
}

function PreviewEmpty({ message, action }: { message: string; action?: { label: string; onClick: () => void } }) {
  return <div className="documents-preview-state"><img src="/empty-state-for-file.svg" alt="" /><p>{message}</p>{action && <Button type="button" variant="outline" onClick={action.onClick}>{action.label}</Button>}</div>;
}
