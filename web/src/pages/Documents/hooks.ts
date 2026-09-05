import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import * as documentsApi from './api';
import type { CreateParseJobInput, DatasetFilters, DocumentFilters } from './types';

export function useDocumentDatasets(filters: DatasetFilters = {}) {
  return useQuery({
    queryKey: queryKeys.documents.datasetList(filters),
    queryFn: () => documentsApi.listDatasets(filters),
  });
}

export function useDocumentDataset(datasetId?: string) {
  return useQuery({
    queryKey: queryKeys.documents.dataset(datasetId ?? ''),
    queryFn: () => documentsApi.getDataset(datasetId ?? ''),
    enabled: Boolean(datasetId),
  });
}

export function useDocuments(filters: DocumentFilters = {}) {
  return useQuery({
    queryKey: queryKeys.documents.list(filters),
    queryFn: () => documentsApi.listDocuments(filters),
  });
}

export function useDocument(documentId?: string) {
  return useQuery({
    queryKey: queryKeys.documents.detail(documentId ?? ''),
    queryFn: () => documentsApi.getDocument(documentId ?? ''),
    enabled: Boolean(documentId),
  });
}

export function useDocumentTags() {
  return useQuery({
    queryKey: queryKeys.documents.tags(),
    queryFn: documentsApi.listTags,
  });
}

export function useDocumentParseOptions(documentId?: string, inspectionId?: string) {
  return useQuery({
    queryKey: queryKeys.documents.parseOptions(documentId ?? '', inspectionId),
    queryFn: () => documentsApi.getParseOptions(documentId ?? '', inspectionId),
    enabled: Boolean(documentId),
  });
}

export function useDocumentJobs(documentId?: string) {
  return useQuery({
    queryKey: queryKeys.documents.jobs(documentId),
    queryFn: () => documentsApi.listDocumentJobs(documentId ?? ''),
    enabled: Boolean(documentId),
  });
}

export function useDocumentJob(jobId?: string) {
  return useQuery({
    queryKey: queryKeys.documents.job(jobId ?? ''),
    queryFn: () => documentsApi.getDocumentJob(jobId ?? ''),
    enabled: Boolean(jobId),
  });
}

export function useDocumentArtifacts(documentId?: string, jobId?: string) {
  return useQuery({
    queryKey: queryKeys.documents.artifacts(documentId ?? '', jobId),
    queryFn: () => documentsApi.listDocumentArtifacts(documentId ?? '', jobId),
    enabled: Boolean(documentId),
  });
}

export function useDocumentMutations() {
  const client = useQueryClient();
  const invalidateLists = () => client.invalidateQueries({ queryKey: queryKeys.documents.lists() });
  const invalidateDatasets = () => client.invalidateQueries({ queryKey: queryKeys.documents.datasets() });
  const invalidateTags = () => client.invalidateQueries({ queryKey: queryKeys.documents.tags() });

  return {
    createDataset: useMutation({
      mutationFn: documentsApi.createDataset,
      onSuccess: invalidateDatasets,
    }),
    updateDataset: useMutation({
      mutationFn: ({ datasetId, ...input }: { datasetId: string; name: string; description?: string | null }) =>
        documentsApi.updateDataset(datasetId, input),
      onSuccess: invalidateDatasets,
    }),
    deleteDataset: useMutation({
      mutationFn: documentsApi.deleteDataset,
      onSuccess: async () => { await invalidateDatasets(); await invalidateLists(); },
    }),
    createTag: useMutation({ mutationFn: documentsApi.createTag, onSuccess: invalidateTags }),
    deleteTag: useMutation({ mutationFn: documentsApi.deleteTag, onSuccess: invalidateTags }),
    uploadDocument: useMutation({
      mutationFn: ({ file, datasetIds, tagIds }: { file: File; datasetIds?: string[]; tagIds?: string[] }) =>
        documentsApi.uploadDocument(file, { datasetIds, tagIds }),
      onSuccess: async () => { await invalidateLists(); await invalidateDatasets(); await invalidateTags(); },
    }),
    inspectDocument: useMutation({
      mutationFn: documentsApi.inspectDocument,
      onSuccess: (_outcome, documentId) => client.invalidateQueries({ queryKey: queryKeys.documents.inspections(documentId) }),
    }),
    updateDocument: useMutation({
      mutationFn: ({ documentId, ...input }: {
        documentId: string;
        original_filename: string;
        dataset_ids?: string[];
        tag_ids?: string[];
      }) => documentsApi.updateDocument(documentId, input),
      onSuccess: async (document) => {
        await client.invalidateQueries({ queryKey: queryKeys.documents.detail(document.document_id) });
        await invalidateLists();
      },
    }),
    createParseJob: useMutation({
      mutationFn: ({ documentId, input }: { documentId: string; input: CreateParseJobInput }) =>
        documentsApi.createDocumentParseJob(documentId, input),
      onSuccess: (_result, { documentId }) => client.invalidateQueries({ queryKey: queryKeys.documents.jobs(documentId) }),
    }),
    cancelJob: useMutation({
      mutationFn: documentsApi.cancelDocumentJob,
      onSuccess: (job) => client.invalidateQueries({ queryKey: queryKeys.documents.job(job.job_id) }),
    }),
    deleteDocument: useMutation({
      mutationFn: documentsApi.deleteDocument,
      onSuccess: async () => { await invalidateLists(); await invalidateDatasets(); await invalidateTags(); },
    }),
  };
}
