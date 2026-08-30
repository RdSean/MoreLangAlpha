import { beforeEach, describe, expect, it, vi } from 'vitest';

const state = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn(), apiPatch: vi.fn(), apiDelete: vi.fn() }));
vi.mock('@/api/client', () => ({ api: { get: state.apiGet, post: state.apiPost, patch: state.apiPatch, delete: state.apiDelete } }));
vi.mock('@/pages/ChatAgent/utils/api/transport', () => ({ streamFetch: vi.fn() }));

import { pollWechatLinkAttempt, startWechatLinkAttempt } from '../api';
import { queryKeys } from '@/lib/queryKeys';

describe('channel settings API', () => {
  beforeEach(() => Object.values(state).forEach((mock) => mock.mockReset()));

  it('uses generic WeChat channel endpoints', async () => {
    state.apiPost.mockResolvedValue({ data: { attempt_id: 'attempt-1', status: 'waiting' } });
    await startWechatLinkAttempt();
    await pollWechatLinkAttempt('attempt-1', '1234');
    expect(state.apiPost).toHaveBeenNthCalledWith(1, '/api/v1/channels/wechat/link-attempts');
    expect(state.apiPost).toHaveBeenNthCalledWith(2, '/api/v1/channels/wechat/link-attempts/attempt-1/poll', { verification_code: '1234' });
  });

  it('keeps WeChat state below the settings namespace', () => {
    expect(queryKeys.settings.channels.wechat()).toEqual(['settings', 'channels', 'wechat']);
  });
});
