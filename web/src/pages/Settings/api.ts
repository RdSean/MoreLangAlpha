import { api } from '@/api/client';
import { streamFetch } from '@/pages/ChatAgent/utils/api/transport';

export interface FlashWorkspaceSummary {
  workspace_id: string;
  name: string;
  status: string | null;
  updated_at?: string | null;
}

export interface FamilyChild {
  user_id: string;
  email: string | null;
  username: string | null;
  name: string;
  role: 'student';
  household_id: string;
  flash_workspace: FlashWorkspaceSummary;
}

export interface FamilyThread {
  thread_id: string;
  workspace_id: string;
  thread_index: number;
  current_status: string;
  msg_type?: string | null;
  title?: string | null;
  first_query_content?: string | null;
  platform?: string | null;
  metadata?: Record<string, unknown>;
  is_shared?: boolean;
  is_pinned?: boolean;
  archived_at?: string | null;
  turn_count?: number | null;
  created_at?: string;
  updated_at?: string;
}

export interface FamilyThreadList {
  threads: FamilyThread[];
  total: number;
  limit: number;
  offset: number;
}

export interface CreateChildAccountInput {
  username: string;
  password: string;
  name: string;
}

export interface CreatedChildAccount {
  user_id: string;
  email: string | null;
  name: string;
  role: 'student';
  household_id: string;
}

export interface FamilyLlmAvailabilityModel {
  model_key: string;
  display_name: string;
  provider: string;
  model_id: string;
  capabilities?: {
    input_modalities: string[];
  };
}

export interface FamilyLlmAvailability {
  models: FamilyLlmAvailabilityModel[];
  default_model_key: string | null;
  selected_model_key: string | null;
  selected_source: 'preference' | 'default' | null;
  has_available_models: boolean;
  empty_reason: 'no_available_models' | null;
}

export async function listFamilyChildren(): Promise<FamilyChild[]> {
  const { data } = await api.get<FamilyChild[]>('/api/v1/auth/children');
  return data;
}

export async function createChildAccount(input: CreateChildAccountInput): Promise<CreatedChildAccount> {
  const { data } = await api.post<CreatedChildAccount>('/api/v1/auth/children', input);
  return data;
}

export async function getFamilyLlmAvailability(): Promise<FamilyLlmAvailability> {
  const { data } = await api.get<FamilyLlmAvailability>('/api/v1/family/llm-availability');
  return data;
}

export async function setFamilyLlmPreference(modelKey: string | null): Promise<FamilyLlmAvailability> {
  const { data } = await api.put<FamilyLlmAvailability>('/api/v1/family/llm-preference', {
    model_key: modelKey,
  });
  return data;
}

export async function getFamilyChildWorkspace(studentUserId: string): Promise<FlashWorkspaceSummary> {
  const { data } = await api.get<FlashWorkspaceSummary>(`/api/v1/auth/children/${encodeURIComponent(studentUserId)}/workspace`);
  return data;
}

export async function listFamilyChildThreads(
  studentUserId: string,
  limit = 20,
  offset = 0,
  sortBy: 'created_at' | 'updated_at' | 'thread_index' = 'updated_at',
  sortOrder: 'asc' | 'desc' = 'desc',
): Promise<FamilyThreadList> {
  const { data } = await api.get<FamilyThreadList>(`/api/v1/auth/children/${encodeURIComponent(studentUserId)}/threads`, {
    params: { limit, offset, sort_by: sortBy, sort_order: sortOrder },
  });
  return data;
}

export async function streamFamilyChildThreadReplay(
  studentUserId: string,
  threadId: string,
  onEvent: (event: Record<string, unknown>) => void,
): Promise<void> {
  await streamFetch(
    `/api/v1/auth/children/${encodeURIComponent(studentUserId)}/threads/${encodeURIComponent(threadId)}/replay`,
    { method: 'GET' },
    onEvent,
  );
}
