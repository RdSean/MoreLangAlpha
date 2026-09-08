import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, Upload } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useDocumentDataset } from './hooks';
import DatasetGrid from './components/DatasetGrid';
import DocumentTable, { type DocumentTableFilters } from './components/DocumentTable';
import DocumentWizard from './components/DocumentWizard';
import DocumentPreviewDrawer from './components/DocumentPreviewDrawer';
import type { DatasetSummary, DocumentSummary } from './types';
import './DocumentsPage.css';

type DocumentsTab = 'datasets' | 'documents';

const TABS: Array<{ id: DocumentsTab; labelKey: string }> = [
  { id: 'datasets', labelKey: 'documents.tabs.datasets' },
  { id: 'documents', labelKey: 'documents.tabs.allDocuments' },
];

function positivePage(value: string | null): number {
  const page = Number(value);
  return Number.isInteger(page) && page > 0 ? page : 1;
}

function readTableFilters(params: URLSearchParams, prefix: string): DocumentTableFilters {
  return {
    query: params.get(`${prefix}_q`) ?? '',
    datasetId: params.get(`${prefix}_dataset`) ?? '',
    tagIds: (params.get(`${prefix}_tags`) ?? '').split(',').filter(Boolean),
    mediaType: params.get(`${prefix}_media`) ?? '',
    classification: (params.get(`${prefix}_classification`) ?? '') as DocumentTableFilters['classification'],
    parseStatus: (params.get(`${prefix}_status`) ?? '') as DocumentTableFilters['parseStatus'],
  };
}

function writeTableFilters(params: URLSearchParams, prefix: string, filters: DocumentTableFilters): void {
  const values: Record<string, string> = {
    q: filters.query,
    dataset: filters.datasetId,
    tags: filters.tagIds.join(','),
    media: filters.mediaType,
    classification: filters.classification,
    status: filters.parseStatus,
  };
  for (const [key, value] of Object.entries(values)) {
    const name = `${prefix}_${key}`;
    if (value) params.set(name, value);
    else params.delete(name);
  }
}

function DatasetDocuments({
  datasetId,
  filters,
  page,
  onBack,
  onFiltersChange,
  onPageChange,
  onOpenDocument,
}: {
  datasetId: string;
  filters: DocumentTableFilters;
  page: number;
  onBack: () => void;
  onFiltersChange: (filters: DocumentTableFilters, resetPage: boolean) => void;
  onPageChange: (page: number) => void;
  onOpenDocument: (document: DocumentSummary) => void;
}) {
  const { t } = useTranslation();
  const dataset = useDocumentDataset(datasetId);
  return (
    <div className="documents-dataset-detail">
      <div className="documents-dataset-detail-header">
        <Button type="button" variant="ghost" size="icon" onClick={onBack} aria-label={t('documents.datasets.back')}>
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        </Button>
        <div>
          <h2>{dataset.data?.name ?? t('documents.datasets.datasetFallback')}</h2>
          {dataset.data?.description && <p>{dataset.data.description}</p>}
        </div>
      </div>
      <DocumentTable
        datasetId={datasetId}
        filters={filters}
        page={page}
        onFiltersChange={onFiltersChange}
        onPageChange={onPageChange}
        onOpenDocument={onOpenDocument}
      />
    </div>
  );
}

export default function DocumentsPage() {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab: DocumentsTab = searchParams.get('tab') === 'documents' ? 'documents' : 'datasets';
  const selectedDatasetId = searchParams.get('dataset');
  const selectedDocumentId = searchParams.get('document') ?? undefined;
  const wizardOpen = searchParams.get('upload') === '1';
  const datasetPage = positivePage(searchParams.get('datasets_page'));
  const allDocumentsPage = positivePage(searchParams.get('documents_page'));
  const datasetDocumentsPage = positivePage(searchParams.get('dataset_documents_page'));
  const allDocumentsFilters = readTableFilters(searchParams, 'documents');
  const datasetDocumentsFilters = readTableFilters(searchParams, 'dataset_documents');
  const [previewOpen, setPreviewOpen] = useState(Boolean(selectedDocumentId) && !wizardOpen);

  useEffect(() => {
    setPreviewOpen(Boolean(selectedDocumentId) && !wizardOpen);
  }, [selectedDocumentId, wizardOpen]);

  const updateParams = (change: (params: URLSearchParams) => void) => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      change(next);
      return next;
    }, { replace: true });
  };

  const selectTab = (tab: DocumentsTab) => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.set('tab', tab);
      return next;
    });
  };

  const activeLabel = t(TABS.find((tab) => tab.id === activeTab)!.labelKey);
  const openDataset = (dataset: DatasetSummary) => updateParams((params) => params.set('dataset', dataset.dataset_id));
  const openDocument = (document: DocumentSummary) => {
    setPreviewOpen(true);
    updateParams((params) => params.set('document', document.document_id));
  };
  const openUpload = () => updateParams((params) => {
    params.set('upload', '1');
    params.delete('document');
  });
  const closeWizard = () => updateParams((params) => params.delete('upload'));
  const closePreview = () => setPreviewOpen(false);
  const openParserForDocument = (documentId: string) => updateParams((params) => {
    params.set('upload', '1');
    params.set('document', documentId);
  });
  const updateDocumentFilters = (prefix: string, filters: DocumentTableFilters, resetPage: boolean) => {
    updateParams((params) => {
      writeTableFilters(params, prefix, filters);
      if (resetPage) params.delete(`${prefix}_page`);
    });
  };

  return (
    <div className={`documents-page${previewOpen ? ' documents-page--preview-open' : ''}`}>
      <main className="documents-main">
      <div className="documents-container">
        <header className="documents-header">
          <h1 className="documents-title title-font">{t('documents.title')}</h1>
          <Button type="button" onClick={openUpload}>
            <Upload className="mr-2 h-4 w-4" aria-hidden="true" />
            {t('documents.wizard.open')}
          </Button>
        </header>

        <div className="documents-tabs" role="tablist" aria-label={t('documents.viewLabel')}>
          {TABS.map((tab) => {
            const selected = tab.id === activeTab;
            return (
              <button
                key={tab.id}
                id={`documents-tab-${tab.id}`}
                type="button"
                role="tab"
                aria-selected={selected}
                aria-controls={`documents-panel-${tab.id}`}
                tabIndex={selected ? 0 : -1}
                className={`documents-tab${selected ? ' is-active' : ''}`}
                onClick={() => selectTab(tab.id)}
              >
                {t(tab.labelKey)}
              </button>
            );
          })}
        </div>

        <section
          id={`documents-panel-${activeTab}`}
          className="documents-tab-panel"
          role="tabpanel"
          aria-labelledby={`documents-tab-${activeTab}`}
          aria-label={activeLabel}
        >
          {activeTab === 'datasets' && !selectedDatasetId && (
            <DatasetGrid
              query={searchParams.get('datasets_q') ?? ''}
              page={datasetPage}
              onQueryChange={(query) => updateParams((params) => {
                if (query) params.set('datasets_q', query);
                else params.delete('datasets_q');
                params.delete('datasets_page');
              })}
              onPageChange={(page) => updateParams((params) => params.set('datasets_page', String(page)))}
              onOpenDataset={openDataset}
            />
          )}
          {activeTab === 'datasets' && selectedDatasetId && (
            <DatasetDocuments
              datasetId={selectedDatasetId}
              filters={datasetDocumentsFilters}
              page={datasetDocumentsPage}
              onBack={() => updateParams((params) => params.delete('dataset'))}
              onFiltersChange={(filters, resetPage) => updateDocumentFilters('dataset_documents', filters, resetPage)}
              onPageChange={(page) => updateParams((params) => params.set('dataset_documents_page', String(page)))}
              onOpenDocument={openDocument}
            />
          )}
          {activeTab === 'documents' && (
            <DocumentTable
              filters={allDocumentsFilters}
              page={allDocumentsPage}
              onFiltersChange={(filters, resetPage) => updateDocumentFilters('documents', filters, resetPage)}
              onPageChange={(page) => updateParams((params) => params.set('documents_page', String(page)))}
              onOpenDocument={openDocument}
            />
          )}
        </section>
      </div>
      <DocumentWizard
        open={wizardOpen}
        documentId={selectedDocumentId}
        onOpenChange={(open) => !open && closeWizard()}
      />
      </main>
      <DocumentPreviewDrawer
        open={previewOpen && Boolean(selectedDocumentId) && !wizardOpen}
        documentId={selectedDocumentId}
        onOpenChange={(open) => !open && closePreview()}
        onOpenParser={openParserForDocument}
      />
    </div>
  );
}
