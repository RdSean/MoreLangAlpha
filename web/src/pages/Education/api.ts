import { api } from '@/api/client';
import type { BookPipelineJob, BookPipelineProgress, CompletedParseJob, CreateBookPipelineJobInput, CreateEducationTaskInput, EducationAsset, EducationHomeworkDictionaries, EducationMember, EducationTask, EducationTaskCalendar, EducationTaskCalendarRequest, EducationTaskDetail, EducationTaskReview, EducationTaskSubmission, KnowledgePointCandidate, KnowledgePointCandidateReview, KnowledgePointLesson, KnowledgePointSourcePreview, LearningAssignment, LearningChatSpace, LearningItem, LearningItemKind, LessonGenerationStatus, MergeKnowledgePointCandidatesInput, ParentLearningTranscript, SplitKnowledgePointCandidateInput, StructureGenerationJob, StructureGenerationProgress, StudentKnowledgePointLesson, StudentTextbookStructure, SubmitEducationTaskInput, TextbookAssignment, TextbookDetail, TextbookLibraryItem, TextbookProcessingJob, TextbookStructure, TextbookStructureUnit, UpdateKnowledgePointCandidateInput } from './types';

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

export async function uploadEducationAsset(file: File, options?: { stagingKey?: string; stagingSlot?: number }): Promise<EducationAsset> {
  const body = new FormData();
  body.append('file', file);
  const params = options?.stagingKey && options.stagingSlot !== undefined ? { staging_key: options.stagingKey, staging_slot: options.stagingSlot } : undefined;
  const { data } = await api.post<EducationAsset>('/api/v1/education/assets', body, {
    headers: { 'Content-Type': 'multipart/form-data' },
    params,
  });
  return data;
}

export async function deleteEducationAsset(assetId: string): Promise<void> {
  await api.delete(`/api/v1/education/assets/${assetId}`);
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

export async function getLatestTextbookStructure(versionId: string): Promise<TextbookStructure | null> {
  const { data } = await api.get<TextbookStructure | null>(`/api/v1/education/textbook-versions/${versionId}/structure`);
  return data;
}

export async function getKnowledgePointCandidateReview(
  structureId: string,
): Promise<KnowledgePointCandidateReview> {
  const { data } = await api.get<KnowledgePointCandidateReview>(
    `/api/v1/education/structures/${structureId}/candidates`,
  );
  return data;
}

export async function updateKnowledgePointCandidate(
  candidateId: string,
  input: UpdateKnowledgePointCandidateInput,
): Promise<KnowledgePointCandidate> {
  const { data } = await api.patch<KnowledgePointCandidate>(
    `/api/v1/education/candidates/${candidateId}`,
    input,
  );
  return data;
}

export async function acceptKnowledgePointCandidates(
  candidateIds: string[],
): Promise<KnowledgePointCandidate[]> {
  const { data } = await api.post<KnowledgePointCandidate[]>(
    '/api/v1/education/candidates/accept',
    { candidate_ids: candidateIds },
  );
  return data;
}

export async function rejectKnowledgePointCandidates(
  candidateIds: string[],
): Promise<KnowledgePointCandidate[]> {
  const { data } = await api.post<KnowledgePointCandidate[]>(
    '/api/v1/education/candidates/reject',
    { candidate_ids: candidateIds },
  );
  return data;
}

export async function mergeKnowledgePointCandidates(
  input: MergeKnowledgePointCandidatesInput,
): Promise<KnowledgePointCandidate[]> {
  const { data } = await api.post<KnowledgePointCandidate[]>(
    '/api/v1/education/candidates/merge',
    input,
  );
  return data;
}

export async function splitKnowledgePointCandidate(
  input: SplitKnowledgePointCandidateInput,
): Promise<KnowledgePointCandidate[]> {
  const { data } = await api.post<KnowledgePointCandidate[]>(
    '/api/v1/education/candidates/split',
    input,
  );
  return data;
}

export async function createBookPipelineJob(
  versionId: string,
  input: CreateBookPipelineJobInput,
): Promise<BookPipelineJob> {
  const { data } = await api.post<BookPipelineJob>(
    `/api/v1/education/textbook-versions/${versionId}/book-pipeline-jobs`,
    input,
  );
  return data;
}

export async function cancelBookPipelineJob(
  jobId: string,
): Promise<BookPipelineJob> {
  const { data } = await api.post<BookPipelineJob>(
    `/api/v1/education/book-pipeline-jobs/${jobId}/cancel`,
  );
  return data;
}

export async function getBookPipelineJobProgress(
  jobId: string,
): Promise<BookPipelineProgress> {
  const { data } = await api.get<BookPipelineProgress>(
    `/api/v1/education/jobs/${jobId}/progress`,
  );
  return data;
}

export async function createTextbookStructure(versionId: string, profile?: Record<string, unknown>): Promise<StructureGenerationJob> {
  const { data } = await api.post<StructureGenerationJob>(`/api/v1/education/textbook-versions/${versionId}/structures`, profile ? { profile } : {});
  return data;
}

export async function getStructureGenerationJob(generationJobId: string): Promise<StructureGenerationJob> {
  const { data } = await api.get<StructureGenerationJob>(`/api/v1/education/structure-generation-jobs/${generationJobId}`);
  return data;
}

export async function getStructureGenerationProgress(generationJobId: string): Promise<StructureGenerationProgress> {
  const { data } = await api.get<StructureGenerationProgress>(`/api/v1/education/structure-generation-jobs/${generationJobId}/progress`);
  return data;
}

export async function resumeStructureGenerationJob(generationJobId: string): Promise<StructureGenerationJob> {
  const { data } = await api.post<StructureGenerationJob>(`/api/v1/education/structure-generation-jobs/${generationJobId}/resume`);
  return data;
}

export async function generateBookAssets(structureId: string): Promise<StructureGenerationJob> {
  const { data } = await api.post<StructureGenerationJob>(`/api/v1/education/textbook-structures/${structureId}/book-assets`);
  return data;
}

export async function updateTextbookStructure(structureId: string, units: TextbookStructureUnit[]): Promise<TextbookStructure> {
  const { data } = await api.put<TextbookStructure>(`/api/v1/education/textbook-structures/${structureId}`, { units });
  return data;
}

export async function acceptTextbookStructure(structureId: string): Promise<TextbookStructure> {
  const { data } = await api.post<TextbookStructure>(`/api/v1/education/textbook-structures/${structureId}/review`);
  return data;
}

export async function generateKnowledgePointLesson(knowledgePointId: string, autoGrading = false): Promise<StructureGenerationJob> {
  const { data } = await api.post<StructureGenerationJob>(`/api/v1/education/knowledge-points/${knowledgePointId}/lessons`, { auto_grading: autoGrading });
  return data;
}

export async function getKnowledgePointLesson(lessonId: string): Promise<KnowledgePointLesson> {
  const { data } = await api.get<KnowledgePointLesson>(`/api/v1/education/knowledge-point-lessons/${lessonId}`);
  return data;
}

export async function getKnowledgePointLessonByPoint(knowledgePointId: string): Promise<KnowledgePointLesson | null> {
  const { data } = await api.get<KnowledgePointLesson | null>(`/api/v1/education/knowledge-points/${knowledgePointId}/lesson`);
  return data;
}

export async function getKnowledgePointSourcePreview(knowledgePointId: string): Promise<KnowledgePointSourcePreview> {
  const { data } = await api.get<KnowledgePointSourcePreview>(`/api/v1/education/knowledge-points/${knowledgePointId}/source-preview`);
  return data;
}

export async function getLessonGenerationStatus(knowledgePointId: string): Promise<LessonGenerationStatus> {
  const { data } = await api.get<LessonGenerationStatus>(`/api/v1/education/knowledge-points/${knowledgePointId}/lesson-generation`);
  return data;
}

export async function createKnowledgePointLessonRevision(lessonId: string, contentMarkdown: string): Promise<KnowledgePointLesson> {
  const { data } = await api.post<KnowledgePointLesson>(`/api/v1/education/knowledge-point-lessons/${lessonId}/revisions`, { content_markdown: contentMarkdown });
  return data;
}

export async function approveKnowledgePointLesson(lessonId: string, revisionId: string): Promise<KnowledgePointLesson> {
  const { data } = await api.post<KnowledgePointLesson>(`/api/v1/education/knowledge-point-lessons/${lessonId}/review`, { revision_id: revisionId });
  return data;
}

export async function publishTextbookStructure(versionId: string, structureId: string): Promise<{ publication_id: string; version_id: string; structure_id: string }> {
  const { data } = await api.post<{ publication_id: string; version_id: string; structure_id: string }>(`/api/v1/education/textbook-versions/${versionId}/structure-publications`, { structure_id: structureId });
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

export async function listCompletedParseJobs(): Promise<CompletedParseJob[]> {
  const { data } = await api.get<CompletedParseJob[]>('/api/v1/education/textbook-parse-jobs/completed');
  return data;
}

export async function startTextbookProcessingFromParseJobs(textbookId: string, sourceParseJobIds: string[]): Promise<TextbookProcessingJob> {
  const { data } = await api.post<TextbookProcessingJob>(`/api/v1/education/textbooks/${textbookId}/processing`, { source_parse_job_ids: sourceParseJobIds });
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

export async function assignTextbookPublication(publicationId: string, studentUserId: string): Promise<TextbookAssignment> {
  const { data } = await api.post<TextbookAssignment>(`/api/v1/education/textbook-publications/${publicationId}/assignments`, { student_user_id: studentUserId });
  return data;
}

export async function listLearningAssignments(): Promise<LearningAssignment[]> {
  const { data } = await api.get<LearningAssignment[]>('/api/v1/education/learning');
  return data;
}

export async function getStudentTextbookStructure(assignmentId: string): Promise<StudentTextbookStructure> {
  const { data } = await api.get<StudentTextbookStructure>(`/api/v1/education/learning/${assignmentId}/structure`);
  return data;
}

export async function getStudentKnowledgePointLesson(assignmentId: string, knowledgePointId: string): Promise<StudentKnowledgePointLesson> {
  const { data } = await api.get<StudentKnowledgePointLesson>(`/api/v1/education/learning/${assignmentId}/knowledge-points/${knowledgePointId}`);
  return data;
}

export async function listStudentLearningItems(
  assignmentId: string,
  filters: { unitId?: string; knowledgePointId?: string } = {},
): Promise<LearningItem[]> {
  const { data } = await api.get<LearningItem[]>(`/api/v1/education/learning/${assignmentId}/items`, {
    params: {
      unit_id: filters.unitId,
      knowledge_point_id: filters.knowledgePointId,
    },
  });
  return data;
}

export async function createStudentLearningItem(
  assignmentId: string,
  knowledgePointId: string,
  input: {
    unitId?: string;
    kind: Exclude<LearningItemKind, 'summary'>;
    content: string;
    sourceAnchor?: Record<string, unknown> | null;
  },
): Promise<LearningItem> {
  const { data } = await api.post<LearningItem>(`/api/v1/education/learning/${assignmentId}/knowledge-points/${knowledgePointId}/items`, {
    unit_id: input.unitId,
    kind: input.kind,
    content: input.content,
    source_anchor: input.sourceAnchor,
  });
  return data;
}

export async function updateStudentLearningItem(
  assignmentId: string,
  itemId: string,
  input: { content: string; sourceAnchor?: Record<string, unknown> | null },
): Promise<LearningItem> {
  const { data } = await api.patch<LearningItem>(`/api/v1/education/learning/${assignmentId}/items/${itemId}`, {
    content: input.content,
    source_anchor: input.sourceAnchor,
  });
  return data;
}

export async function deleteStudentLearningItem(assignmentId: string, itemId: string): Promise<void> {
  await api.delete(`/api/v1/education/learning/${assignmentId}/items/${itemId}`);
}

export async function generateStudentUnitSummary(assignmentId: string, unitId: string): Promise<LearningItem> {
  const { data } = await api.post<LearningItem>(`/api/v1/education/learning/${assignmentId}/units/${unitId}/summaries`);
  return data;
}

export async function updateStudentKpProgress(assignmentId: string, knowledgePointId: string, status: 'learning' | 'read' | 'review_recommended'): Promise<void> {
  await api.post(`/api/v1/education/learning/${assignmentId}/knowledge-points/${knowledgePointId}/progress`, { status });
}

export async function getLearningChatSpace(assignmentId: string): Promise<LearningChatSpace> {
  const { data } = await api.get<LearningChatSpace>(`/api/v1/education/learning/${assignmentId}/chat-space`);
  return data;
}

export async function getParentLearningTranscript(assignmentId: string): Promise<ParentLearningTranscript> {
  const { data } = await api.get<ParentLearningTranscript>(`/api/v1/education/learning/${assignmentId}/chat-transcript`);
  return data;
}
