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
}
