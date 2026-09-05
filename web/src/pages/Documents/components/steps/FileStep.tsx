import { useEffect, useState } from 'react';
import { FileText, Upload } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import type { DatasetSummary, DocumentSummary, Tag } from '../../types';

interface FileStepProps {
  document?: DocumentSummary;
  datasets: DatasetSummary[];
  tags: Tag[];
  initialDatasetIds: string[];
  pending: boolean;
  uploadProgress: number;
  error?: string;
  onSubmit: (selection: { file?: File; datasetIds: string[]; tagIds: string[] }) => void;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const value = bytes >= 1024 * 1024 ? bytes / (1024 * 1024) : bytes / 1024;
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${bytes >= 1024 * 1024 ? 'MB' : 'KB'}`;
}

export default function FileStep({
  document,
  datasets,
  tags,
  initialDatasetIds,
  pending,
  uploadProgress,
  error,
  onSubmit,
}: FileStepProps) {
  const { t } = useTranslation();
  const [file, setFile] = useState<File>();
  const [datasetIds, setDatasetIds] = useState(initialDatasetIds);
  const [tagIds, setTagIds] = useState<string[]>([]);

  useEffect(() => setDatasetIds(initialDatasetIds), [initialDatasetIds]);

  const toggle = (values: string[], value: string, checked: boolean) => (
    checked ? [...values, value] : values.filter((item) => item !== value)
  );

  return (
    <form
      className="documents-wizard-step"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit({ file, datasetIds, tagIds });
      }}
    >
      <div>
        <h2>{t('documents.wizard.file.title')}</h2>
        <p>{t('documents.wizard.file.subtitle')}</p>
      </div>

      {document ? (
        <div className="documents-file-summary">
          <FileText className="h-5 w-5" aria-hidden="true" />
          <div>
            <strong>{document.original_filename}</strong>
            <span>{formatBytes(document.source_size_bytes)} · {document.document_format.toUpperCase()}</span>
          </div>
        </div>
      ) : (
        <label className="documents-file-picker" htmlFor="document-pdf-file">
          <Upload className="h-5 w-5" aria-hidden="true" />
          <span>{file ? file.name : t('documents.wizard.file.pick')}</span>
          {file && <small>{formatBytes(file.size)}</small>}
          <input
            id="document-pdf-file"
            type="file"
            accept="application/pdf,.pdf"
            aria-label={t('documents.wizard.file.inputLabel')}
            disabled={pending}
            onChange={(event) => setFile(event.target.files?.[0])}
          />
        </label>
      )}

      {(datasets.length > 0 || tags.length > 0) && (
        <div className="documents-file-options">
          {datasets.length > 0 && (
            <fieldset>
              <legend>{t('documents.wizard.file.datasets')}</legend>
              <div className="documents-option-checks">
                {datasets.map((dataset) => (
                  <label key={dataset.dataset_id}>
                    <input
                      type="checkbox"
                      checked={datasetIds.includes(dataset.dataset_id)}
                      onChange={(event) => setDatasetIds(toggle(datasetIds, dataset.dataset_id, event.target.checked))}
                    />
                    <span>{dataset.name}</span>
                  </label>
                ))}
              </div>
            </fieldset>
          )}
          {tags.length > 0 && (
            <fieldset>
              <legend>{t('documents.wizard.file.tags')}</legend>
              <div className="documents-option-checks">
                {tags.map((tag) => (
                  <label key={tag.tag_id}>
                    <input
                      type="checkbox"
                      checked={tagIds.includes(tag.tag_id)}
                      onChange={(event) => setTagIds(toggle(tagIds, tag.tag_id, event.target.checked))}
                    />
                    <span>{tag.name}</span>
                  </label>
                ))}
              </div>
            </fieldset>
          )}
        </div>
      )}

      {error && <p className="documents-wizard-error" role="alert">{error}</p>}
      {pending && (
        <div className="documents-upload-progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={uploadProgress}>
          <span style={{ width: `${uploadProgress}%` }} />
        </div>
      )}
      <div className="documents-wizard-actions">
        <Button type="submit" disabled={pending || (!document && !file)}>
          {pending
            ? t('documents.wizard.file.inspecting')
            : t(document ? 'documents.wizard.file.inspectExisting' : 'documents.wizard.file.submit')}
        </Button>
      </div>
    </form>
  );
}
