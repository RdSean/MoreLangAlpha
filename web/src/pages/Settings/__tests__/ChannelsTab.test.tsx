import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const state = vi.hoisted(() => ({
  start: vi.fn(),
  poll: vi.fn(),
  cancel: vi.fn(),
  disconnect: vi.fn(),
  update: vi.fn(),
  refetch: vi.fn(),
  status: 'unlinked',
}));

vi.mock('../api', () => ({
  startWechatLinkAttempt: state.start,
  pollWechatLinkAttempt: state.poll,
  cancelWechatLinkAttempt: state.cancel,
  disconnectWechat: state.disconnect,
  updateWechatStatus: state.update,
}));

vi.mock('../queries', () => ({
  useWechatStatus: () => ({
    data: { channel_type: 'wechat', status: state.status, idle_timeout_seconds: 21600 },
    refetch: state.refetch,
  }),
}));

import { ChannelsTab } from '../panels/ChannelsTab';

beforeEach(() => {
  state.start.mockReset().mockResolvedValue({
    attempt_id: 'attempt-1', channel_type: 'wechat', status: 'waiting',
    qr_code_url: 'https://example.invalid/qr', expires_at: '2026-08-30T00:00:00Z',
  });
  state.poll.mockReset().mockResolvedValue({
    attempt_id: 'attempt-1', channel_type: 'wechat', status: 'linked',
    expires_at: '2026-08-30T00:00:00Z',
  });
  state.cancel.mockReset().mockResolvedValue(undefined);
  state.disconnect.mockReset().mockResolvedValue(undefined);
  state.update.mockReset().mockResolvedValue({});
  state.refetch.mockReset().mockResolvedValue({});
  state.status = 'unlinked';
});

describe('ChannelsTab', () => {
  it('keeps the QR code visible when a waiting poll omits its image URL', async () => {
    render(<ChannelsTab />);

    fireEvent.click(screen.getByRole('button', { name: 'Configure' }));

    expect(await screen.findByRole('img', { name: 'WeChat QR code' })).toHaveAttribute('src', 'https://example.invalid/qr');
    state.poll.mockResolvedValueOnce({ attempt_id: 'attempt-1', channel_type: 'wechat', status: 'waiting', expires_at: '2026-08-30T00:00:00Z' });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 2_200));
    });
    expect(screen.getByRole('img', { name: 'WeChat QR code' })).toHaveAttribute('src', 'https://example.invalid/qr');
  }, 7_000);

  it('allows an active binding to start a reconfiguration QR flow', async () => {
    state.status = 'active';
    render(<ChannelsTab />);

    fireEvent.click(screen.getByRole('button', { name: 'Configure' }));

    expect(await screen.findByRole('img', { name: 'WeChat QR code' })).toBeInTheDocument();
    expect(state.start).toHaveBeenCalledOnce();
  });
});
