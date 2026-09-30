export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

export type PdfClassification = 'text_based' | 'mixed' | 'scanned' | 'image_based' | 'unknown';
export type ParseJobStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
export type ParseJobStage = 'queued' | 'preparing' | 'parsing' | 'storing' | 'completed' | 'failed' | 'cancelled';
export type ArtifactKind = 'primary_document' | 'embedded_image' | 'structured_data' | 'manifest';

export interface Paginated<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface DatasetSummary {
  dataset_id: string;
  name: string;
  description?: string | null;
  document_count: number;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface Tag {
  tag_id: string;
  name: string;
  document_count: number;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface DocumentSummary {
  document_id: string;
  original_filename: string;
  media_type: string;
  document_format: string;
  source_size_bytes: number;
  source_sha256: string;
  datasets: Array<Pick<DatasetSummary, 'dataset_id' | 'name'>>;
  tags: Array<Pick<Tag, 'tag_id' | 'name'>>;
  classification?: PdfClassification | null;
  parse_status?: ParseJobStatus | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export type DocumentStructureStatus =
  | 'queued'
  | 'running'
  | 'review'
  | 'accepted'
  | 'failed'
  | 'cancelled';

export interface DocumentTeachingUsage {
  document_id: string;
  producer_job_id: string;
  primary_artifact_id: string;
  textbook_id: string;
  textbook_title: string;
  content_version_id: string;
  content_version_sequence: number;
  artifact_position: number;
  structure_id?: string | null;
  structure_sequence?: number | null;
  structure_status?: DocumentStructureStatus | null;
  book_asset_prefix?: string | null;
  publication_id?: string | null;
  is_published: boolean;
  has_asset_manifest: boolean;
  created_at?: string | null;
}

export interface Inspection {
  inspection_id: string;
  document_id: string;
  inspector_id: string;
  inspector_name: string;
  inspector_version?: string | null;
  status: 'pending' | 'completed' | 'failed';
  detected_format?: string | null;
  classification?: PdfClassification | null;
  summary: Record<string, JsonValue>;
  details: Record<string, JsonValue>;
  error_code?: string | null;
  error_message?: string | null;
  created_at?: string | null;
  completed_at?: string | null;
}

export interface ParserOption {
  parser_id: string;
  display_name: string;
  version?: string | null;
  supported_formats: string[];
  supported_classifications: PdfClassification[];
  available: boolean;
  reason: string;
  warning?: string | null;
  recommended: boolean;
}

export interface InspectionOutcome {
  inspection: Inspection;
  parser_options: ParserOption[];
}

export type DatalabMode = 'fast' | 'balanced' | 'accurate';

/**
 * Advanced knobs for the hosted Datalab parser, sent as the parse job's
 * `parser_options`.
 *
 * Every field is optional and only present when the user moved it off its
 * default, so the server's defaults stay authoritative for anything untouched.
 * The server validates the same shape with a Pydantic model and ignores
 * unknown keys.
 */
export interface DatalabOptions {
  mode?: DatalabMode;
  paginate?: boolean;
  merge_cross_page?: boolean;
  keep_pageheader_in_output?: boolean;
  keep_pagefooter_in_output?: boolean;
  page_range?: string;
  max_pages?: number;
  skip_cache?: boolean;
  disable_image_extraction?: boolean;
  disable_image_captions?: boolean;
  token_efficient_markdown?: boolean;
  extract_links?: boolean;
  new_block_types?: boolean;
  add_block_ids?: boolean;
  extras?: string;
}

/**
 * Narrow the options to the wire shape.
 *
 * The create-job body takes `Record<string, JsonValue>`, which has no room for
 * `undefined`; every optional field here may be absent *or* explicitly
 * undefined. This drops the latter so what is sent is exactly the keys the user
 * touched.
 */
export function toParserOptions(options: DatalabOptions): Record<string, JsonValue> {
  return Object.fromEntries(
    Object.entries(options).filter(([, value]) => value !== undefined),
  ) as Record<string, JsonValue>;
}

export type UsageRange = '7d' | '14d' | '30d';

export interface DocumentUsageDay {
  day: string;
  pages: number;
  cost_cents: number;
  conversions: number;
}

export interface DocumentUsageTotals {
  pages: number;
  cost_cents: number;
  conversions: number;
}

/** What the account's document conversions have cost, by day. */
export interface DocumentUsage {
  range: UsageRange;
  totals: DocumentUsageTotals;
  days: DocumentUsageDay[];
}

export interface ParseJob {
  job_id: string;
  document_id: string;
  inspection_id: string;
  parser_id: string;
  parser_name: string;
  parser_version?: string | null;
  parser_options: Record<string, JsonValue>;
  request_mode: 'sync' | 'async';
  status: ParseJobStatus;
  stage: ParseJobStage;
  percentage: number;
  status_version: number;
  attempt_count: number;
  primary_artifact_id?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  cancellation_requested_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
}

export interface Artifact {
  artifact_id: string;
  document_id: string;
  producer_job_id: string;
  artifact_kind: ArtifactKind;
  format: string;
  media_type: string;
  schema_name?: string | null;
  schema_version?: string | null;
  relative_path: string;
  locator?: Record<string, JsonValue> | null;
  metadata?: Record<string, JsonValue> | null;
  created_at?: string | null;
}

export interface DatasetFilters {
  query?: string;
  limit?: number;
  offset?: number;
}

export interface DocumentFilters {
  query?: string;
  dataset_id?: string;
  tag_ids?: string[];
  media_type?: string;
  classification?: PdfClassification;
  parse_status?: ParseJobStatus;
  limit?: number;
  offset?: number;
}

export interface CreateParseJobInput {
  inspection_id: string;
  parser_id: string;
  mode?: 'sync' | 'async';
  options?: Record<string, JsonValue>;
}

export interface CreateParseJobResult {
  job: ParseJob;
  status: 200 | 202;
}
