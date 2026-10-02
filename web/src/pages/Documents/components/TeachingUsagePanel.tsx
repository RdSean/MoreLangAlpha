import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { BookOpenCheck, ExternalLink, Loader2, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useDocumentTeachingUsage } from '../hooks';
import type { DocumentStructureStatus, DocumentTeachingUsage } from '../types';

interface TeachingUsagePanelProps {
  documentId: string;
}

const STRUCTURE_STATUS_KEYS: Record<DocumentStructureStatus, string> = {
  queued: 'queued',
  running: 'active',
  ready: 'ready',
  failed: 'failed',
};

export default function TeachingUsagePanel({ documentId }: TeachingUsagePanelProps) {
  const { t } = useTranslation();
  const usages = useDocumentTeachingUsage(documentId);

  if (usages.isLoading) {
    return (
      <div className="documents-detail-state" role="status">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        {t('documents.detail.teachingUsage.loading')}
      </div>
    );
  }

  if (usages.isError) {
    return (
      <div className="documents-detail-state documents-detail-state--error" role="alert">
        <p>{t('documents.detail.teachingUsage.loadFailed')}</p>
        <Button type="button" variant="outline" size="sm" onClick={() => void usages.refetch()}>
          <RefreshCw className="mr-2 h-3.5 w-3.5" aria-hidden="true" />
          {t('documents.actions.retry')}
        </Button>
      </div>
    );
  }

  if (!usages.data?.length) {
    return (
      <div className="documents-detail-state">
        <BookOpenCheck className="h-5 w-5" aria-hidden="true" />
        <p>{t('documents.detail.teachingUsage.empty')}</p>
      </div>
    );
  }

  return (
    <section className="documents-teaching-usage" aria-label={t('documents.detail.teachingUsage.label')}>
      <ol className="documents-teaching-usage-list">
        {usages.data.map((usage) => (
          <TeachingUsageItem key={usage.textbook_id} usage={usage} />
        ))}
      </ol>
    </section>
  );
}

function TeachingUsageItem({ usage }: { usage: DocumentTeachingUsage }) {
  const { t } = useTranslation();
  const textbookPath = `/textbooks/${encodeURIComponent(usage.textbook_id)}`;
  const statusKey = STRUCTURE_STATUS_KEYS[usage.structure_status];

  return (
    <li className="documents-teaching-usage-item">
      <div className="documents-teaching-usage-heading">
        <div className="min-w-0">
          <Link className="documents-teaching-usage-title" to={textbookPath}>
            {usage.textbook_title}
          </Link>
          <div className="documents-teaching-usage-meta">
            <span>{usage.source_filename}</span>
            <span>{t('documents.detail.teachingUsage.artifact', { id: usage.primary_artifact_id })}</span>
            <span>{t('documents.detail.teachingUsage.job', { id: usage.parse_job_id })}</span>
          </div>
        </div>
        <span className={`documents-teaching-usage-status is-${statusKey}`}>
          {t(`documents.detail.teachingUsage.status.${statusKey}`)}
        </span>
      </div>

      <div className="documents-teaching-usage-package">
        <span>{t('documents.detail.teachingUsage.materials', usage.materials)}</span>
        <Link className="documents-teaching-usage-asset-link" to={textbookPath}>
          <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
          {t('documents.detail.teachingUsage.openTextbook')}
        </Link>
      </div>
    </li>
  );
}
