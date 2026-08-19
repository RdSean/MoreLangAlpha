import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const state = vi.hoisted(() => ({
  member: { user_id: 'parent-1', name: '家长', role: 'parent' as 'parent' | 'student' } as { user_id: string; name: string; role: 'parent' | 'student' } | null,
  children: [] as Array<Record<string, unknown>>,
}));

vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ member: state.member, logout: vi.fn() }) }));
vi.mock('@/hooks/useUser', () => ({ useUser: () => ({ isLoading: false }) }));
vi.mock('@/hooks/usePreferences', () => ({ usePreferences: () => ({ isLoading: false }) }));
vi.mock('../panels/UserInfoTab', () => ({ UserInfoTab: () => <div /> }));
vi.mock('../panels/PreferencesTab', () => ({ PreferencesTab: () => <div /> }));
vi.mock('../panels/ModelTab', () => ({ ModelTab: () => <div /> }));
vi.mock('../panels/ExperimentsTab', () => ({ ExperimentsTab: () => <div /> }));
vi.mock('../queries', () => ({
  useFamilyChildren: () => ({ data: state.children, isLoading: false, isError: false, refetch: vi.fn() }),
  useCreateChildAccount: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useFamilyChildWorkspace: () => ({ data: { workspace_id: 'flash-1', name: 'Flash', status: 'flash' }, isLoading: false, isError: false, refetch: vi.fn() }),
  useFamilyChildThreads: () => ({ data: { threads: [], total: 0, limit: 20, offset: 0 }, isLoading: false, isError: false, refetch: vi.fn() }),
}));

import Settings from '../Settings';

function Location() {
  return <output data-testid="location">{useLocation().search}</output>;
}

function renderSettings() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}><MemoryRouter initialEntries={['/settings?tab=family']}><Settings /><Location /></MemoryRouter></QueryClientProvider>);
}

beforeEach(() => {
  state.member = { user_id: 'parent-1', name: '家长', role: 'parent' };
  state.children = [{ user_id: 'student-1', email: null, username: 'xiaoming', name: '小明', role: 'student', household_id: 'household-1', flash_workspace: { workspace_id: 'flash-1', name: 'Flash', status: 'flash' } }];
});

describe('Settings family account route', () => {
  it('shows the parent tab and uses a deep-linkable child detail URL', () => {
    renderSettings();

    expect(screen.getByRole('button', { name: '家庭账户' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '查看对话' }));

    expect(screen.getByTestId('location')).toHaveTextContent('?tab=family&student=student-1');
    expect(screen.getByRole('heading', { name: '小明的对话记录' })).toBeInTheDocument();
  });
});
