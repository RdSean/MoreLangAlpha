export type EducationTaskStatus = 'open' | 'submitted' | 'revision_requested' | 'completed' | 'cancelled';

export interface EducationTask {
  task_id: string;
  task_rule_id: string;
  household_id: string;
  assigned_student_id: string;
  occurrence_date: string;
  due_at: string;
  title: string;
  description: string;
  status: EducationTaskStatus;
  created_at?: string;
  latest_review_decision?: 'revision_requested' | 'completed';
  latest_feedback_text?: string;
}

export interface EducationMember {
  user_id: string;
  name: string;
  role: 'parent' | 'student';
}

export interface CreateEducationTaskInput {
  assigned_student_id: string;
  title: string;
  description: string;
  due_at: string;
  frequency: 'once' | 'daily';
  material_asset_ids: string[];
}

export interface SubmitEducationTaskInput {
  submission_text: string;
  idempotency_key: string;
  asset_ids: string[];
}

export interface EducationAsset {
  asset_id: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  created_at?: string;
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
  teaching_material?: string | null;
  progress_status?: 'not_started' | 'learning' | 'read' | 'check_completed' | 'review_recommended';
  questions: TextbookQuestion[];
}

export interface TextbookAssignmentSummary {
  assignment_id: string;
  student_user_id: string;
  student_name?: string;
  created_at?: string;
}

export interface TeachingPackageSummary {
  teaching_package_id: string;
  job_id: string;
  sequence: number;
  status: 'queued' | 'preparing' | 'building_skill' | 'generating_teaching' | 'validating' | 'review' | 'failed' | 'cancelled';
  job_status: 'queued' | 'preparing' | 'running' | 'validating' | 'completed' | 'failed' | 'cancelled';
  chapter_count: number;
  question_count: number;
}

export type TeachingJobAction = 'cancel' | 'resume';
export type TeachingJobPhase = TeachingPackageSummary['status'];

export interface TeachingJobEvent {
  sequence: number;
  phase: TeachingJobPhase;
  summary: string;
  chapter_id?: string | null;
  created_at?: string | null;
}

export interface TeachingJobAttempt {
  attempt_id: string;
  root_run_id?: string | null;
  previous_attempt_id?: string | null;
  status: string;
  started_at?: string | null;
  heartbeat_at?: string | null;
  completed_at?: string | null;
}

export interface TeachingJob {
  job_id: string;
  teaching_package_id: string;
  content_version_id: string;
  status: 'queued' | 'preparing' | 'running' | 'validating' | 'completed' | 'failed' | 'cancelled';
  phase: TeachingJobPhase;
  attempt_count: number;
  completed_chapter_count: number;
  total_chapter_count: number;
  last_heartbeat_at?: string | null;
  error_message?: string | null;
  created_at?: string | null;
  completed_at?: string | null;
  actions: TeachingJobAction[];
  events: TeachingJobEvent[];
  attempts: TeachingJobAttempt[];
}

export interface TextbookSource {
  asset_id: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
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
  teaching_packages: TeachingPackageSummary[];
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

export interface TextbookPublication {
  publication_id: string;
  version_id: string;
  teaching_package_id: string;
  created_at?: string;
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
