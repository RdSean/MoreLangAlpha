export type EducationTaskStatus = 'open' | 'completed' | 'cancelled';

export interface EducationTask {
  task_id: string;
  task_rule_id: string;
  household_id: string;
  assigned_student_id: string;
  occurrence_date: string;
  due_at: string;
  title: string;
  description: string;
  subject_code?: string | null;
  type_code?: string | null;
  practice_source_code?: string | null;
  grade_code?: string | null;
  status: EducationTaskStatus;
  completed_at?: string | null;
  created_at?: string;
  latest_review_decision?: 'feedback' | 'revision_requested';
  latest_feedback_text?: string;
}

export interface EducationMember {
  user_id: string;
  name: string;
  role: 'parent' | 'student';
  grade_code?: string | null;
}

export interface CreateEducationTaskInput {
  idempotency_key: string;
  assigned_student_id: string;
  title: string;
  description: string;
  due_at: string;
  subject_code: string;
  type_code: string;
  practice_source_code?: string | null;
  frequency: 'once' | 'daily' | 'weekdays' | 'weekly';
  weekdays?: number[] | null;
  material_asset_ids: string[];
}

export interface SubmitEducationTaskInput {
  submission_text: string;
  idempotency_key: string;
  asset_ids: string[];
}

export interface EducationHomeworkType {
  code: string;
  name: string;
  sort_order: number;
}

export interface EducationSubjectDictionary {
  code: string;
  name: string;
  color: string;
  sort_order: number;
  homework_types: EducationHomeworkType[];
}

export interface EducationHomeworkDictionaries {
  timezone: string;
  subjects: EducationSubjectDictionary[];
  grade_levels: Array<{ code: string; name: string; stage: string; sort_order: number }>;
  practice_sources: Array<{ code: string; name: string; sort_order: number }>;
}

export interface EducationAsset {
  asset_id: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  created_at?: string;
}

export interface EducationTaskAsset extends EducationAsset {
  download_endpoint: string;
}

export interface EducationTaskSubmission {
  submission_id: string;
  task_id: string;
  sequence: number;
  submission_text: string;
  submitted_by_user_id?: string | null;
  idempotency_key?: string | null;
  submission_kind?: 'check_in' | 'revision' | null;
  created_at?: string | null;
}

export interface EducationTaskReview {
  review_id: string;
  submission_id: string;
  decision: 'feedback' | 'revision_requested';
  feedback_text: string;
  reviewed_by_user_id?: string | null;
  created_at?: string | null;
}

export interface EducationTaskSubmissionDetail extends EducationTaskSubmission {
  assets: EducationTaskAsset[];
  reviews: EducationTaskReview[];
}

export interface EducationTaskDetail extends EducationTask {
  parent_materials: EducationTaskAsset[];
  submissions: EducationTaskSubmissionDetail[];
}

export interface EducationCalendarTask extends EducationTask {
  subject_color?: string | null;
  is_completed: boolean;
  is_overdue: boolean;
}

export interface EducationTaskCalendarDay {
  date: string;
  task_count: number;
  completed_count: number;
  overdue_count: number;
  tasks: EducationCalendarTask[];
}

export interface EducationTaskCalendar {
  student_id?: string | null;
  start_date: string;
  end_date: string;
  days: EducationTaskCalendarDay[];
  stats: {
    today_count: number;
    week_count: number;
    overdue_count: number;
    completed_count: number;
  };
}

export interface EducationTaskCalendarRequest {
  start_date: string;
  end_date: string;
  student_id?: string;
}

export type BookJobKind = 'structure' | 'materials';
export type BookMaterialDepth = 'summary' | 'lesson' | 'deep';
export type BookJobStatus =
  | 'queued'
  | 'running'
  | 'succeeded'
  | 'partially_succeeded'
  | 'failed'
  | 'cancelled';
export type BookJobItemStatus =
  | 'queued'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'cancelled'
  | 'not_run';
export type BookJobItemKind = 'structure' | 'material' | 'supplementary';
export type BookActivityStatus = 'available' | 'unavailable';
export type BookSourceStatus = 'pending' | 'preparing' | 'ready' | 'failed' | 'cancelled';
export type BookExecutionPhase = 'initial_queue' | 'source_freezing' | 'runtime_queue'
  | 'sandbox_preparation' | 'input_staging' | 'ptc_execution' | 'finalization';
export type BookTimingStatus = 'available' | 'partial' | 'unavailable';

export interface BookPreparationProgress {
  total_resources: number | null;
  verified_resources: number;
}

export interface BookPhaseTiming {
  phase: BookExecutionPhase;
  status: BookTimingStatus;
  started_at: string | null;
  ended_at: string | null;
  measured_ms: number | null;
  segment_count: number;
}

export interface BookAttemptTiming {
  attempt: number;
  request_round: number;
  status: BookTimingStatus;
  queued_at: string | null;
  claimed_at: string | null;
  terminal_at: string | null;
  total_ms: number | null;
  phases: BookPhaseTiming[];
}

export interface BookAttemptStatistics {
  item_id: string;
  kind: BookJobItemKind;
  status: BookJobItemStatus | 'interrupted';
  knowledge_point_title: string | null;
  timing: BookAttemptTiming;
}

export interface BookJobStatistics {
  job_id: string;
  request_round: number;
  server_now: string;
  status: BookTimingStatus;
  round_total_ms: number | null;
  material_sample_count: number;
  material_median_ms: number | null;
  material_longest_ms: number | null;
  supplementary: BookAttemptStatistics[];
  attempts: BookAttemptStatistics[];
  next_cursor: string | null;
}

export interface BookJobItem {
  item_id: string;
  kind: BookJobItemKind;
  position: number;
  knowledge_point_id: string | null;
  skill_kp_id: string | null;
  knowledge_point_title?: string | null;
  status: BookJobItemStatus;
  attempt: number;
  safe_error: string | null;
  started_at: string | null;
  finished_at: string | null;
  execution_phase?: BookExecutionPhase | null;
  queued_at?: string | null;
  preparation_progress?: BookPreparationProgress | null;
  timing_summary?: BookAttemptTiming | null;
}

export interface BookJobSummary {
  job_id: string;
  kind: BookJobKind;
  status: BookJobStatus;
  total_items: number;
  succeeded_items: number;
  failed_items: number;
  cancelled_items: number;
  not_run_items: number;
  high_water_seq: number;
  activity_status: BookActivityStatus;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  safe_error: string | null;
  request_round?: number;
  round_accepted_at?: string | null;
  server_now?: string | null;
}

export interface BookJob extends BookJobSummary {
  token_usage?: { status: 'available' | 'partial'; input_tokens: number; output_tokens: number; total_tokens: number; recorded_calls: number } | null;
  textbook_id: string;
  depth: BookMaterialDepth | null;
  requirements: string | null;
  replace_existing: boolean;
  include_supplementary: boolean;
  items: BookJobItem[];
  material_progress?: { completed: number; total: number } | null;
}

export interface BookActivityEvent {
  seq: number;
  job_id: string;
  item_id: string | null;
  kind: string;
  status: string;
  message: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface BookActivityPage {
  job_id: string;
  status: BookJobStatus;
  events: BookActivityEvent[];
  high_water_seq: number;
  activity_status: BookActivityStatus;
  cursor_expired: boolean;
  has_more: boolean;
}

export type BookStructureStatus = 'queued' | 'running' | 'ready' | 'failed';

export interface BookMaterialCounts {
  total: number;
  ready: number;
}

export interface FrozenBookSource {
  page_count?: number | null;
  document_id: string;
  parse_job_id: string;
  primary_artifact_id: string;
  filename: string;
  media_type: string;
  parser_id: string;
  parser_name: string;
  completed_at: string;
  content_sha256: string;
  size_bytes: number;
  image_count: number;
  frozen_at: string | null;
}

export type BookSourceCandidate = Omit<FrozenBookSource, 'frozen_at'>;

export interface CreateManagedTextbookInput {
  parse_job_id: string;
  primary_artifact_id: string;
  title: string;
  idempotency_key: string;
}

export interface CreateManagedTextbookResponse {
  textbook_id: string;
  job_id: string;
  acceptance: 'accepted_new' | 'reused';
}

export interface ManagedTextbookSummary {
  textbook_id: string;
  title: string;
  structure_status: BookStructureStatus;
  materials: BookMaterialCounts;
  current_job: BookJobSummary | null;
  updated_at: string;
  source_status?: BookSourceStatus;
  cover_available?: boolean;
  cover_updated_at?: string | null;
}

export interface TextbookWorkbench extends ManagedTextbookSummary {
  source: FrozenBookSource | null;
  source_status: BookSourceStatus;
  selected_source?: BookSourceCandidate | null;
  source_frozen_at?: string | null;
  current_structure_id: string | null;
  recent_job: BookJobSummary | null;
  assigned_student_count: number;
}

export interface BookAssignment {
  textbook_id: string;
  student_user_id: string;
  assigned_at: string;
}

export interface BookAssignmentRequest {
  student_user_ids: string[];
}

export interface BookStructureAnchor {
  start_line: number;
  end_line: number;
}

export interface BookStructureNode {
  id: string;
  title: string;
  anchor: BookStructureAnchor;
  page_range?: { start: number | null; end?: number | null; label?: string | null; source?: string } | null;
  children?: BookStructureNode[];
  level?: number;
  number?: string | null;
  type?: string;
  summary?: string | null;
  content_file?: string | null;
  [key: string]: unknown;
}

export interface BookStructureDocument {
  schema_version: string;
  book: Record<string, unknown> & { title: string };
  source: Record<string, unknown> & { path: string; total_lines: number };
  nodes: BookStructureNode[];
  coverage: Record<string, unknown>;
  level_names?: string[];
  [key: string]: unknown;
}

export interface KnowledgePointProjection {
  knowledge_point_id: string;
  skill_kp_id: string;
  position: number;
  title: string;
  unit_skill_node_id: string | null;
  node_skill_ids: string[];
  start_line: number;
  end_line: number;
  content_file: string | null;
  material_available: boolean;
}

export interface BookStructure {
  textbook_id: string;
  structure_id: string;
  schema_version: string;
  structure: BookStructureDocument;
  knowledge_points: KnowledgePointProjection[];
  warnings: string[];
}

export interface BookSourceSlice {
  textbook_id: string;
  start_line: number;
  end_line: number;
  total_lines: number;
  markdown: string;
}

export interface KnowledgePointMaterial {
  textbook_id: string;
  knowledge_point_id: string;
  skill_kp_id: string;
  material_available: boolean;
  markdown: string | null;
  generated_at: string | null;
  depth: BookMaterialDepth | null;
  requirements: string | null;
  content_sha256: string | null;
}

export interface CreateBookJobInput {
  kind: BookJobKind;
  knowledge_point_ids: string[];
  depth: BookMaterialDepth;
  requirements: string | null;
  replace_existing: boolean;
  include_supplementary: boolean;
  idempotency_key: string;
}

export interface StudentTextbookStructure extends BookStructure {
  assignment_id: string;
  textbook_title: string;
}

export interface StudentKnowledgePointMaterial extends KnowledgePointMaterial {
  assignment_id: string;
}

export type LearningItemKind = 'question' | 'highlight' | 'note' | 'summary';

export interface LearningItem {
  item_id: string;
  assignment_id: string;
  skill_node_id?: string | null;
  knowledge_point_id?: string | null;
  kind: LearningItemKind;
  content: string;
  source_anchor?: Record<string, unknown> | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface LearningAssignment {
  assignment_id: string;
  textbook_id: string;
  textbook_title: string;
  structure_id: string | null;
  knowledge_point_count: number;
  completed_knowledge_point_count: number;
  created_at?: string;
}

export interface LearningChatSpace {
  assignment_id: string;
  workspace_id: string;
  conversation_thread_id: string;
  created_at?: string;
}

export interface ParentLearningTranscript {
  assignment_id: string;
  student_user_id: string;
  textbook_title: string;
  conversation_thread_id: string | null;
  messages: Array<{
    role: 'user' | 'assistant';
    content: string;
    timestamp?: string | null;
  }>;
}
