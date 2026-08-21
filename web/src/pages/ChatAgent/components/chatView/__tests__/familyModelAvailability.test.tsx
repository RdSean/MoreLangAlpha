import { describe, expect, it } from 'vitest';

import { buildFamilyModelAvailability } from '../familyModelAvailability';

describe('ChatView family model availability', () => {
  it('projects the server-selected default as an opaque model key', () => {
    const result = buildFamilyModelAvailability({
      models: [{
        model_key: 'deepseek-chat',
        display_name: '家庭 DeepSeek Flash',
        provider: 'deepseek',
        model_id: 'deepseek-chat',
      }],
      selected_model_key: 'deepseek-chat',
      selected_source: 'default',
      default_model_key: 'deepseek-chat',
      has_available_models: true,
      empty_reason: null,
    }, false, false);

    expect(result).toEqual({
      initialModel: 'deepseek-chat',
      models: [{ modelKey: 'deepseek-chat', displayName: '家庭 DeepSeek Flash' }],
      status: 'ready',
    });
  });

  it('does not invent a model when the family has choices but no default or preference', () => {
    const result = buildFamilyModelAvailability({
      models: [{
        model_key: 'deepseek-chat',
        display_name: '家庭 DeepSeek Flash',
        provider: 'deepseek',
        model_id: 'deepseek-chat',
      }],
      selected_model_key: null,
      selected_source: null,
      default_model_key: null,
      has_available_models: true,
      empty_reason: null,
    }, false, false);

    expect(result.initialModel).toBeNull();
    expect(result.models).toHaveLength(1);
    expect(result.status).toBe('ready');
  });

  it('reports empty and failed states without returning a fallback model', () => {
    expect(buildFamilyModelAvailability(null, false, false)).toMatchObject({ initialModel: null, models: [], status: 'empty' });
    expect(buildFamilyModelAvailability(null, false, true)).toMatchObject({ initialModel: null, models: [], status: 'error' });
  });
});
