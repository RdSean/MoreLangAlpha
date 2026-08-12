import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const useWorkspacesMock = vi.fn();
const getRecentThreadsMock = vi.fn();

vi.mock('@/hooks/useWorkspaces', () => ({
  useWorkspaces: () => useWorkspacesMock(),
}));
vi.mock('@/pages/ChatAgent/utils/api', () => ({
  getRecentThreads: (...args: unknown[]) => getRecentThreadsMock(...args),
}));

import WorkspaceOverview from '../WorkspaceOverview';

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{`${location.pathname}${location.search}`}</output>;
}

function renderOverview() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/dashboard']} future={{ v7_startTransition: true }}>
        <WorkspaceOverview />
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('WorkspaceOverview', () => {
  beforeEach(() => {
    useWorkspacesMock.mockReturnValue({
      data: {
        workspaces: [{ workspace_id: 'workspace-1', name: 'Home learning', description: 'Shared family learning space' }],
        total: 1,
      },
      isLoading: false,
    });
    getRecentThreadsMock.mockResolvedValue({
      threads: [{ thread_id: 'thread-1', workspace_id: 'workspace-1', title: 'Plan this week', updated_at: '2026-08-07T09:00:00Z' }],
      total: 1,
    });
  });

  it('offers generic workspace actions and recent work without the legacy dashboard shell', async () => {
    renderOverview();

    const overview = await screen.findByTestId('workspace-overview');
    expect(overview).not.toHaveClass('dashboard-container');
    expect(screen.getByRole('heading', { name: 'Workspace' })).toBeInTheDocument();
    expect(await screen.findByText('Plan this week')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /^Start a chat/ }));
    expect(screen.getByTestId('location')).toHaveTextContent('/chat');

    fireEvent.click(screen.getByRole('button', { name: /^Manage automations/ }));
    expect(screen.getByTestId('location')).toHaveTextContent('/automations');

    fireEvent.click(screen.getByRole('button', { name: /^Open workspace files/ }));
    expect(screen.getByTestId('location')).toHaveTextContent('/chat/workspace-1?panel=files');
  });
});
