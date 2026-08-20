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

export interface FamilyLlmEndpoint {
  endpoint_id: string;
  display_name: string;
  provider: string;
  model_id: string;
  base_url: string | null;
  masked_api_key: string | null;
  enabled: boolean;
  sort_order: number;
}

export interface FamilyLlmPool {
  endpoints: FamilyLlmEndpoint[];
  default_endpoint_id: string | null;
}

export interface FamilyLlmAvailabilityEndpoint {
  endpoint_id: string;
  display_name: string;
  provider: string;
  model_id: string;
  enabled: boolean;
  sort_order: number;
  model_key: string;
}

export interface FamilyLlmAvailability {
  endpoints: FamilyLlmAvailabilityEndpoint[];
  selected_endpoint_id: string | null;
  selected_source: 'preference' | 'default' | null;
  preference_endpoint_id: string | null;
  default_endpoint_id: string | null;
}

export interface FamilyLlmEndpointInput {
  display_name: string;
  provider: string;
  model_id: string;
  base_url?: string | null;
  api_key?: string;
  enabled: boolean;
  sort_order: number;
}

export interface FamilyLlmEndpointUpdate {
  display_name?: string;
  provider?: string;
  model_id?: string;
  base_url?: string | null;
  /** Undefined keeps the encrypted value; an empty string explicitly clears it. */
  api_key?: string;
  enabled?: boolean;
  sort_order?: number;
}

export async function listFamilyChildren(): Promise<FamilyChild[]> {
  const { data } = await api.get<FamilyChild[]>('/api/v1/auth/children');
  return data;
}

export async function createChildAccount(input: CreateChildAccountInput): Promise<CreatedChildAccount> {
  const { data } = await api.post<CreatedChildAccount>('/api/v1/auth/children', input);
  return data;
}

export async function getFamilyLlmPool(): Promise<FamilyLlmPool> {
  const { data } = await api.get<FamilyLlmPool>('/api/v1/family/llm-pool');
  return data;
}

export async function createFamilyLlmEndpoint(input: FamilyLlmEndpointInput): Promise<FamilyLlmEndpoint> {
  const { data } = await api.post<FamilyLlmEndpoint>('/api/v1/family/llm-pool', input);
  return data;
}

export async function updateFamilyLlmEndpoint(
  endpointId: string,
  input: FamilyLlmEndpointUpdate,
): Promise<FamilyLlmEndpoint> {
  // Sending an undefined key would be ambiguous in JSON. Omit it to preserve
  // the stored encrypted value; the empty string intentionally clears it.
  const { api_key: apiKey, ...fields } = input;
  const payload = apiKey === undefined ? fields : { ...fields, api_key: apiKey };
  const { data } = await api.patch<FamilyLlmEndpoint>(
    `/api/v1/family/llm-pool/${encodeURIComponent(endpointId)}`,
    payload,
  );
  return data;
}

export async function deleteFamilyLlmEndpoint(endpointId: string): Promise<void> {
  await api.delete(`/api/v1/family/llm-pool/${encodeURIComponent(endpointId)}`);
}

export async function setFamilyLlmDefault(endpointId: string | null): Promise<Pick<FamilyLlmPool, 'default_endpoint_id'>> {
  const { data } = await api.put<Pick<FamilyLlmPool, 'default_endpoint_id'>>(
    '/api/v1/family/llm-pool/default',
    { endpoint_id: endpointId },
  );
  return data;
}

export async function clearFamilyLlmDefault(): Promise<Pick<FamilyLlmPool, 'default_endpoint_id'>> {
  return setFamilyLlmDefault(null);
}

export async function getFamilyLlmAvailability(): Promise<FamilyLlmAvailability> {
  const { data } = await api.get<FamilyLlmAvailability>('/api/v1/family/llm-availability');
  return data;
}

export async function setFamilyLlmPreference(endpointId: string | null): Promise<FamilyLlmAvailability> {
  const { data } = await api.put<FamilyLlmAvailability>('/api/v1/family/llm-preference', {
    endpoint_id: endpointId,
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
