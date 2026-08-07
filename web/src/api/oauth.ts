import { api } from '@/api/client';

export interface OAuthStatus {
  connected: boolean;
  account_id: string | null;
  email: string | null;
  plan_type: string | null;
}

const disconnected: OAuthStatus = {
  connected: false,
  account_id: null,
  email: null,
  plan_type: null,
};

export async function initiateCodexDevice(): Promise<Record<string, unknown>> {
  const { data } = await api.post('/api/v1/oauth/codex/device/initiate');
  return data;
}

export async function pollCodexDevice(): Promise<Record<string, unknown>> {
  const { data } = await api.post('/api/v1/oauth/codex/device/poll');
  return data;
}

export async function getCodexOAuthStatus(): Promise<OAuthStatus> {
  try {
    const { data } = await api.get<OAuthStatus>('/api/v1/oauth/codex/status');
    return data;
  } catch {
    return disconnected;
  }
}

export async function disconnectCodexOAuth(): Promise<Record<string, unknown>> {
  const { data } = await api.delete('/api/v1/oauth/codex');
  return data;
}

export async function initiateClaudeOAuth(): Promise<Record<string, unknown>> {
  const { data } = await api.post('/api/v1/oauth/claude/initiate');
  return data;
}

export async function submitClaudeCallback(callbackInput: string): Promise<Record<string, unknown>> {
  const { data } = await api.post('/api/v1/oauth/claude/callback', { callback_input: callbackInput });
  return data;
}

export async function getClaudeOAuthStatus(): Promise<OAuthStatus> {
  try {
    const { data } = await api.get<OAuthStatus>('/api/v1/oauth/claude/status');
    return data;
  } catch {
    return disconnected;
  }
}

export async function disconnectClaudeOAuth(): Promise<Record<string, unknown>> {
  const { data } = await api.delete('/api/v1/oauth/claude');
  return data;
}
