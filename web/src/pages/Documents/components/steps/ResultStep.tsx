import { Download, FileJson, FileText, Image } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import Markdown from '@/pages/ChatAgent/components/Markdown';
import { artifactDownloadUrl } from '../../api';
import type { Artifact, ParseJob } from '../../types';

interface ResultStepProps {
  artifacts: Artifact[];
  markdown?: string;
  previewError?: string;
  jobs: ParseJob[];
  onParseAgain: () => void;
  onComplete: () => void;
}

function ArtifactIcon({ artifact }: { artifact: Artifact }) {
  if (artifact.artifact_kind === 'embedded_image') return <Image className="h-4 w-4" aria-hidden="true" />;
  if (artifact.artifact_kind === 'structured_data' || artifact.format === 'json') return <FileJson className="h-4 w-4" aria-hidden="true" />;
  return <FileText className="h-4 w-4" aria-hidden="true" />;
}

export default function ResultStep({ artifacts, markdown, previewError, jobs, onParseAgain, onComplete }: ResultStepProps) {
  const { t } = useTranslation();
  return (
    <div className="documents-wizard-step documents-result-step">
      <div>
        <img className="documents-result-confetti" src="/task-celebrating-confetti.svg" alt="" aria-hidden="true" />
        <h2>{t('documents.wizard.result.title')}</h2>
        <p>{t('documents.wizard.result.subtitle')}</p>
      </div>

      {markdown !== undefined && (
        <section className="documents-markdown-preview" aria-label={t('documents.wizard.result.preview')}>
          <Markdown content={markdown} variant="panel" />
        </section>
      )}
      {previewError && <p className="documents-wizard-error" role="alert">{previewError}</p>}

      <section className="documents-artifacts" aria-labelledby="document-artifacts-title">
        <h3 id="document-artifacts-title">{t('documents.wizard.result.artifacts')}</h3>
        <div className="documents-artifact-list">
          {artifacts.map((artifact) => (
            <div key={artifact.artifact_id} className="documents-artifact-row">
              <ArtifactIcon artifact={artifact} />
              <div>
                <strong>{artifact.relative_path}</strong>
                <span>{artifact.format} · {artifact.media_type}</span>
              </div>
              <a
                href={artifactDownloadUrl(artifact.artifact_id)}
                aria-label={t('documents.wizard.result.downloadLabel', { name: artifact.relative_path })}
                title={t('documents.wizard.result.downloadLabel', { name: artifact.relative_path })}
              >
                <Download className="h-4 w-4" aria-hidden="true" />
              </a>
            </div>
          ))}
        </div>
      </section>

      {jobs.length > 0 && (
        <section className="documents-job-history" aria-labelledby="document-job-history-title">
          <h3 id="document-job-history-title">{t('documents.wizard.result.history')}</h3>
          <div>
            {jobs.map((job) => (
              <div key={job.job_id} className="documents-job-history-row">
                <span>{job.parser_name}</span>
                <code>{t(`documents.status.${job.status}`)}</code>
              </div>
            ))}
          </div>
        </section>
      )}

      <div className="documents-wizard-actions">
        <Button type="button" variant="outline" onClick={onParseAgain}>{t('documents.wizard.result.parseAgain')}</Button>
        <Button type="button" onClick={onComplete}>{t('documents.wizard.result.complete')}</Button>
      </div>
    </div>
  );
}
