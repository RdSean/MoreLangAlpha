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
  getFamilyLlmAvailability,
  setFamilyLlmPreference,
} from '../api';

describe('family LLM settings API', () => {
  beforeEach(() => {
    request.get.mockReset();
    request.post.mockReset();
    request.patch.mockReset();
    request.put.mockReset();
    request.delete.mockReset();
  });

  it('uses only the owner-backed availability and student preference endpoints', async () => {
    request.get.mockResolvedValue({
      data: {
        models: [{ model_key: 'deepseek-chat', display_name: 'DeepSeek Flash', provider: 'deepseek', model_id: 'deepseek-chat' }],
        default_model_key: 'deepseek-chat',
        selected_model_key: 'deepseek-chat',
        selected_source: 'default',
        has_available_models: true,
        empty_reason: null,
      },
    });
    request.put.mockResolvedValue({ data: { models: [], selected_model_key: 'claude-sonnet-5' } });

    await getFamilyLlmAvailability();
    await setFamilyLlmPreference('claude-sonnet-5');

    expect(request.get).toHaveBeenCalledWith('/api/v1/family/llm-availability');
    expect(request.put).toHaveBeenCalledWith('/api/v1/family/llm-preference', { model_key: 'claude-sonnet-5' });
    expect(request.post).not.toHaveBeenCalled();
    expect(request.patch).not.toHaveBeenCalled();
    expect(request.delete).not.toHaveBeenCalled();
  });
});
