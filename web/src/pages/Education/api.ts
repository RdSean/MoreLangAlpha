import { api } from '@/api/client';
import type { CreateEducationTaskInput, EducationAsset, EducationMember, EducationTask, SubmitEducationTaskInput } from './types';

export async function listEducationTasks(): Promise<EducationTask[]> {
  const { data } = await api.get<EducationTask[]>('/api/v1/education/tasks');
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

export async function submitEducationTask(taskId: string, input: SubmitEducationTaskInput): Promise<void> {
  await api.post(`/api/v1/education/tasks/${taskId}/submissions`, input);
}

export async function reviewEducationTask(taskId: string, decision: 'revision_requested' | 'completed', feedbackText: string): Promise<void> {
  await api.post(`/api/v1/education/tasks/${taskId}/reviews`, {
    decision,
    feedback_text: feedbackText,
  });
}

export async function cancelEducationTask(taskId: string): Promise<void> {
  await api.post(`/api/v1/education/tasks/${taskId}/cancel`);
}

export async function uploadEducationAsset(file: File): Promise<EducationAsset> {
  const body = new FormData();
  body.append('file', file);
  const { data } = await api.post<EducationAsset>('/api/v1/education/assets', body, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}
