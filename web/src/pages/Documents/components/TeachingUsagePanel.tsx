import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { BookOpenCheck, ExternalLink, Loader2, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useDocumentTeachingUsage } from '../hooks';
import type { DocumentTeachingPackageStatus, DocumentTeachingUsage } from '../types';

interface TeachingUsagePanelProps {
  documentId: string;
}

type DisplayStatus = DocumentTeachingPackageStatus | 'published';

const PACKAGE_STATUS_KEYS: Record<DisplayStatus, string> = {
  queued: 'queued',
  preparing: 'active',
  building_skill: 'active',
  generating_teaching: 'active',
  validating: 'active',
  running: 'active',
  review: 'review',
  published: 'published',
  failed: 'failed',
  cancelled: 'cancelled',
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
          <TeachingUsageItem key={`${usage.content_version_id}:${usage.teaching_package_id ?? 'unpackaged'}:${usage.artifact_position}`} usage={usage} />
        ))}
      </ol>
    </section>
  );
}

function TeachingUsageItem({ usage }: { usage: DocumentTeachingUsage }) {
  const { t } = useTranslation();
  const textbookPath = `/textbooks/${encodeURIComponent(usage.textbook_id)}`;
  const canOpenAssets = usage.has_asset_manifest
    && (usage.status === 'review' || usage.is_published);
  const displayStatus: DisplayStatus | null = usage.is_published ? 'published' : (usage.status ?? null);
  const statusKey = displayStatus ? PACKAGE_STATUS_KEYS[displayStatus] : null;

  return (
    <li className="documents-teaching-usage-item">
      <div className="documents-teaching-usage-heading">
        <div className="min-w-0">
          <Link className="documents-teaching-usage-title" to={textbookPath}>
            {usage.textbook_title}
          </Link>
          <div className="documents-teaching-usage-meta">
            <span>{t('documents.detail.teachingUsage.contentVersion', { sequence: usage.content_version_sequence })}</span>
            <span>{t('documents.detail.teachingUsage.sourcePosition', { position: usage.artifact_position })}</span>
            <span>{t('documents.detail.teachingUsage.artifact', { id: usage.primary_artifact_id })}</span>
            <span>{t('documents.detail.teachingUsage.job', { id: usage.producer_job_id })}</span>
          </div>
        </div>
        <span className={`documents-teaching-usage-status${statusKey ? ` is-${statusKey}` : ''}`}>
          {statusKey
            ? t(`documents.detail.teachingUsage.status.${statusKey}`)
            : t('documents.detail.teachingUsage.unpackaged')}
        </span>
      </div>

      {usage.teaching_package_id ? (
        <div className="documents-teaching-usage-package">
          <span>
            {usage.teaching_package_sequence == null
              ? t('documents.detail.teachingUsage.package')
              : t('documents.detail.teachingUsage.packageSequence', { sequence: usage.teaching_package_sequence })}
          </span>
          {canOpenAssets && (
            <Link className="documents-teaching-usage-asset-link" to={textbookPath}>
              <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
              {t('documents.detail.teachingUsage.viewAssets')}
            </Link>
          )}
        </div>
      ) : (
        <p className="documents-teaching-usage-note">
          {t('documents.detail.teachingUsage.unpackagedNote')}
        </p>
      )}
    </li>
  );
}
