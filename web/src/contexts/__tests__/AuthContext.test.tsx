import React, { type ReactElement } from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const apiGet = vi.fn();
const apiPost = vi.fn();

vi.mock('@/api/client', () => ({
  api: {
    defaults: { baseURL: '' },
    get: (...args: unknown[]) => apiGet(...args),
    post: (...args: unknown[]) => apiPost(...args),
  },
}));

const { AuthProvider, useAuth } = await import('../AuthContext');

const member = {
  user_id: 'parent-user',
  email: 'parent@example.test',
  name: 'Parent',
  role: 'parent',
  household_id: 'household-1',
};

function renderWithQueryClient(ui: ReactElement) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      {ui}
    </QueryClientProvider>,
  );
}

describe('AuthContext', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiGet.mockRejectedValue({ response: { status: 401 } });
  });

  it('restores the signed-in member from the local cookie session', async () => {
    apiGet.mockResolvedValue({ data: member });

    function Consumer() {
      const auth = useAuth();
      return <span data-testid="user">{auth.userId ?? 'none'}</span>;
    }

    renderWithQueryClient(<AuthProvider><Consumer /></AuthProvider>);

    await waitFor(() => expect(apiGet).toHaveBeenCalledWith('/api/v1/auth/me'));
    expect(screen.getByTestId('user')).toHaveTextContent('parent-user');
  });

  it('posts local credentials and retains the returned member', async () => {
    apiPost.mockResolvedValue({ data: member });
    let auth: ReturnType<typeof useAuth> | undefined;
    function Capture() {
      auth = useAuth();
      return null;
    }

    renderWithQueryClient(<AuthProvider><Capture /></AuthProvider>);
    await waitFor(() => expect(auth?.isInitialized).toBe(true));
    await act(async () => {
      await auth!.login('parent@example.test', 'a-long-enough-password');
    });

    expect(apiPost).toHaveBeenCalledWith('/api/v1/auth/login', {
      login_identifier: 'parent@example.test',
      password: 'a-long-enough-password',
    });
    await waitFor(() => expect(auth!.member).toEqual(member));
  });

  it('creates a family only through the parent registration endpoint', async () => {
    apiPost.mockResolvedValue({ data: member });
    let auth: ReturnType<typeof useAuth> | undefined;
    function Capture() {
      auth = useAuth();
      return null;
    }

    renderWithQueryClient(<AuthProvider><Capture /></AuthProvider>);
    await waitFor(() => expect(auth?.isInitialized).toBe(true));
    await act(async () => {
      await auth!.registerParent({
        email: 'parent@example.test',
        password: 'a-long-enough-password',
        name: 'Parent',
        householdName: 'Lee family',
        timezone: 'Asia/Tokyo',
      });
    });

    expect(apiPost).toHaveBeenCalledWith('/api/v1/auth/register-parent', {
      email: 'parent@example.test',
      password: 'a-long-enough-password',
      name: 'Parent',
      household_name: 'Lee family',
      timezone: 'Asia/Tokyo',
    });
  });
});
