import { api } from '@/api/client';

export const PROFILE_REQUEST_TIMEOUT_MS = 10_000;

export async function getCurrentUser(
  params?: { refresh_tier?: boolean },
): Promise<Record<string, unknown>> {
  const { data } = await api.get('/api/v1/users/me', {
    params,
    timeout: PROFILE_REQUEST_TIMEOUT_MS,
  });
  return data;
}

export async function getPreferences(): Promise<Record<string, unknown> | null> {
  try {
    const { data } = await api.get('/api/v1/users/me/preferences');
    return data;
  } catch (error: unknown) {
    const status = (error as { response?: { status?: number } }).response?.status;
    if (status === 404) return null;
    throw error;
  }
}

export async function updateCurrentUser(
  userData: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const { data } = await api.put('/api/v1/users/me', userData);
  return data;
}

export async function updatePreferences(
  preferences: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const { data } = await api.put('/api/v1/users/me/preferences', preferences);
  return data;
}

export async function clearPreferences(): Promise<Record<string, unknown>> {
  const { data } = await api.delete('/api/v1/users/me/preferences');
  return data;
}

export async function uploadAvatar(file: File): Promise<{ avatar_url: string }> {
  const formData = new FormData();
  formData.append('file', file);

  const { data } = await api.post('/api/v1/users/me/avatar', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}
