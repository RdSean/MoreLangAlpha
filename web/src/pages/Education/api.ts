import { api } from '@/api/client';
import type { CreateEducationTaskInput, EducationAsset, EducationHomeworkDictionaries, EducationMember, EducationTask, EducationTaskCalendar, EducationTaskCalendarRequest, EducationTaskDetail, EducationTaskReview, EducationTaskSubmission, LearningAnswer, LearningAssignment, LearningChatSpace, ParentLearningRecords, ParentLearningTranscript, StudentLearning, SubmitEducationTaskInput, TeachingChapterAsset, TeachingJob, TeachingPackageAssets, TeachingReviewAssetKind, TextbookAssignment, TextbookDetail, TextbookLibraryItem, TextbookProcessingJob, TextbookPublication } from './types';

export async function listEducationTasks(): Promise<EducationTask[]> {
  const { data } = await api.get<EducationTask[]>('/api/v1/education/tasks');
  return data;
}

export async function getEducationTaskDetail(taskId: string): Promise<EducationTaskDetail> {
  const { data } = await api.get<EducationTaskDetail>(`/api/v1/education/tasks/${taskId}`);
  return data;
}

export async function getEducationTaskCalendar(params: EducationTaskCalendarRequest): Promise<EducationTaskCalendar> {
  const { data } = await api.get<EducationTaskCalendar>('/api/v1/education/tasks/calendar', { params });
  return data;
}

export async function getEducationHomeworkDictionaries(): Promise<EducationHomeworkDictionaries> {
  const { data } = await api.get<EducationHomeworkDictionaries>('/api/v1/education/dictionaries');
  return data;
}

export async function listEducationMembers(): Promise<EducationMember[]> {
  const { data } = await api.get<EducationMember[]>('/api/v1/auth/members');
  return data;
}

export async function ensureStudentFlashWorkspace(): Promise<{ workspace_id: string }> {
  const { data } = await api.post<{ workspace_id: string }>('/api/v1/workspaces/flash');
  return data;
}

export async function createEducationTask(input: CreateEducationTaskInput): Promise<EducationTask> {
  const { data } = await api.post<EducationTask>('/api/v1/education/tasks', input);
  return data;
}

export async function checkInEducationTask(taskId: string, input: SubmitEducationTaskInput): Promise<EducationTaskSubmission> {
  const { data } = await api.post<EducationTaskSubmission>(`/api/v1/education/tasks/${taskId}/check-in`, input);
  return data;
}

export async function appendEducationTaskRevision(taskId: string, input: SubmitEducationTaskInput): Promise<EducationTaskSubmission> {
  const { data } = await api.post<EducationTaskSubmission>(`/api/v1/education/tasks/${taskId}/revisions`, input);
  return data;
}

export async function reviewEducationTask(taskId: string, decision: 'feedback' | 'revision_requested', feedbackText: string): Promise<EducationTaskReview> {
  const { data } = await api.post<EducationTaskReview>(`/api/v1/education/tasks/${taskId}/reviews`, {
    decision,
    feedback_text: feedbackText,
  });
  return data;
}

export async function cancelEducationTask(taskId: string): Promise<EducationTask> {
  const { data } = await api.post<EducationTask>(`/api/v1/education/tasks/${taskId}/cancel`);
  return data;
}

export async function uploadEducationAsset(file: File): Promise<EducationAsset> {
  const body = new FormData();
  body.append('file', file);
  const { data } = await api.post<EducationAsset>('/api/v1/education/assets', body, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}

export async function listEducationAssets(): Promise<EducationAsset[]> {
  const { data } = await api.get<EducationAsset[]>('/api/v1/education/assets');
  return data;
}

export async function getEducationAssetDownloadUrl(assetId: string): Promise<string> {
  const { data } = await api.get<{ url: string }>(`/api/v1/education/assets/${assetId}/download`);
  return data.url;
}

export async function listTextbooks(): Promise<TextbookLibraryItem[]> {
  const { data } = await api.get<TextbookLibraryItem[]>('/api/v1/education/textbooks');
  return data;
}

export async function getTextbook(textbookId: string): Promise<TextbookDetail> {
  const { data } = await api.get<TextbookDetail>(`/api/v1/education/textbooks/${textbookId}`);
  return data;
}

export async function createTextbook(input: { title: string }): Promise<TextbookLibraryItem> {
  const { data } = await api.post<TextbookLibraryItem>('/api/v1/education/textbooks', input);
  return data;
}

export async function startTextbookProcessing(textbookId: string, sourceAssetIds: string[]): Promise<TextbookProcessingJob> {
  const { data } = await api.post<TextbookProcessingJob>(`/api/v1/education/textbooks/${textbookId}/processing`, { source_asset_ids: sourceAssetIds });
  return data;
}

export async function runTextbookProcessing(jobId: string): Promise<TextbookProcessingJob> {
  const { data } = await api.post<TextbookProcessingJob>(`/api/v1/education/textbook-processing/${jobId}/run`);
  return data;
}

export async function retryTextbookProcessing(jobId: string): Promise<TextbookProcessingJob> {
  const { data } = await api.post<TextbookProcessingJob>(`/api/v1/education/textbook-processing/${jobId}/retry`);
  return data;
}

export async function createTeachingPackage(contentVersionId: string): Promise<TeachingJob> {
  const { data } = await api.post<TeachingJob>(`/api/v1/education/textbook-versions/${contentVersionId}/teaching-packages`);
  return data;
}

export async function getTeachingJob(jobId: string): Promise<TeachingJob> {
  const { data } = await api.get<TeachingJob>(`/api/v1/education/teaching-jobs/${jobId}`);
  return data;
}

export async function cancelTeachingJob(jobId: string): Promise<TeachingJob> {
  const { data } = await api.post<TeachingJob>(`/api/v1/education/teaching-jobs/${jobId}/cancel`);
  return data;
}

export async function resumeTeachingJob(jobId: string): Promise<TeachingJob> {
  const { data } = await api.post<TeachingJob>(`/api/v1/education/teaching-jobs/${jobId}/resume`);
  return data;
}

export async function getTeachingPackageAssets(teachingPackageId: string): Promise<TeachingPackageAssets> {
  const { data } = await api.get<TeachingPackageAssets>(`/api/v1/education/teaching-packages/${teachingPackageId}/assets`);
  return data;
}

export async function getTeachingChapterAsset(teachingPackageId: string, chapterId: string, kind: TeachingReviewAssetKind): Promise<TeachingChapterAsset> {
  const { data } = await api.get<TeachingChapterAsset>(`/api/v1/education/teaching-packages/${teachingPackageId}/chapters/${chapterId}/assets/${kind}`);
  return data;
}

export async function publishTextbookVersion(textbookId: string, versionId: string, teachingPackageId: string): Promise<TextbookPublication> {
  const { data } = await api.post<TextbookPublication>(`/api/v1/education/textbooks/${textbookId}/versions/${versionId}/publish`, { teaching_package_id: teachingPackageId });
  return data;
}

export async function assignTextbookPublication(publicationId: string, studentUserId: string): Promise<TextbookAssignment> {
  const { data } = await api.post<TextbookAssignment>(`/api/v1/education/textbook-publications/${publicationId}/assignments`, { student_user_id: studentUserId });
  return data;
}

export async function listLearningAssignments(): Promise<LearningAssignment[]> {
  const { data } = await api.get<LearningAssignment[]>('/api/v1/education/learning');
  return data;
}

export async function getStudentLearning(assignmentId: string): Promise<StudentLearning> {
  const { data } = await api.get<StudentLearning>(`/api/v1/education/learning/${assignmentId}`);
  return data;
}

export async function getStudentChapterContext(assignmentId: string, chapterId: string): Promise<{ content: string }> {
  const { data } = await api.get<{ content: string }>(`/api/v1/education/learning/${assignmentId}/chapters/${chapterId}/context`);
  return data;
}

export async function getLearningChatSpace(assignmentId: string): Promise<LearningChatSpace> {
  const { data } = await api.get<LearningChatSpace>(`/api/v1/education/learning/${assignmentId}/chat-space`);
  return data;
}

export async function updateLearningProgress(assignmentId: string, chapterId: string, status: 'learning' | 'read' | 'check_completed' | 'review_recommended'): Promise<void> {
  await api.post(`/api/v1/education/learning/${assignmentId}/chapters/${chapterId}/progress`, { status });
}

export async function answerLearningQuestion(assignmentId: string, questionId: string, selectedOption: string): Promise<LearningAnswer> {
  const { data } = await api.post<LearningAnswer>(`/api/v1/education/learning/${assignmentId}/questions/${questionId}/answers`, { selected_option: selectedOption });
  return data;
}

export async function getParentLearningRecords(assignmentId: string): Promise<ParentLearningRecords> {
  const { data } = await api.get<ParentLearningRecords>(`/api/v1/education/learning/${assignmentId}/records`);
  return data;
}

export async function getParentLearningTranscript(assignmentId: string): Promise<ParentLearningTranscript> {
  const { data } = await api.get<ParentLearningTranscript>(`/api/v1/education/learning/${assignmentId}/chat-transcript`);
  return data;
}
