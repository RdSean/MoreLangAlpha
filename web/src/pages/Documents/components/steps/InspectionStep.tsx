import { RotateCcw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import type { DocumentSummary, InspectionOutcome, JsonValue } from '../../types';

interface InspectionStepProps {
  document: DocumentSummary;
  outcome: InspectionOutcome;
  pending: boolean;
  onRetry: () => void;
  onContinue: () => void;
}

function numberValue(value: JsonValue | undefined): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

function pageDimensions(value: JsonValue | undefined): string | undefined {
  if (!Array.isArray(value) || value.length === 0) return undefined;
  const first = value[0];
  if (!first || typeof first !== 'object' || Array.isArray(first)) return undefined;
  const width = numberValue(first.width_points);
  const height = numberValue(first.height_points);
  if (width === undefined || height === undefined) return undefined;
  return `${Math.round(width)} × ${Math.round(height)} pt`;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const megabytes = bytes / (1024 * 1024);
  return megabytes >= 1 ? `${megabytes.toFixed(megabytes >= 10 ? 0 : 1)} MB` : `${Math.round(bytes / 1024)} KB`;
}

export default function InspectionStep({ document, outcome, pending, onRetry, onContinue }: InspectionStepProps) {
  const { t } = useTranslation();
  const { inspection, parser_options: parserOptions } = outcome;
  const pageCount = numberValue(inspection.summary.page_count);
  const dimensions = pageDimensions(inspection.summary.page_dimensions);
  const recommended = parserOptions.find((option) => option.recommended);
  const completed = inspection.status === 'completed';

  return (
    <div className="documents-wizard-step">
      <div>
        <h2>{t('documents.wizard.inspection.title')}</h2>
        <p>{completed ? t('documents.wizard.inspection.subtitle') : t('documents.wizard.inspection.failed')}</p>
      </div>

      <dl className="documents-inspection-summary">
        <div><dt>{t('documents.wizard.summary.filename')}</dt><dd>{document.original_filename}</dd></div>
        <div><dt>{t('documents.wizard.summary.size')}</dt><dd>{formatBytes(document.source_size_bytes)}</dd></div>
        {pageCount !== undefined && <div><dt>{t('documents.wizard.summary.pages')}</dt><dd>{t('documents.wizard.summary.pageCount', { count: pageCount })}</dd></div>}
        {dimensions && <div><dt>{t('documents.wizard.summary.dimensions')}</dt><dd>{dimensions}</dd></div>}
        <div>
          <dt>{t('documents.wizard.summary.classification')}</dt>
          <dd>{t(`documents.classification.${inspection.classification ?? 'unknown'}`)}</dd>
        </div>
      </dl>

      {recommended && (
        <div className="documents-recommendation">
          <span>{t('documents.wizard.inspection.recommended')}</span>
          <strong>{recommended.display_name}</strong>
          <p>{recommended.reason}</p>
        </div>
      )}
      {!completed && inspection.error_message && <p className="documents-wizard-error" role="alert">{inspection.error_message}</p>}

      <div className="documents-wizard-actions">
        {!completed ? (
          <Button type="button" variant="outline" disabled={pending} onClick={onRetry}>
            <RotateCcw className="mr-2 h-4 w-4" aria-hidden="true" />
            {t('documents.wizard.inspection.retry')}
          </Button>
        ) : (
          <Button type="button" onClick={onContinue}>{t('documents.wizard.inspection.continue')}</Button>
        )}
      </div>
    </div>
  );
}
