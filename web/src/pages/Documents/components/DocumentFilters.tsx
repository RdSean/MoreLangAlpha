import { useEffect, useState } from 'react';
import { Filter, Search, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Select } from '@/components/ui/select';
import type { DatasetSummary, Tag } from '../types';
import type { DocumentTableFilters } from './DocumentTable';

interface DocumentFiltersProps {
  filters: DocumentTableFilters;
  datasets: DatasetSummary[];
  tags: Tag[];
  fixedDatasetId?: string;
  onChange: (filters: DocumentTableFilters, resetPage: boolean) => void;
}

export default function DocumentFilters({ filters, datasets, tags, fixedDatasetId, onChange }: DocumentFiltersProps) {
  const { t } = useTranslation();
  const [query, setQuery] = useState(filters.query);

  useEffect(() => setQuery(filters.query), [filters.query]);
  useEffect(() => {
    if (query === filters.query) return;
    const timer = window.setTimeout(() => onChange({ ...filters, query }, true), 300);
    return () => window.clearTimeout(timer);
  }, [filters, onChange, query]);

  const set = <K extends keyof DocumentTableFilters>(key: K, value: DocumentTableFilters[K]) => {
    onChange({ ...filters, [key]: value }, true);
  };
  const activeCount = [
    !fixedDatasetId && filters.datasetId,
    filters.tagIds.length > 0,
    filters.mediaType,
    filters.classification,
    filters.parseStatus,
  ].filter(Boolean).length;

  return (
    <div className="documents-filter-bar">
      <label className="documents-search-field documents-search-field--table">
        <span className="sr-only">{t('documents.table.searchLabel')}</span>
        <Search className="documents-search-icon" aria-hidden="true" />
        <Input
          type="search"
          value={query}
          placeholder={t('documents.table.searchPlaceholder')}
          aria-label={t('documents.table.searchLabel')}
          onChange={(event) => setQuery(event.target.value)}
        />
      </label>

      {!fixedDatasetId && (
        <Select
          className="documents-filter-select"
          value={filters.datasetId}
          aria-label={t('documents.filters.dataset')}
          onChange={(event) => set('datasetId', event.target.value)}
        >
          <option value="">{t('documents.filters.allDatasets')}</option>
          {datasets.map((dataset) => <option key={dataset.dataset_id} value={dataset.dataset_id}>{dataset.name}</option>)}
        </Select>
      )}

      <Popover>
        <PopoverTrigger asChild>
          <Button type="button" variant="outline" className="documents-filter-trigger">
            <Filter className="mr-2 h-4 w-4" aria-hidden="true" />
            {filters.tagIds.length
              ? t('documents.filters.selectedTags', { count: filters.tagIds.length })
              : t('documents.filters.tags')}
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-64 p-2">
          <div className="documents-tag-options" aria-label={t('documents.filters.tags')}>
            {tags.length === 0 ? (
              <p>{t('documents.filters.noTags')}</p>
            ) : tags.map((tag) => (
              <label key={tag.tag_id} className="documents-tag-option">
                <input
                  type="checkbox"
                  checked={filters.tagIds.includes(tag.tag_id)}
                  onChange={() => set(
                    'tagIds',
                    filters.tagIds.includes(tag.tag_id)
                      ? filters.tagIds.filter((id) => id !== tag.tag_id)
                      : [...filters.tagIds, tag.tag_id],
                  )}
                />
                <span>{tag.name}</span>
              </label>
            ))}
          </div>
        </PopoverContent>
      </Popover>

      <Select
        className="documents-filter-select"
        value={filters.mediaType}
        aria-label={t('documents.filters.format')}
        onChange={(event) => set('mediaType', event.target.value)}
      >
        <option value="">{t('documents.filters.allFormats')}</option>
        <option value="application/pdf">PDF</option>
      </Select>

      <Select
        className="documents-filter-select"
        value={filters.classification}
        aria-label={t('documents.filters.classification')}
        onChange={(event) => set('classification', event.target.value as DocumentTableFilters['classification'])}
      >
        <option value="">{t('documents.filters.allClassifications')}</option>
        <option value="text_based">{t('documents.classification.text_based')}</option>
        <option value="mixed">{t('documents.classification.mixed')}</option>
        <option value="scanned">{t('documents.classification.scanned')}</option>
        <option value="image_based">{t('documents.classification.image_based')}</option>
        <option value="unknown">{t('documents.classification.unknown')}</option>
      </Select>

      <Select
        className="documents-filter-select"
        value={filters.parseStatus}
        aria-label={t('documents.filters.status')}
        onChange={(event) => set('parseStatus', event.target.value as DocumentTableFilters['parseStatus'])}
      >
        <option value="">{t('documents.filters.allStatuses')}</option>
        <option value="queued">{t('documents.status.queued')}</option>
        <option value="running">{t('documents.status.running')}</option>
        <option value="completed">{t('documents.status.completed')}</option>
        <option value="failed">{t('documents.status.failed')}</option>
        <option value="cancelled">{t('documents.status.cancelled')}</option>
      </Select>

      {activeCount > 0 && (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => onChange({
            query: filters.query,
            datasetId: '',
            tagIds: [],
            mediaType: '',
            classification: '',
            parseStatus: '',
          }, true)}
        >
          <X className="mr-2 h-4 w-4" aria-hidden="true" />
          {t('documents.actions.clearFilters')}
        </Button>
      )}
    </div>
  );
}
