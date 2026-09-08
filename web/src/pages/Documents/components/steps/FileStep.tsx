import { useEffect, useState } from 'react';
import { Check, ChevronDown, FileText, Plus, Upload } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import type { DatasetSummary, DocumentSummary, Tag } from '../../types';
import DatasetDialog from '../DatasetDialog';

interface FileStepProps {
  document?: DocumentSummary;
  datasets: DatasetSummary[];
  tags: Tag[];
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
  pending,
  uploadProgress,
  error,
  onSubmit,
}: FileStepProps) {
  const { t } = useTranslation();
  const [file, setFile] = useState<File>();
  const [datasetIds, setDatasetIds] = useState<string[]>([]);
  const [tagIds, setTagIds] = useState<string[]>([]);
  const [createDatasetOpen, setCreateDatasetOpen] = useState(false);
  const [createdDatasets, setCreatedDatasets] = useState<DatasetSummary[]>([]);

  useEffect(() => {
    setDatasetIds([]);
    setTagIds([]);
  }, [document?.document_id]);

  const updateDatasetIds = (next: string[]) => {
    setDatasetIds(next);
  };

  const toggleDataset = (datasetId: string) => {
    updateDatasetIds(
      datasetIds.includes(datasetId)
        ? datasetIds.filter((item) => item !== datasetId)
        : [...datasetIds, datasetId],
    );
  };

  const availableDatasets = [...datasets, ...createdDatasets.filter((created) => !datasets.some((dataset) => dataset.dataset_id === created.dataset_id))];
  const selectedDatasets = availableDatasets.filter((dataset) => datasetIds.includes(dataset.dataset_id));
  const otherDatasets = availableDatasets.filter((dataset) => !datasetIds.includes(dataset.dataset_id));

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

      <div className="documents-file-options">
          <fieldset>
            <legend>{t('documents.wizard.file.datasets')}</legend>
            <div className="flex min-w-0 items-stretch">
              <Popover>
                <PopoverTrigger asChild>
                  <Button
                    type="button"
                    variant="outline"
                    className="min-h-11 min-w-0 flex-1 justify-between rounded-r-none px-3 text-left font-normal"
                    disabled={pending}
                    aria-label={t('documents.wizard.file.datasetSelectorLabel')}
                  >
                    {selectedDatasets.length === 0 ? (
                      <span className="truncate">{t('documents.wizard.file.datasetPlaceholder')}</span>
                    ) : (
                      <span className="flex min-w-0 flex-1 flex-wrap gap-1">
                        {selectedDatasets.map((dataset) => (
                          <span key={dataset.dataset_id} className="inline-flex max-w-full items-center rounded-full bg-secondary px-2 py-0.5 text-xs font-medium text-secondary-foreground">
                            <span className="truncate">{dataset.name}</span>
                          </span>
                        ))}
                      </span>
                    )}
                    <ChevronDown className="ml-2 size-4 shrink-0" aria-hidden="true" />
                  </Button>
                </PopoverTrigger>
                <PopoverContent align="start" className="w-[min(24rem,calc(100vw-4rem))] p-2">
                  <div className="max-h-64 overflow-y-auto">
                    {availableDatasets.length === 0 ? (
                      <p className="px-2 py-3 text-sm text-muted-foreground">{t('documents.wizard.file.noDatasets')}</p>
                    ) : (
                      <>
                        {selectedDatasets.length > 0 && (
                          <p className="px-2 pb-1 pt-1 text-xs font-medium text-muted-foreground">
                            {t('documents.wizard.file.selectedGroup')}
                          </p>
                        )}
                        {selectedDatasets.map((dataset) => (
                          <button
                            key={dataset.dataset_id}
                            type="button"
                            aria-pressed="true"
                            className="flex min-h-11 w-full items-center gap-2 rounded-md px-2 text-left text-sm hover:bg-[var(--color-bg-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                            onClick={() => toggleDataset(dataset.dataset_id)}
                          >
                            <span className="flex size-4 shrink-0 items-center justify-center rounded-sm border border-primary bg-primary text-primary-foreground">
                              <Check className="size-3" aria-hidden="true" />
                            </span>
                            <span className="min-w-0 flex-1 truncate">{dataset.name}</span>
                          </button>
                        ))}
                        {otherDatasets.length > 0 && (
                          <p className="px-2 pb-1 pt-3 text-xs font-medium text-muted-foreground">
                            {t(selectedDatasets.length > 0 ? 'documents.wizard.file.otherGroup' : 'documents.wizard.file.allGroup')}
                          </p>
                        )}
                        {otherDatasets.map((dataset) => (
                          <button
                            key={dataset.dataset_id}
                            type="button"
                            aria-pressed="false"
                            className="flex min-h-11 w-full items-center gap-2 rounded-md px-2 text-left text-sm hover:bg-[var(--color-bg-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                            onClick={() => toggleDataset(dataset.dataset_id)}
                          >
                            <span className="size-4 shrink-0 rounded-sm border" aria-hidden="true" />
                            <span className="min-w-0 flex-1 truncate">{dataset.name}</span>
                          </button>
                        ))}
                      </>
                    )}
                  </div>
                </PopoverContent>
              </Popover>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    type="button"
                    variant="outline"
                    size="icon"
                    className="min-h-11 min-w-11 shrink-0 rounded-l-none border-l-0"
                    disabled={pending}
                    aria-label={t('documents.wizard.file.datasetActions')}
                  >
                    <ChevronDown className="size-4" aria-hidden="true" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onSelect={() => setCreateDatasetOpen(true)}>
                    <Plus className="size-4" aria-hidden="true" />
                    {t('documents.wizard.file.createDataset')}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
            <DatasetDialog
              open={createDatasetOpen}
              onOpenChange={setCreateDatasetOpen}
              onCreated={(dataset) => {
                setCreatedDatasets((current) => [...current, dataset]);
                updateDatasetIds([...datasetIds, dataset.dataset_id]);
                setCreateDatasetOpen(false);
              }}
            />
          </fieldset>
          {tags.length > 0 && (
            <fieldset>
              <legend>{t('documents.wizard.file.tags')}</legend>
              <div className="documents-option-checks">
                {tags.map((tag) => (
                  <label key={tag.tag_id}>
                    <input
                      type="checkbox"
                      checked={tagIds.includes(tag.tag_id)}
                      onChange={(event) => setTagIds((values) => event.target.checked ? [...values, tag.tag_id] : values.filter((item) => item !== tag.tag_id))}
                    />
                    <span>{tag.name}</span>
                  </label>
                ))}
              </div>
            </fieldset>
          )}
      </div>

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
