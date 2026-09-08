import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { fetchArtifactText, listDocumentArtifacts, watchDocumentJob } from '../api';
import {
  useDocument,
  useDocumentDatasets,
  useDocumentJobs,
  useDocumentMutations,
  useDocumentTags,
} from '../hooks';
import type { Artifact, DocumentSummary, InspectionOutcome, ParseJob } from '../types';
import FileStep from './steps/FileStep';
import InspectionStep from './steps/InspectionStep';
import MethodStep from './steps/MethodStep';
import ProgressStep from './steps/ProgressStep';
import ResultStep from './steps/ResultStep';

type WizardStage = 'file' | 'inspection' | 'method' | 'progress' | 'result';

const STAGES: WizardStage[] = ['file', 'inspection', 'method', 'progress', 'result'];
const TERMINAL = new Set<ParseJob['status']>(['completed', 'failed', 'cancelled']);

interface DocumentWizardProps {
  open: boolean;
  documentId?: string;
  onOpenChange: (open: boolean) => void;
}

export default function DocumentWizard({
  open,
  documentId,
  onOpenChange,
}: DocumentWizardProps) {
  const { t } = useTranslation();
  const existingDocument = useDocument(documentId);
  const datasets = useDocumentDatasets({ limit: 100, offset: 0 });
  const tags = useDocumentTags();
  const mutations = useDocumentMutations();
  const [stage, setStage] = useState<WizardStage>('file');
  const [document, setDocument] = useState<DocumentSummary>();
  const [outcome, setOutcome] = useState<InspectionOutcome>();
  const [selectedParserId, setSelectedParserId] = useState('');
  const [job, setJob] = useState<ParseJob>();
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [markdown, setMarkdown] = useState<string>();
  const [uploadProgress, setUploadProgress] = useState(0);
  const [error, setError] = useState<string>();
  const [streamError, setStreamError] = useState<string>();
  const loadedJobRef = useRef<string | undefined>(undefined);
  const jobs = useDocumentJobs(document?.document_id);
  const refetchJobs = jobs.refetch;

  useEffect(() => {
    if (open && existingDocument.data && existingDocument.data.document_id === documentId) {
      setDocument(existingDocument.data);
    }
  }, [documentId, existingDocument.data, open]);

  useEffect(() => {
    if (open) return;
    setStage('file');
    setDocument(undefined);
    setOutcome(undefined);
    setSelectedParserId('');
    setJob(undefined);
    setArtifacts([]);
    setMarkdown(undefined);
    setUploadProgress(0);
    setError(undefined);
    setStreamError(undefined);
    loadedJobRef.current = undefined;
  }, [open]);

  const inspect = async (source: DocumentSummary) => {
    setError(undefined);
    try {
      const nextOutcome = await mutations.inspectDocument.mutateAsync(source.document_id);
      setOutcome(nextOutcome);
      setSelectedParserId('');
      setStage('inspection');
    } catch {
      setError(t('documents.wizard.errors.inspection'));
    }
  };

  const prepare = async (selection: { file?: File; datasetIds: string[]; tagIds: string[] }) => {
    setError(undefined);
    setUploadProgress(0);
    try {
      let source = document;
      if (!source) {
        if (!selection.file) return;
        source = await mutations.uploadDocument.mutateAsync({
          file: selection.file,
          datasetIds: selection.datasetIds,
          tagIds: selection.tagIds,
          onProgress: setUploadProgress,
        });
        setDocument(source);
      }
      await inspect(source);
    } catch {
      setError(t('documents.wizard.errors.upload'));
    }
  };

  const loadResult = useCallback(async (snapshot: ParseJob) => {
    if (loadedJobRef.current === snapshot.job_id) return;
    loadedJobRef.current = snapshot.job_id;
    setError(undefined);
    try {
      const nextArtifacts = await listDocumentArtifacts(snapshot.document_id, snapshot.job_id);
      setArtifacts(nextArtifacts);
      const primary = nextArtifacts.find((artifact) => (
        artifact.artifact_kind === 'primary_document'
        && (artifact.format === 'markdown' || artifact.media_type === 'text/markdown')
      ));
      if (primary) {
        try {
          setMarkdown(await fetchArtifactText(primary.artifact_id));
        } catch {
          setError(t('documents.wizard.errors.preview'));
        }
      } else {
        setMarkdown(undefined);
      }
      setStage('result');
      void refetchJobs();
    } catch {
      loadedJobRef.current = undefined;
      setError(t('documents.wizard.errors.artifacts'));
    }
  }, [refetchJobs, t]);

  const activeJobId = job?.job_id;
  useEffect(() => {
    if (!open || !activeJobId || !job) return;
    if (job.status === 'completed') {
      void loadResult(job);
      return;
    }
    if (TERMINAL.has(job.status)) return;

    const controller = new AbortController();
    void watchDocumentJob(activeJobId, {
      signal: controller.signal,
      onSnapshot: (snapshot) => {
        setJob((current) => !current || snapshot.status_version >= current.status_version ? snapshot : current);
        if (snapshot.status === 'completed') void loadResult(snapshot);
      },
      onError: () => setStreamError(t('documents.wizard.progress.polling')),
    });
    return () => controller.abort();
    // A watcher belongs to one durable job ID; snapshots update `job` without
    // replacing the connection that is already following that job.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeJobId, loadResult, open]);

  const start = async () => {
    if (!document || !outcome || !selectedParserId) return;
    setError(undefined);
    setStreamError(undefined);
    try {
      const created = await mutations.createParseJob.mutateAsync({
        documentId: document.document_id,
        input: {
          inspection_id: outcome.inspection.inspection_id,
          parser_id: selectedParserId,
          mode: 'async',
          options: {},
        },
      });
      loadedJobRef.current = undefined;
      setJob(created.job);
      setStage('progress');
    } catch {
      setError(t('documents.wizard.errors.start'));
    }
  };

  const cancel = async () => {
    if (!job) return;
    try {
      setJob(await mutations.cancelJob.mutateAsync(job.job_id));
    } catch {
      setStreamError(t('documents.wizard.errors.cancel'));
    }
  };

  const chooseAgain = () => {
    setSelectedParserId('');
    setJob(undefined);
    setArtifacts([]);
    setMarkdown(undefined);
    setError(undefined);
    setStage('method');
  };

  const currentStep = STAGES.indexOf(stage);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="documents-wizard" variant="centered">
        <DialogHeader>
          <DialogTitle className="title-font">{t('documents.wizard.title')}</DialogTitle>
        </DialogHeader>
        <ol className="documents-wizard-stepper" aria-label={t('documents.wizard.progressLabel')}>
          {STAGES.map((item, index) => (
            <li key={item} className={index <= currentStep ? 'is-reached' : ''} aria-current={index === currentStep ? 'step' : undefined}>
              <span>{index + 1}</span>
              <small>{t(`documents.wizard.steps.${item}`)}</small>
            </li>
          ))}
        </ol>

        <div className="documents-wizard-body">
          {stage === 'file' && (
            <FileStep
              document={document}
              datasets={datasets.data?.items ?? []}
              tags={tags.data ?? []}
              pending={mutations.uploadDocument.isPending || mutations.inspectDocument.isPending}
              uploadProgress={uploadProgress}
              error={error}
              onSubmit={(selection) => void prepare(selection)}
            />
          )}
          {stage === 'inspection' && document && outcome && (
            <InspectionStep
              document={document}
              outcome={outcome}
              pending={mutations.inspectDocument.isPending}
              onRetry={() => void inspect(document)}
              onContinue={() => setStage('method')}
            />
          )}
          {stage === 'method' && outcome && (
            <MethodStep
              options={outcome.parser_options}
              selectedParserId={selectedParserId}
              pending={mutations.createParseJob.isPending}
              error={error}
              onSelect={setSelectedParserId}
              onBack={() => setStage('inspection')}
              onStart={() => void start()}
            />
          )}
          {stage === 'progress' && job && (
            <ProgressStep
              job={job}
              cancelling={mutations.cancelJob.isPending}
              streamError={streamError}
              onCancel={() => void cancel()}
              onChooseAnother={chooseAgain}
            />
          )}
          {stage === 'result' && (
            <ResultStep
              artifacts={artifacts}
              markdown={markdown}
              previewError={error}
              jobs={jobs.data ?? []}
              onParseAgain={chooseAgain}
              onComplete={() => onOpenChange(false)}
            />
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
