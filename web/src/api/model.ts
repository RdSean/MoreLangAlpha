/**
 * Model and BYOK API key endpoints.
 * Extracted from Dashboard/utils/api.ts for shared use.
 */
import { api } from '@/api/client';

export interface TokenizerResourceStatus {
  encoding: 'cl100k_base';
  status: 'ready' | 'approximate';
  exact: boolean;
  error_code: string | null;
}

export async function getAvailableModels(): Promise<Record<string, unknown>> {
  const { data } = await api.get('/api/v1/models');
  return data;
}

export async function getUserApiKeys(): Promise<Record<string, unknown>> {
  const { data } = await api.get('/api/v1/users/me/api-keys');
  return data;
}

export async function updateUserApiKeys(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
  const { data } = await api.put('/api/v1/users/me/api-keys', payload);
  return data;
}

export async function deleteUserApiKey(provider: string): Promise<Record<string, unknown>> {
  const { data } = await api.delete(`/api/v1/users/me/api-keys/${provider}`);
  return data;
}

export async function getTokenizerResourceStatus(): Promise<TokenizerResourceStatus> {
  const { data } = await api.get<TokenizerResourceStatus>('/api/v1/runtime-resources/tokenizer');
  return data;
}

export async function retryTokenizerVocabularyDownload(): Promise<TokenizerResourceStatus> {
  const { data } = await api.post<TokenizerResourceStatus>('/api/v1/runtime-resources/tokenizer/download');
  return data;
}
