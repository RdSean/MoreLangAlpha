import { useState } from 'react';
import { Folder, MoreHorizontal, Plus, Search } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import ConfirmDialog from '@/components/ui/ConfirmDialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import { useToast } from '@/components/ui/use-toast';
import { relativeTime } from '@/lib/format';
import { useDocumentDatasets, useDocumentMutations } from '../hooks';
import type { DatasetSummary } from '../types';
import DatasetDialog from './DatasetDialog';
import Pagination from './Pagination';

const PAGE_SIZE = 12;

interface DatasetGridProps {
  query: string;
  page: number;
  onQueryChange: (query: string) => void;
  onPageChange: (page: number) => void;
  onOpenDataset: (dataset: DatasetSummary) => void;
}

export default function DatasetGrid({
  query,
  page,
  onQueryChange,
  onPageChange,
  onOpenDataset,
}: DatasetGridProps) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const datasets = useDocumentDatasets({ query: query || undefined, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE });
  const mutations = useDocumentMutations();
  const [editing, setEditing] = useState<DatasetSummary>();
  const [deleting, setDeleting] = useState<DatasetSummary>();

  const removeDataset = async () => {
    if (!deleting) return;
    try {
      await mutations.deleteDataset.mutateAsync(deleting.dataset_id);
      setDeleting(undefined);
    } catch {
      toast({ variant: 'destructive', description: t('documents.datasets.deleteFailed') });
    }
  };

  return (
    <div className="documents-collection-view">
      <div className="documents-toolbar">
        <label className="documents-search-field">
          <span className="sr-only">{t('documents.datasets.searchLabel')}</span>
          <Search className="documents-search-icon" aria-hidden="true" />
          <Input
            type="search"
            value={query}
            placeholder={t('documents.datasets.searchPlaceholder')}
            aria-label={t('documents.datasets.searchLabel')}
            onChange={(event) => onQueryChange(event.target.value)}
          />
        </label>
        <DatasetDialog
          trigger={
            <Button type="button">
              <Plus className="mr-2 h-4 w-4" aria-hidden="true" />
              {t('documents.datasets.createAction')}
            </Button>
          }
        />
      </div>

      {datasets.isLoading ? (
        <div className="documents-dataset-grid" aria-label={t('documents.datasets.loading')}>
          {Array.from({ length: 6 }, (_, index) => <div key={index} className="documents-dataset-skeleton" />)}
        </div>
      ) : datasets.isError ? (
        <div className="documents-state" role="alert">
          <p>{t('documents.datasets.loadFailed')}</p>
          <Button type="button" variant="outline" size="sm" onClick={() => void datasets.refetch()}>
            {t('documents.actions.retry')}
          </Button>
        </div>
      ) : !datasets.data?.items.length ? (
        <div className="documents-state">
          <Folder className="h-6 w-6" aria-hidden="true" />
          <p>{query ? t('documents.datasets.noResults') : t('documents.datasets.empty')}</p>
        </div>
      ) : (
        <div className="documents-dataset-grid">
          {datasets.data.items.map((dataset) => (
            <article key={dataset.dataset_id} className="documents-dataset-card">
              <div className="documents-dataset-card-header">
                <Folder className="h-5 w-5" aria-hidden="true" />
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="h-9 w-9"
                      aria-label={t('documents.datasets.actionsLabel', { name: dataset.name })}
                    >
                      <MoreHorizontal className="h-4 w-4" aria-hidden="true" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onSelect={() => setEditing(dataset)}>
                      {t('documents.actions.rename')}
                    </DropdownMenuItem>
                    <DropdownMenuItem variant="destructive" onSelect={() => setDeleting(dataset)}>
                      {t('documents.actions.delete')}
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
              <button
                type="button"
                className="documents-dataset-open"
                aria-label={t('documents.datasets.openLabel', { name: dataset.name })}
                onClick={() => onOpenDataset(dataset)}
              >
                <span className="documents-dataset-name">{dataset.name}</span>
                {dataset.description && <span className="documents-dataset-description">{dataset.description}</span>}
                <span className="documents-dataset-meta">
                  <span>{t('documents.datasets.documentCount', { count: dataset.document_count })}</span>
                  {dataset.updated_at && <span>{relativeTime(dataset.updated_at)}</span>}
                </span>
              </button>
            </article>
          ))}
        </div>
      )}

      <Pagination
        page={page}
        pageSize={PAGE_SIZE}
        total={datasets.data?.total ?? 0}
        onPageChange={onPageChange}
      />

      <DatasetDialog dataset={editing} open={Boolean(editing)} onOpenChange={(open) => !open && setEditing(undefined)} />
      <ConfirmDialog
        open={Boolean(deleting)}
        onOpenChange={(open) => !open && setDeleting(undefined)}
        title={t('documents.datasets.deleteTitle')}
        message={t('documents.datasets.deleteMessage', { name: deleting?.name ?? '' })}
        confirmLabel={t('documents.actions.delete')}
        onConfirm={removeDataset}
      />
    </div>
  );
}
