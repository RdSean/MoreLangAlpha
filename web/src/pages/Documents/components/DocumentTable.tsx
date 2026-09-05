import { useState } from 'react';
import { FileText, MoreHorizontal } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import ConfirmDialog from '@/components/ui/ConfirmDialog';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import { useToast } from '@/components/ui/use-toast';
import { relativeTime } from '@/lib/format';
import { useDocumentDatasets, useDocuments, useDocumentMutations, useDocumentTags } from '../hooks';
import type { DocumentSummary, ParseJobStatus, PdfClassification } from '../types';
import DocumentFilterBar from './DocumentFilters';
import Pagination from './Pagination';

const PAGE_SIZE = 20;

export interface DocumentTableFilters {
  query: string;
  datasetId: string;
  tagIds: string[];
  mediaType: string;
  classification: PdfClassification | '';
  parseStatus: ParseJobStatus | '';
}

interface DocumentTableProps {
  datasetId?: string;
  filters: DocumentTableFilters;
  page: number;
  onFiltersChange: (filters: DocumentTableFilters, resetPage: boolean) => void;
  onPageChange: (page: number) => void;
  onOpenDocument: (document: DocumentSummary) => void;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB'];
  let value = bytes / 1024;
  let unit = units[0];
  for (let index = 1; value >= 1024 && index < units.length; index += 1) {
    value /= 1024;
    unit = units[index];
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${unit}`;
}

export default function DocumentTable({
  datasetId,
  filters,
  page,
  onFiltersChange,
  onPageChange,
  onOpenDocument,
}: DocumentTableProps) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const documents = useDocuments({
    query: filters.query || undefined,
    dataset_id: datasetId || filters.datasetId || undefined,
    tag_ids: filters.tagIds.length ? filters.tagIds : undefined,
    media_type: filters.mediaType || undefined,
    classification: filters.classification || undefined,
    parse_status: filters.parseStatus || undefined,
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  });
  const datasets = useDocumentDatasets({ limit: 100, offset: 0 });
  const tags = useDocumentTags();
  const mutations = useDocumentMutations();
  const [editing, setEditing] = useState<DocumentSummary>();
  const [filename, setFilename] = useState('');
  const [deleting, setDeleting] = useState<DocumentSummary>();

  const startRename = (document: DocumentSummary) => {
    setFilename(document.original_filename);
    setEditing(document);
  };

  const rename = async () => {
    if (!editing || !filename.trim()) return;
    try {
      await mutations.updateDocument.mutateAsync({
        documentId: editing.document_id,
        original_filename: filename.trim(),
      });
      setEditing(undefined);
    } catch {
      toast({ variant: 'destructive', description: t('documents.table.renameFailed') });
    }
  };

  const remove = async () => {
    if (!deleting) return;
    try {
      await mutations.deleteDocument.mutateAsync(deleting.document_id);
      setDeleting(undefined);
    } catch {
      toast({ variant: 'destructive', description: t('documents.table.deleteFailed') });
    }
  };

  return (
    <div className="documents-collection-view">
      <DocumentFilterBar
        filters={filters}
        datasets={datasets.data?.items ?? []}
        tags={tags.data ?? []}
        fixedDatasetId={datasetId}
        onChange={onFiltersChange}
      />

      {documents.isLoading ? (
        <div className="documents-table-loading" role="status">{t('documents.table.loading')}</div>
      ) : documents.isError ? (
        <div className="documents-state" role="alert">
          <p>{t('documents.table.loadFailed')}</p>
          <Button type="button" variant="outline" size="sm" onClick={() => void documents.refetch()}>
            {t('documents.actions.retry')}
          </Button>
        </div>
      ) : !documents.data?.items.length ? (
        <div className="documents-state">
          <FileText className="h-6 w-6" aria-hidden="true" />
          <p>{t('documents.table.empty')}</p>
        </div>
      ) : (
        <div className="documents-table-wrap">
          <table className="documents-table" aria-label={t('documents.table.label')}>
            <thead>
              <tr>
                <th scope="col">{t('documents.table.columns.name')}</th>
                <th scope="col">{t('documents.table.columns.datasets')}</th>
                <th scope="col">{t('documents.table.columns.tags')}</th>
                <th scope="col">{t('documents.table.columns.format')}</th>
                <th scope="col">{t('documents.table.columns.size')}</th>
                <th scope="col">{t('documents.table.columns.status')}</th>
                <th scope="col">{t('documents.table.columns.updated')}</th>
                <th scope="col"><span className="sr-only">{t('documents.table.columns.actions')}</span></th>
              </tr>
            </thead>
            <tbody>
              {documents.data.items.map((document) => (
                <tr key={document.document_id}>
                  <td className="documents-table-name-cell">
                    <button
                      type="button"
                      className="documents-table-open"
                      title={document.original_filename}
                      aria-label={t('documents.table.openLabel', { name: document.original_filename })}
                      onClick={() => onOpenDocument(document)}
                    >
                      <FileText className="h-4 w-4" aria-hidden="true" />
                      <span>{document.original_filename}</span>
                    </button>
                  </td>
                  <td><div className="documents-cell-items">{document.datasets.map((item) => <span key={item.dataset_id}>{item.name}</span>)}</div></td>
                  <td><div className="documents-cell-items">{document.tags.map((item) => <span key={item.tag_id}>{item.name}</span>)}</div></td>
                  <td className="documents-data-cell">{document.document_format.toUpperCase()}</td>
                  <td className="documents-data-cell">{formatBytes(document.source_size_bytes)}</td>
                  <td>
                    <span className={`documents-status documents-status--${document.parse_status ?? 'none'}`}>
                      {t(`documents.status.${document.parse_status ?? 'none'}`)}
                    </span>
                  </td>
                  <td className="documents-data-cell">{relativeTime(document.updated_at)}</td>
                  <td className="documents-table-actions">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="h-9 w-9"
                          aria-label={t('documents.table.actionsLabel', { name: document.original_filename })}
                        >
                          <MoreHorizontal className="h-4 w-4" aria-hidden="true" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onSelect={() => onOpenDocument(document)}>{t('documents.actions.open')}</DropdownMenuItem>
                        <DropdownMenuItem onSelect={() => startRename(document)}>{t('documents.actions.rename')}</DropdownMenuItem>
                        <DropdownMenuItem variant="destructive" onSelect={() => setDeleting(document)}>{t('documents.actions.delete')}</DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Pagination
        page={page}
        pageSize={PAGE_SIZE}
        total={documents.data?.total ?? 0}
        onPageChange={onPageChange}
      />

      <Dialog open={Boolean(editing)} onOpenChange={(open) => !open && setEditing(undefined)}>
        <DialogContent variant="centered" className="max-w-md">
          <DialogHeader><DialogTitle className="title-font">{t('documents.table.renameTitle')}</DialogTitle></DialogHeader>
          <form
            className="grid gap-4"
            onSubmit={(event) => {
              event.preventDefault();
              void rename();
            }}
          >
            <label className="grid gap-1.5 text-sm font-medium" htmlFor="document-filename">
              {t('documents.table.filename')}
              <Input id="document-filename" value={filename} maxLength={512} autoFocus required onChange={(event) => setFilename(event.target.value)} />
            </label>
            <DialogFooter>
              <Button type="submit" disabled={!filename.trim() || mutations.updateDocument.isPending}>
                {mutations.updateDocument.isPending ? t('documents.actions.saving') : t('documents.actions.save')}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={Boolean(deleting)}
        onOpenChange={(open) => !open && setDeleting(undefined)}
        title={t('documents.table.deleteTitle')}
        message={t('documents.table.deleteMessage', { name: deleting?.original_filename ?? '' })}
        confirmLabel={t('documents.actions.delete')}
        onConfirm={remove}
      />
    </div>
  );
}
