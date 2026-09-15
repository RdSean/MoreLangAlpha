import { AlertCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import type { ParseJob } from '../../types';

interface ProgressStepProps {
  job: ParseJob;
  cancelling: boolean;
  streamError?: string;
  onCancel: () => void;
  onChooseAnother: () => void;
}

export default function ProgressStep({ job, cancelling, streamError, onCancel, onChooseAnother }: ProgressStepProps) {
  const { t } = useTranslation();
  const terminalError = job.status === 'failed' || job.status === 'cancelled';

  return (
    <div className="documents-wizard-step">
      <div>
        <h2>{t('documents.wizard.progress.title')}</h2>
        <p>{job.parser_name}</p>
      </div>
      <div className="documents-job-progress">
        <div className="documents-job-progress-copy">
          <span>{t(`documents.stage.${job.stage}`)}</span>
          <strong>{job.percentage}%</strong>
        </div>
        <div className="documents-job-progress-track" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={job.percentage}>
          <span style={{ width: `${job.percentage}%` }} />
        </div>
      </div>
      {streamError && <p className="documents-wizard-notice">{streamError}</p>}
      {terminalError && (
        <div className="documents-job-error" role="alert">
          <AlertCircle className="h-5 w-5" aria-hidden="true" />
          <div>
            <strong>{t(job.status === 'cancelled' ? 'documents.wizard.progress.cancelled' : 'documents.wizard.progress.failed')}</strong>
            {job.error_message && <p>{job.error_message}</p>}
          </div>
        </div>
      )}
      <div className="documents-wizard-actions">
        {terminalError ? (
          <Button type="button" variant="outline" onClick={onChooseAnother}>{t('documents.wizard.progress.chooseAnother')}</Button>
        ) : (
          <Button type="button" variant="outline" disabled={cancelling} onClick={onCancel}>
            {cancelling ? t('documents.wizard.progress.cancelling') : t('documents.wizard.progress.cancel')}
          </Button>
        )}
      </div>
    </div>
  );
}
