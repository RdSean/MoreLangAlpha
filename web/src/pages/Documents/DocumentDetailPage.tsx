import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, FileText, Loader2, RefreshCw } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useDocument } from './hooks';
import DocumentContentPane, { type DocumentContentTab } from './components/DocumentContentPane';
import TeachingUsagePanel from './components/TeachingUsagePanel';
import './DocumentDetailPage.css';

type DocumentDetailTab = DocumentContentTab | 'teaching';

const TABS: Array<{ id: DocumentDetailTab; labelKey: string }> = [
  { id: 'source', labelKey: 'documents.detail.sourceTab' },
  { id: 'parsed', labelKey: 'documents.detail.parsedTab' },
  { id: 'teaching', labelKey: 'documents.detail.teachingTab' },
];

export default function DocumentDetailPage() {
  const { t } = useTranslation();
  const { documentId } = useParams();
  const documentRecord = useDocument(documentId);
  const [activeTab, setActiveTab] = useState<DocumentDetailTab>('source');

  useEffect(() => {
    setActiveTab('source');
  }, [documentId]);

  if (documentRecord.isLoading) {
    return (
      <DocumentDetailFrame>
        <div className="documents-detail-state" role="status">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          {t('documents.detail.loading')}
        </div>
      </DocumentDetailFrame>
    );
  }

  if (documentRecord.isError) {
    return (
      <DocumentDetailFrame>
        <div className="documents-detail-state documents-detail-state--error" role="alert">
          <p>{t('documents.detail.loadFailed')}</p>
          <Button type="button" variant="outline" size="sm" onClick={() => void documentRecord.refetch()}>
            <RefreshCw className="mr-2 h-3.5 w-3.5" aria-hidden="true" />
            {t('documents.actions.retry')}
          </Button>
        </div>
      </DocumentDetailFrame>
    );
  }

  if (!documentRecord.data || !documentId) {
    return (
      <DocumentDetailFrame>
        <div className="documents-detail-state">
          <p>{t('documents.detail.notFound')}</p>
        </div>
      </DocumentDetailFrame>
    );
  }

  const document = documentRecord.data;

  return (
    <main className="documents-detail-page" data-testid="document-detail-page">
      <div className="documents-detail-container">
        <header className="documents-detail-header">
          <Link className="documents-detail-back" to="/documents">
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
            {t('documents.detail.back')}
          </Link>
          <div className="documents-detail-title-row">
            <div className="min-w-0">
              <p className="documents-detail-eyebrow">{t('documents.title')}</p>
              <div className="documents-detail-name">
                <FileText className="h-5 w-5 shrink-0" aria-hidden="true" />
                <h1>{document.original_filename}</h1>
                {document.parse_status && (
                  <Badge variant="muted">{t(`documents.status.${document.parse_status}`)}</Badge>
                )}
              </div>
            </div>
          </div>
        </header>

        <div className="documents-detail-tabs" role="tablist" aria-label={t('documents.detail.tabsLabel')}>
          {TABS.map((tab) => {
            const selected = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                id={`document-detail-tab-${tab.id}`}
                type="button"
                role="tab"
                aria-selected={selected}
                aria-controls={`document-detail-panel-${tab.id}`}
                tabIndex={selected ? 0 : -1}
                className={`documents-detail-tab${selected ? ' is-active' : ''}`}
                onClick={() => setActiveTab(tab.id)}
              >
                {t(tab.labelKey)}
              </button>
            );
          })}
        </div>

        <section
          id={`document-detail-panel-${activeTab}`}
          className={`documents-detail-panel documents-detail-panel--${activeTab}`}
          role="tabpanel"
          aria-labelledby={`document-detail-tab-${activeTab}`}
        >
          {activeTab === 'teaching' ? (
            <TeachingUsagePanel documentId={documentId} />
          ) : (
            <DocumentContentPane
              documentId={documentId}
              document={document}
              activeTab={activeTab}
            />
          )}
        </section>
      </div>
    </main>
  );
}

function DocumentDetailFrame({ children }: { children: React.ReactNode }) {
  const { t } = useTranslation();
  return (
    <main className="documents-detail-page">
      <div className="documents-detail-container">
        <Link className="documents-detail-back" to="/documents">
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          {t('documents.detail.back')}
        </Link>
        {children}
      </div>
    </main>
  );
}
