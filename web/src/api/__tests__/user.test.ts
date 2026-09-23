import { describe, expect, it, vi } from 'vitest';
import type { Mock } from 'vitest';

vi.mock('@/api/client', () => ({
  api: {
    get: vi.fn(),
  },
}));

import { api } from '@/api/client';
import { getCurrentUser } from '../user';

const mockGet = api.get as Mock;

describe('getCurrentUser', () => {
  it('bounds the profile request so the app gate cannot hang forever', async () => {
    mockGet.mockResolvedValue({ data: { user_id: 'user-1' } });

    await getCurrentUser({ refresh_tier: true });

    expect(mockGet).toHaveBeenCalledWith('/api/v1/users/me', {
      params: { refresh_tier: true },
      timeout: 10_000,
    });
  });
});
