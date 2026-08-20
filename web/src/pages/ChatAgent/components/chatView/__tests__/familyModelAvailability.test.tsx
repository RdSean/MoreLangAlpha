import { describe, expect, it } from 'vitest';

import { buildFamilyModelAvailability } from '../familyModelAvailability';

describe('ChatView family model availability', () => {
  it('projects the server-selected default as an opaque model key', () => {
    const result = buildFamilyModelAvailability({
      endpoints: [{
        endpoint_id: 'endpoint-1',
        display_name: '家庭 DeepSeek Flash',
        provider: 'deepseek',
        model_id: 'deepseek-chat',
        enabled: true,
        sort_order: 0,
        model_key: 'family:endpoint-1',
      }],
      selected_endpoint_id: 'endpoint-1',
      selected_source: 'default',
      preference_endpoint_id: null,
      default_endpoint_id: 'endpoint-1',
    }, false, false);

    expect(result).toEqual({
      initialModel: 'family:endpoint-1',
      models: [{ modelKey: 'family:endpoint-1', displayName: '家庭 DeepSeek Flash' }],
      status: 'ready',
    });
  });

  it('does not invent a model when the family has choices but no default or preference', () => {
    const result = buildFamilyModelAvailability({
      endpoints: [{
        endpoint_id: 'endpoint-1',
        display_name: '家庭 DeepSeek Flash',
        provider: 'deepseek',
        model_id: 'deepseek-chat',
        enabled: true,
        sort_order: 0,
        model_key: 'family:endpoint-1',
      }],
      selected_endpoint_id: null,
      selected_source: null,
      preference_endpoint_id: null,
      default_endpoint_id: null,
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
