import { Suspense, lazy, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronLeft, ChevronRight, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import Markdown from '@/pages/ChatAgent/components/Markdown';
import DocumentErrorBoundary from '@/pages/ChatAgent/components/viewers/DocumentErrorBoundary';
import { documentSourceUrl, fetchArtifactText } from '../api';
import { resolveRelativeImageSources } from '../artifactImages';
import { useDocumentArtifacts, useDocumentJobs } from '../hooks';
import type { Artifact, DocumentSummary } from '../types';
import './DocumentPreviewDrawer.css';
import '../../ChatAgent/components/FilePanel.css';

const PreviewViewer = lazy(() => import('@/pages/ChatAgent/components/viewers/PreviewViewer'));

export type DocumentContentTab = 'source' | 'parsed';
type SourceViewMode = 'continuous' | 'single';

interface DocumentContentPaneProps {
  documentId: string;
  document?: DocumentSummary;
  activeTab: DocumentContentTab;
  isDragging: boolean;
  onOpenParser?: (documentId: string) => void;
  onClose?: () => void;
}

export default function DocumentContentPane({
  documentId,
  document,
  activeTab,
  isDragging,
  onOpenParser,
  onClose,
}: DocumentContentPaneProps) {
  const { t } = useTranslation();
  const jobs = useDocumentJobs(documentId);
  const artifacts = useDocumentArtifacts(documentId);
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

  const renderedMarkdown = useMemo(
    () =>
      markdown === undefined
        ? markdown
        : resolveRelativeImageSources(markdown, artifacts.data, window.location.origin),
    [markdown, artifacts.data],
  );

  useEffect(() => {
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
  }, [documentId]);

  useEffect(() => {
    setMarkdown(undefined);
    setMarkdownError(false);
    setMarkdownLoading(false);
    if (activeTab !== 'parsed' || !markdownArtifact) return;
    setMarkdownLoading(true);
    let cancelled = false;
    fetchArtifactText(markdownArtifact.artifact_id)
      .then((value) => { if (!cancelled) setMarkdown(value); })
      .catch(() => { if (!cancelled) setMarkdownError(true); })
      .finally(() => { if (!cancelled) setMarkdownLoading(false); });
    return () => { cancelled = true; };
  }, [activeTab, markdownArtifact]);

  const filename = document?.original_filename ?? t('documents.preview.titleFallback');
  const isPdfSource = document?.media_type?.includes('pdf') || filename.toLowerCase().endsWith('.pdf');
  const sourcePreviewUrl = sourceUrl && sourceViewMode === 'single'
    ? `${sourceUrl}#page=${sourcePage}`
    : sourceUrl;

  if (activeTab === 'source') {
    if (sourceLoading) return <PreviewLoading />;
    if (sourceError) return <PreviewEmpty message={t('documents.preview.sourceError')} />;
    if (!source || !sourcePreviewUrl) return <PreviewLoading />;
    return (
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
          <DocumentErrorBoundary fallback={<PreviewEmpty message={t('documents.preview.sourceError')} />}>
            <Suspense fallback={<PreviewLoading />}>
              <PreviewViewer
                url={sourcePreviewUrl}
                port={0}
                title={filename}
                loading={false}
                error={false}
                onClose={onClose ?? (() => undefined)}
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
          </DocumentErrorBoundary>
        </div>
      </div>
    );
  }

  if (markdownLoading) return <PreviewLoading />;
  if (markdownError) return <PreviewEmpty message={t('documents.preview.parsedError')} />;
  if (renderedMarkdown !== undefined) {
    return <div className="documents-preview-markdown"><Markdown variant="panel" content={renderedMarkdown} /></div>;
  }
  return (
    <PreviewEmpty
      message={t('documents.preview.noParsed')}
      action={onOpenParser ? { label: t('documents.preview.openParser'), onClick: () => onOpenParser(documentId) } : undefined}
    />
  );
}

function PreviewLoading() {
  return <div className="documents-preview-state"><Loader2 className="h-5 w-5 animate-spin" aria-label="Loading" /></div>;
}

function PreviewEmpty({ message, action }: { message: string; action?: { label: string; onClick: () => void } }) {
  return <div className="documents-preview-state"><img src="/empty-state-for-file.svg" alt="" /><p>{message}</p>{action && <Button type="button" variant="outline" onClick={action.onClick}>{action.label}</Button>}</div>;
}
