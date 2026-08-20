import { beforeEach, describe, expect, it, vi } from 'vitest';

const request = vi.hoisted(() => ({
  defaults: { baseURL: '' },
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
}));

vi.mock('@/api/client', () => ({ api: request }));

import {
  clearFamilyLlmDefault,
  createFamilyLlmEndpoint,
  deleteFamilyLlmEndpoint,
  getFamilyLlmPool,
  setFamilyLlmDefault,
  updateFamilyLlmEndpoint,
} from '../api';

describe('family LLM settings API', () => {
  beforeEach(() => {
    request.get.mockReset();
    request.post.mockReset();
    request.patch.mockReset();
    request.put.mockReset();
    request.delete.mockReset();
  });

  it('uses the parent pool endpoints with explicit payloads', async () => {
    request.get.mockResolvedValue({ data: { endpoints: [], default_endpoint_id: null } });
    request.post.mockResolvedValue({ data: { endpoint_id: 'endpoint-1' } });
    request.patch.mockResolvedValue({ data: { endpoint_id: 'endpoint-1' } });
    request.put.mockResolvedValue({ data: { default_endpoint_id: 'endpoint-1' } });
    request.delete.mockResolvedValue({ data: undefined });

    await getFamilyLlmPool();
    await createFamilyLlmEndpoint({
      display_name: '家庭 DeepSeek Flash',
      provider: 'deepseek',
      model_id: 'deepseek-chat',
      base_url: 'https://api.deepseek.com',
      api_key: 'secret-key',
      enabled: true,
      sort_order: 0,
    });
    await updateFamilyLlmEndpoint('endpoint-1', {
      display_name: '新版 Flash',
      provider: 'deepseek',
      model_id: 'deepseek-chat',
      base_url: 'https://api.deepseek.com',
      enabled: true,
      sort_order: 0,
    });
    await setFamilyLlmDefault('endpoint-1');
    await clearFamilyLlmDefault();
    await deleteFamilyLlmEndpoint('endpoint-1');

    expect(request.get).toHaveBeenCalledWith('/api/v1/family/llm-pool');
    expect(request.post).toHaveBeenCalledWith('/api/v1/family/llm-pool', expect.objectContaining({ api_key: 'secret-key' }));
    expect(request.patch).toHaveBeenCalledWith(
      '/api/v1/family/llm-pool/endpoint-1',
      expect.not.objectContaining({ api_key: expect.anything() }),
    );
    expect(request.put).toHaveBeenNthCalledWith(1, '/api/v1/family/llm-pool/default', { endpoint_id: 'endpoint-1' });
    expect(request.put).toHaveBeenNthCalledWith(2, '/api/v1/family/llm-pool/default', { endpoint_id: null });
    expect(request.delete).toHaveBeenCalledWith('/api/v1/family/llm-pool/endpoint-1');
  });

  it('allows an edit to explicitly clear a stored API key', async () => {
    request.patch.mockResolvedValue({ data: { endpoint_id: 'endpoint-1' } });

    await updateFamilyLlmEndpoint('endpoint-1', { api_key: '' });

    expect(request.patch).toHaveBeenCalledWith('/api/v1/family/llm-pool/endpoint-1', { api_key: '' });
  });
});
