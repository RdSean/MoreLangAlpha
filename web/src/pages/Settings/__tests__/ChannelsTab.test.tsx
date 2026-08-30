import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const state = vi.hoisted(() => ({
  start: vi.fn(),
  poll: vi.fn(),
  cancel: vi.fn(),
  disconnect: vi.fn(),
  update: vi.fn(),
  refetch: vi.fn(),
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
    data: { channel_type: 'wechat', status: 'unlinked', idle_timeout_seconds: 21600 },
    refetch: state.refetch,
  }),
}));

import { ChannelsTab } from '../panels/ChannelsTab';

beforeEach(() => {
  state.start.mockReset().mockResolvedValue({
    attempt_id: 'attempt-1', channel_type: 'wechat', status: 'verification_required',
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
});

describe('ChannelsTab', () => {
  it('closes and refreshes after a manually submitted verification code links', async () => {
    render(<ChannelsTab />);

    fireEvent.click(screen.getByRole('button', { name: 'Configure WeChat' }));
    const code = await screen.findByLabelText('Enter the code shown in WeChat');
    fireEvent.change(code, { target: { value: '123456' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(state.refetch).toHaveBeenCalledOnce());
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
