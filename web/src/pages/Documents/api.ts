import { api } from '@/api/client';
import type {
  Artifact,
  DocumentUsage,
  UsageRange,
  CreateParseJobInput,
  CreateParseJobResult,
  DatasetFilters,
  DatasetSummary,
  DocumentFilters,
  DocumentSummary,
  InspectionOutcome,
  Paginated,
  ParseJob,
  ParserOption,
  Tag,
} from './types';

export async function createDataset(input: { name: string; description?: string | null }): Promise<DatasetSummary> {
  const { data } = await api.post<DatasetSummary>('/api/v1/document-datasets', input);
  return data;
}

export async function listDatasets(filters: DatasetFilters = {}): Promise<Paginated<DatasetSummary>> {
  const { data } = await api.get<Paginated<DatasetSummary>>('/api/v1/document-datasets', { params: filters });
  return data;
}

export async function getDataset(datasetId: string): Promise<DatasetSummary> {
  const { data } = await api.get<DatasetSummary>(`/api/v1/document-datasets/${datasetId}`);
  return data;
}

export async function updateDataset(datasetId: string, input: { name: string; description?: string | null }): Promise<DatasetSummary> {
  const { data } = await api.patch<DatasetSummary>(`/api/v1/document-datasets/${datasetId}`, input);
  return data;
}

export async function deleteDataset(datasetId: string): Promise<void> {
  await api.delete(`/api/v1/document-datasets/${datasetId}`);
}

export async function listTags(): Promise<Tag[]> {
  const { data } = await api.get<Tag[]>('/api/v1/document-tags');
  return data;
}

export async function createTag(name: string): Promise<Tag> {
  const { data } = await api.post<Tag>('/api/v1/document-tags', { name });
  return data;
}

export async function deleteTag(tagId: string): Promise<void> {
  await api.delete(`/api/v1/document-tags/${tagId}`);
}

export async function uploadDocument(
  file: File,
  selections: { datasetIds?: string[]; tagIds?: string[] } = {},
  onProgress?: (percentage: number) => void,
): Promise<DocumentSummary> {
  const body = new FormData();
  body.append('file', file);
  for (const datasetId of selections.datasetIds ?? []) body.append('dataset_ids', datasetId);
  for (const tagId of selections.tagIds ?? []) body.append('tag_ids', tagId);
  const { data } = await api.post<DocumentSummary>('/api/v1/documents', body, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: onProgress
      ? ({ loaded, total }) => {
          if (total) onProgress(Math.min(100, Math.round((loaded / total) * 100)));
        }
      : undefined,
  });
  return data;
}

export async function listDocuments(filters: DocumentFilters = {}): Promise<Paginated<DocumentSummary>> {
  const { data } = await api.get<Paginated<DocumentSummary>>('/api/v1/documents', {
    params: filters,
    paramsSerializer: { indexes: null },
  });
  return data;
}

export async function getDocument(documentId: string): Promise<DocumentSummary> {
  const { data } = await api.get<DocumentSummary>(`/api/v1/documents/${documentId}`);
  return data;
}

export async function updateDocument(
  documentId: string,
  input: { original_filename: string; dataset_ids?: string[]; tag_ids?: string[] },
): Promise<DocumentSummary> {
  const { data } = await api.patch<DocumentSummary>(`/api/v1/documents/${documentId}`, input);
  return data;
}

export async function deleteDocument(documentId: string): Promise<void> {
  await api.delete(`/api/v1/documents/${documentId}`);
}

export async function inspectDocument(documentId: string): Promise<InspectionOutcome> {
  const { data } = await api.post<InspectionOutcome>(`/api/v1/documents/${documentId}/inspections`);
  return data;
}

export async function getParseOptions(documentId: string, inspectionId?: string): Promise<ParserOption[]> {
  const { data } = await api.get<{ items: ParserOption[] }>(`/api/v1/documents/${documentId}/parse-options`, {
    params: inspectionId ? { inspection_id: inspectionId } : undefined,
  });
  return data.items;
}

export async function createDocumentParseJob(
  documentId: string,
  input: CreateParseJobInput,
): Promise<CreateParseJobResult> {
  const response = await api.post<ParseJob>(`/api/v1/documents/${documentId}/parse-jobs`, {
    ...input,
    mode: input.mode ?? 'async',
    options: input.options ?? {},
  });
  return { job: response.data, status: response.status as 200 | 202 };
}

export async function listDocumentJobs(documentId: string, limit = 50, offset = 0): Promise<ParseJob[]> {
  const { data } = await api.get<{ items: ParseJob[] }>(`/api/v1/documents/${documentId}/parse-jobs`, {
    params: { limit, offset },
  });
  return data.items;
}

export async function getDocumentJob(jobId: string): Promise<ParseJob> {
  const { data } = await api.get<ParseJob>(`/api/v1/document-jobs/${jobId}`);
  return data;
}

export async function cancelDocumentJob(jobId: string): Promise<ParseJob> {
  const { data } = await api.post<ParseJob>(`/api/v1/document-jobs/${jobId}/cancel`);
  return data;
}

export async function listDocumentArtifacts(documentId: string, producerJobId?: string): Promise<Artifact[]> {
  const { data } = await api.get<{ items: Artifact[] }>(`/api/v1/documents/${documentId}/artifacts`, {
    params: producerJobId ? { producer_job_id: producerJobId } : undefined,
  });
  return data.items;
}

export function artifactDownloadUrl(artifactId: string): string {
  return `${api.defaults.baseURL ?? ''}/api/v1/document-artifacts/${encodeURIComponent(artifactId)}/download`;
}

export function documentSourceUrl(documentId: string): string {
  return `${api.defaults.baseURL ?? ''}/api/v1/documents/${encodeURIComponent(documentId)}/source`;
}

export async function fetchArtifactText(artifactId: string): Promise<string> {
  const response = await fetch(artifactDownloadUrl(artifactId), { credentials: 'include' });
  if (!response.ok) throw new Error('Artifact preview is unavailable');
  return response.text();
}

const TERMINAL_STATUSES = new Set<ParseJob['status']>(['completed', 'failed', 'cancelled']);

export interface WatchDocumentJobOptions {
  onSnapshot: (snapshot: ParseJob) => void;
  onError?: (error: unknown) => void;
  signal?: AbortSignal;
  maxSseErrors?: number;
  reconnectDelayMs?: number;
  pollIntervalMs?: number;
}

export async function watchDocumentJob(jobId: string, options: WatchDocumentJobOptions): Promise<void> {
  const maxSseErrors = options.maxSseErrors ?? 3;
  const reconnectDelayMs = options.reconnectDelayMs ?? 1_000;
  const pollIntervalMs = options.pollIntervalMs ?? 2_000;
  let lastVersion = -1;
  let errors = 0;

  while (!options.signal?.aborted && errors < maxSseErrors) {
    try {
      const params = new URLSearchParams({ after_status_version: String(lastVersion) });
      const response = await fetch(
        `${api.defaults.baseURL ?? ''}/api/v1/document-jobs/${encodeURIComponent(jobId)}/events?${params}`,
        { headers: { Accept: 'text/event-stream' }, credentials: 'include', signal: options.signal },
      );
      if (!response.ok || !response.body || !response.headers.get('Content-Type')?.includes('text/event-stream')) {
        throw new Error('Document job event stream is unavailable');
      }
      const consumed = await consumeSnapshots(response.body, jobId, lastVersion, options.onSnapshot, options.signal);
      lastVersion = consumed.lastVersion;
      if (consumed.terminal) return;
      errors += 1;
    } catch (error) {
      if (isAbort(error) || options.signal?.aborted) return;
      errors += 1;
      if (errors >= maxSseErrors) options.onError?.(error);
    }
    if (errors < maxSseErrors) await delay(reconnectDelayMs, options.signal);
  }

  while (!options.signal?.aborted) {
    try {
      const snapshot = await getDocumentJob(jobId);
      if (snapshot.status_version > lastVersion) {
        lastVersion = snapshot.status_version;
        options.onSnapshot(snapshot);
      }
      if (TERMINAL_STATUSES.has(snapshot.status)) return;
    } catch (error) {
      if (isAbort(error) || options.signal?.aborted) return;
      options.onError?.(error);
    }
    await delay(pollIntervalMs, options.signal);
  }
}

async function consumeSnapshots(
  body: ReadableStream<Uint8Array>,
  jobId: string,
  initialVersion: number,
  onSnapshot: (snapshot: ParseJob) => void,
  signal?: AbortSignal,
): Promise<{ lastVersion: number; terminal: boolean }> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let lastVersion = initialVersion;
  try {
    while (!signal?.aborted) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split('\n\n');
      buffer = blocks.pop() ?? '';
      for (const block of blocks) {
        const snapshot = parseSnapshotBlock(block, jobId);
        if (!snapshot || snapshot.status_version <= lastVersion) continue;
        lastVersion = snapshot.status_version;
        onSnapshot(snapshot);
        if (TERMINAL_STATUSES.has(snapshot.status)) return { lastVersion, terminal: true };
      }
    }
    return { lastVersion, terminal: false };
  } finally {
    try { await reader.cancel(); } catch { /* stream is already closed */ }
  }
}

function parseSnapshotBlock(block: string, jobId: string): ParseJob | null {
  let event = '';
  const data: string[] = [];
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim();
    else if (line.startsWith('data:')) data.push(line.slice(5).trim());
  }
  if (event !== 'snapshot' || data.length === 0) return null;
  try {
    const value = JSON.parse(data.join('\n')) as Partial<ParseJob>;
    if (value.job_id !== jobId || typeof value.status_version !== 'number' || typeof value.status !== 'string') return null;
    return value as ParseJob;
  } catch {
    return null;
  }
}

function delay(milliseconds: number, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) return Promise.resolve();
  return new Promise((resolve) => {
    const timer = window.setTimeout(resolve, milliseconds);
    signal?.addEventListener('abort', () => {
      window.clearTimeout(timer);
      resolve();
    }, { once: true });
  });
}

function isAbort(error: unknown): boolean {
  return typeof error === 'object' && error !== null && 'name' in error && error.name === 'AbortError';
}

/**
 * What this account's document conversions have cost, by day.
 *
 * Totalled by the server: summing the buckets here would give two
 * implementations of "total spend", and the header would eventually disagree
 * with the chart.
 */
export async function getDocumentUsage(range: UsageRange): Promise<DocumentUsage> {
  const { data } = await api.get<DocumentUsage>('/api/v1/document-usage', {
    params: { range },
  });
  return data;
}
