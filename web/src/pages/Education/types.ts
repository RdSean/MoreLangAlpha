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

export type TextbookVersionStatus = 'draft' | 'processing' | 'review' | 'published' | 'failed';

export interface TextbookLibraryItem {
  textbook_id: string;
  household_id: string;
  title: string;
  slug: string;
  created_at?: string;
  latest_version_id?: string | null;
  latest_version_sequence?: number | null;
  latest_version_status?: TextbookVersionStatus | null;
  chapter_count: number;
  assignment_count: number;
}

export interface StructureSourceRef {
  source_id: string;
  start?: number | null;
  end?: number | null;
  quote?: string | null;
  heading_path?: string[];
}

export interface TextbookKnowledgePoint {
  knowledge_point_id: string;
  position: number;
  slug: string;
  title: string;
  summary: string;
  scope_slot?: 'reading_a' | 'reading_b' | null;
  source_refs: StructureSourceRef[];
  confidence: number;
  status: 'review' | 'accepted' | 'blocked';
  lesson_status?: 'review' | 'approved' | 'blocked' | null;
  lesson_revision_id?: string | null;
}

export interface TextbookStructureScope {
  slot: 'reading_a' | 'reading_b';
  title: string;
  summary: string;
  reading_skill: string;
  vocabulary_building: string;
  critical_thinking: string;
  source_id: string;
  line_start: number;
  line_end: number;
  char_start: number;
  char_end: number;
  verified: boolean;
}

export interface TextbookStructureUnit {
  unit_id: string;
  position: number;
  slug: string;
  title: string;
  summary: string;
  unit_type: 'teaching' | 'front_matter' | 'reference' | 'appendix';
  source_refs: StructureSourceRef[];
  confidence: number;
  status: 'review' | 'accepted' | 'blocked';
  scopes: TextbookStructureScope[];
  knowledge_points: TextbookKnowledgePoint[];
}

export interface TextbookStructure {
  structure_id: string;
  version_id: string;
  sequence: number;
  status: 'queued' | 'running' | 'review' | 'accepted' | 'failed' | 'cancelled';
  schema_version: string;
  processing_profile_id?: string | null;
  processing_profile_sha256: string;
  input_manifest_sha256: string;
  source_revision: string;
  created_at?: string | null;
  reviewed_at?: string | null;
  book_asset_prefix?: string | null;
  book_asset_manifest?: Record<string, unknown>;
  validation_warnings: string[];
  units: TextbookStructureUnit[];
  lesson_summary: {
    total: number;
    accepted: number;
    generated: number;
    approved: number;
  };
  latest_generation_job_id?: string | null;
  latest_generation_job?: StructureGenerationJobSummary | null;
}

export interface StructureGenerationJobSummary {
  generation_job_id: string;
  status: string;
  attempt_count: number;
  error_message?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  root_run_id?: string | null;
  started_at?: string | null;
  heartbeat_at?: string | null;
}

export interface StructureGenerationJob {
  generation_job_id: string;
  version_id: string;
  scope: 'structure' | 'lesson';
  structure_id?: string | null;
  status: 'queued' | 'preparing' | 'running' | 'validating' | 'completed' | 'failed' | 'cancelled';
  attempt_count: number;
  error_code?: string | null;
  error_message?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  root_run_id?: string | null;
  started_at?: string | null;
  heartbeat_at?: string | null;
  structure_sequence?: number | null;
  structure_status?: string | null;
  structure_bundle_prefix?: string | null;
}

export interface KnowledgePointLessonRevision {
  revision_id: string;
  revision: number;
  format: 'markdown';
  content_sha256: string;
  size_bytes: number;
  processing_profile_sha256: string;
  created_at?: string | null;
}

export interface KnowledgePointLesson {
  lesson_id: string;
  status: 'draft' | 'generating' | 'review' | 'approved' | 'failed' | 'cancelled';
  latest_revision_id?: string | null;
  knowledge_point_id: string;
  knowledge_point_title: string;
  structure_id: string;
  unit_id: string;
  unit_title: string;
  content_markdown: string;
  revisions: KnowledgePointLessonRevision[];
}

export interface KnowledgePointSourceSnippet {
  source_id: string;
  source_title?: string | null;
  start?: number | null;
  end?: number | null;
  quote?: string | null;
  markdown: string;
  truncated_before: boolean;
  truncated_after: boolean;
}

export interface KnowledgePointSourcePreview {
  knowledge_point_id: string;
  knowledge_point_title: string;
  unit_id: string;
  unit_title: string;
  snippets: KnowledgePointSourceSnippet[];
}

export interface StructureGenerationProgressEvent {
  sequence: number;
  kind: string;
  label: string;
  detail?: string | null;
  status: string;
  timestamp?: string | null;
  count: number;
}

export interface StructureGenerationProgress {
  generation_job_id: string;
  run_id?: string | null;
  status: string;
  events: StructureGenerationProgressEvent[];
  truncated: boolean;
}

export interface LessonGenerationStatus {
  knowledge_point_id: string;
  generating: boolean;
  generation_job_id?: string | null;
  status?: StructureGenerationJob['status'] | null;
  attempt_count: number;
  auto_grading: boolean;
  error_code?: string | null;
  error_message?: string | null;
  started_at?: string | null;
  heartbeat_at?: string | null;
  root_run_id?: string | null;
}

export interface StudentKnowledgePoint {
  knowledge_point_id: string;
  position: number;
  slug: string;
  title: string;
  summary: string;
  has_lesson: boolean;
}

export interface StudentStructureUnit {
  unit_id: string;
  position: number;
  slug: string;
  title: string;
  summary: string;
  unit_type: string;
  knowledge_points: StudentKnowledgePoint[];
}

export interface StudentTextbookStructure {
  assignment_id: string;
  publication_id: string;
  textbook_id: string;
  textbook_title: string;
  textbook_slug: string;
  version_sequence: number;
  structure_id: string;
  structure_sequence: number;
  units: StudentStructureUnit[];
}

export interface StudentKnowledgePointLesson {
  assignment_id: string;
  knowledge_point_id: string;
  knowledge_point_title: string;
  unit_id: string;
  unit_title: string;
  revision_id: string;
  revision: number;
  format: 'markdown';
  content_sha256: string;
  size_bytes: number;
  content_markdown: string;
}

export type LearningItemKind = 'question' | 'highlight' | 'note' | 'summary';

export interface LearningItem {
  item_id: string;
  assignment_id: string;
  unit_id?: string | null;
  knowledge_point_id?: string | null;
  kind: LearningItemKind;
  content: string;
  source_anchor?: Record<string, unknown> | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface TextbookQuestion {
  question_id: string;
  position: number;
  prompt: string;
  options: Record<string, string>;
  correct_option?: string;
  explanation?: string;
  knowledge_point: string;
  selected_option?: string | null;
  is_correct?: boolean | null;
}

export interface TextbookChapter {
  chapter_id: string;
  position: number;
  slug: string;
  title: string;
  page_start?: number | null;
  page_end?: number | null;
  markdown: string;
  progress_status?: 'not_started' | 'learning' | 'read' | 'check_completed' | 'review_recommended';
  questions: TextbookQuestion[];
}

export interface TextbookAssignmentSummary {
  assignment_id: string;
  student_user_id: string;
  student_name?: string;
  created_at?: string;
}

export interface ArtifactTextbookSource {
  legacy: false;
  position: number;
  document_id: string;
  producer_job_id: string;
  primary_artifact_id: string;
  filename: string;
  media_type: string;
  format: string;
  parser_id: string;
  parser_name: string;
  parser_version?: string | null;
  parse_completed_at?: string | null;
  primary_sha256: string;
  document_deleted: boolean;
  document_accessible: boolean;
}

export interface LegacyTextbookSource {
  legacy: true;
  position: number;
  asset_id: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
}

export type TextbookSource = ArtifactTextbookSource | LegacyTextbookSource;

export interface CompletedParseJob {
  producer_job_id: string;
  document_id: string;
  primary_artifact_id: string;
  filename: string;
  media_type: string;
  format: string;
  parser_id: string;
  parser_name: string;
  parser_version?: string | null;
  parse_completed_at?: string | null;
  size_bytes: number;
  artifact_count: number;
}

export interface TextbookVersion {
  version_id: string;
  sequence: number;
  status: TextbookVersionStatus;
  extractor_name?: string | null;
  extractor_version?: string | null;
  processing_error?: string | null;
  processing_job_id?: string | null;
  processing_job_status?: string | null;
  processing_attempt_count?: number | null;
  chapter_count: number;
  is_published: boolean;
  publication_id?: string | null;
  sources: TextbookSource[];
  chapters: TextbookChapter[];
  assignments: TextbookAssignmentSummary[];
}

export interface TextbookDetail {
  textbook_id: string;
  household_id: string;
  title: string;
  slug: string;
  created_at?: string;
  versions: TextbookVersion[];
}

export interface TextbookProcessingJob {
  job_id: string;
  version_id: string;
  status: string;
  attempt_count?: number;
}

export type BookPipelineJobStatus =
  | 'queued'
  | 'preparing'
  | 'running'
  | 'validating'
  | 'awaiting_review'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface CreateBookPipelineJobInput {
  processing_brief: string;
  request_id: string;
  pause_after_chapter_analysis: boolean;
}

export interface BookPipelineJob {
  generation_job_id: string;
  version_id: string;
  scope: 'book_pipeline';
  structure_id?: string | null;
  knowledge_point_id?: string | null;
  status: BookPipelineJobStatus;
  attempt_count: number;
  pause_after_chapter_analysis: boolean;
  reused_existing_job: boolean;
  error_code?: string | null;
  error_message?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  root_run_id?: string | null;
  started_at?: string | null;
  heartbeat_at?: string | null;
}

export interface TextbookAssignment {
  assignment_id: string;
  publication_id: string;
  student_user_id: string;
  created_at?: string;
}

export interface LearningAssignment {
  assignment_id: string;
  publication_id: string;
  textbook_title: string;
  textbook_slug: string;
  version_sequence: number;
  chapter_count: number;
  completed_chapter_count: number;
  created_at?: string;
}

export interface StudentLearning extends Omit<LearningAssignment, 'chapter_count' | 'completed_chapter_count'> {
  chapters: TextbookChapter[];
}

export interface LearningAnswer {
  answer_id?: string;
  assignment_id?: string;
  question_id?: string;
  selected_option?: string;
  is_correct: boolean;
}

export interface ParentLearningRecords {
  assignment_id: string;
  student_user_id: string;
  textbook_title: string;
  records: Array<{
    chapter_id: string;
    chapter_title: string;
    status: string;
    correct_count: number;
    answer_count: number;
  }>;
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
