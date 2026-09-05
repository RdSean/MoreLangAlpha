import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import './DocumentsPage.css';

type DocumentsTab = 'datasets' | 'documents';

const TABS: Array<{ id: DocumentsTab; labelKey: string }> = [
  { id: 'datasets', labelKey: 'documents.tabs.datasets' },
  { id: 'documents', labelKey: 'documents.tabs.allDocuments' },
];

export default function DocumentsPage() {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab: DocumentsTab = searchParams.get('tab') === 'documents' ? 'documents' : 'datasets';

  const selectTab = (tab: DocumentsTab) => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.set('tab', tab);
      return next;
    });
  };

  const activeLabel = t(TABS.find((tab) => tab.id === activeTab)!.labelKey);

  return (
    <div className="documents-page">
      <div className="documents-container">
        <header className="documents-header">
          <h1 className="documents-title title-font">{t('documents.title')}</h1>
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
        />
      </div>
    </div>
  );
}
