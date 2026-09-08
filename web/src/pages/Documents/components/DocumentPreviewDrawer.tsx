import { Suspense, lazy, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { FileText, Loader2, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import Markdown from '@/pages/ChatAgent/components/Markdown';
import { fetchArtifactText, documentSourceUrl } from '../api';
import { useDocument, useDocumentArtifacts, useDocumentJobs } from '../hooks';
import type { Artifact } from '../types';
import './DocumentPreviewDrawer.css';

const PdfViewer = lazy(() => import('@/pages/ChatAgent/components/viewers/PdfViewer'));
type PreviewTab = 'source' | 'parsed';

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
  const document = useDocument(documentId);
  const jobs = useDocumentJobs(documentId);
  const artifacts = useDocumentArtifacts(documentId);
  const [tab, setTab] = useState<PreviewTab>('source');
  const [source, setSource] = useState<ArrayBuffer>();
  const [sourceLoading, setSourceLoading] = useState(false);
  const [sourceError, setSourceError] = useState(false);
  const [markdown, setMarkdown] = useState<string>();
  const [markdownLoading, setMarkdownLoading] = useState(false);
  const [markdownError, setMarkdownError] = useState(false);

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
    setSourceError(false);
    setSourceLoading(true);
    let cancelled = false;
    fetch(documentSourceUrl(documentId), { credentials: 'include' })
      .then(async (response) => {
        if (!response.ok) throw new Error('source unavailable');
        return response.arrayBuffer();
      })
      .then((value) => { if (!cancelled) setSource(value); })
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

  const filename = document.data?.original_filename ?? t('documents.preview.titleFallback');

  return (
    <div aria-hidden={!open}>
      <div className={`documents-preview-overlay${open ? ' is-open' : ''}`} onClick={() => onOpenChange(false)} />
      <aside className={`documents-preview-drawer${open ? ' is-open' : ''}`} aria-label={t('documents.preview.title')}>
        <header className="documents-preview-header">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <FileText className="h-4 w-4 shrink-0" aria-hidden="true" />
              <h2 className="truncate">{filename}</h2>
            </div>
            {document.data?.parse_status && <Badge variant="muted">{t(`documents.status.${document.data.parse_status}`)}</Badge>}
          </div>
          <Button type="button" variant="ghost" size="icon" onClick={() => onOpenChange(false)} aria-label={t('documents.preview.close')}>
            <X className="h-4 w-4" aria-hidden="true" />
          </Button>
        </header>
        <div className="documents-preview-tabs" role="tablist" aria-label={t('documents.preview.tabsLabel')}>
          <button type="button" role="tab" aria-selected={tab === 'source'} onClick={() => setTab('source')}>
            {t('documents.preview.sourceTab')}
          </button>
          <button type="button" role="tab" aria-selected={tab === 'parsed'} onClick={() => setTab('parsed')}>
            {t('documents.preview.parsedTab')}
          </button>
        </div>
        <div className="documents-preview-content">
          {tab === 'source' && (
            sourceLoading ? <PreviewLoading />
              : sourceError ? <PreviewEmpty message={t('documents.preview.sourceError')} />
                : source ? <Suspense fallback={<PreviewLoading />}><PdfViewer data={source} /></Suspense>
                  : <PreviewLoading />
          )}
          {tab === 'parsed' && (
            markdownLoading ? <PreviewLoading />
              : markdownError ? <PreviewEmpty message={t('documents.preview.parsedError')} />
                : markdown !== undefined ? <div className="documents-preview-markdown"><Markdown variant="panel" content={markdown} /></div>
                  : <PreviewEmpty message={t('documents.preview.noParsed')} action={onOpenParser && documentId ? { label: t('documents.preview.openParser'), onClick: () => onOpenParser(documentId) } : undefined} />
          )}
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
