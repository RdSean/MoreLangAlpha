import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, act } from '@testing-library/react';
import { QueryClientProvider, QueryClient } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { queryKeys } from '@/lib/queryKeys';

const prefsState: { current: { other_preference?: Record<string, unknown> | null } | null } = {
  current: {
    other_preference: {
      theme: 'dark',
      dashboard: { mode: 'classic', widgets: [], layouts: {} },
    },
  },
};
const loadingState = { isLoading: false };
const mockMutate = vi.fn();
let mockIsMobile = false;
const lastLayoutToggle: {
  current: { mode: string; onModeChange: (n: 'classic' | 'custom') => void } | null;
} = { current: null };

vi.mock('@/hooks/useIsMobile', () => ({
  useIsMobile: () => mockIsMobile,
}));
vi.mock('@/hooks/usePreferences', () => ({
  usePreferences: () => ({ preferences: prefsState.current, isLoading: loadingState.isLoading }),
}));
vi.mock('@/hooks/useUpdatePreferences', () => ({
  useUpdatePreferences: () => ({ mutate: mockMutate, isPending: false }),
}));
// The classic branch is this branch's own overview page; it takes the toggle as
// an optional prop and renders it in its header.
vi.mock('../WorkspaceOverview', () => ({
  __esModule: true,
  default: (props: {
    layoutToggle?: { mode: string; onModeChange: (n: 'classic' | 'custom') => void };
  }) => {
    if (props.layoutToggle) lastLayoutToggle.current = props.layoutToggle;
    return <div data-testid="classic-dashboard" />;
  },
}));
vi.mock('../DashboardCustom', () => ({
  __esModule: true,
  default: (props: { mode: string; onModeChange: (n: 'classic' | 'custom') => void }) => {
    lastLayoutToggle.current = { mode: props.mode, onModeChange: props.onModeChange };
    return <div data-testid="custom-dashboard" />;
  },
}));

import DashboardRouter from '../DashboardRouter';

function renderRouter(queryClient: QueryClient) {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <DashboardRouter />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function makeClient(): QueryClient {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { retry: false } },
  });
  qc.setQueryData(queryKeys.user.preferences(), prefsState.current);
  return qc;
}

describe('DashboardRouter', () => {
  beforeEach(() => {
    mockMutate.mockReset();
    mockIsMobile = false;
    loadingState.isLoading = false;
    lastLayoutToggle.current = null;
    prefsState.current = {
      other_preference: {
        theme: 'dark',
        dashboard: { mode: 'classic', widgets: [], layouts: {} },
      },
    };
  });
  afterEach(() => vi.restoreAllMocks());

  it('renders the classic overview when prefs.mode === classic', () => {
    const { getByTestId } = renderRouter(makeClient());
    expect(getByTestId('classic-dashboard')).toBeInTheDocument();
  });

  it('renders the widget canvas when prefs.mode === custom', () => {
    prefsState.current = {
      other_preference: { theme: 'dark', dashboard: { mode: 'custom', widgets: [], layouts: {} } },
    };
    const { getByTestId } = renderRouter(makeClient());
    expect(getByTestId('custom-dashboard')).toBeInTheDocument();
  });

  it('forces classic on mobile regardless of prefs.mode', () => {
    mockIsMobile = true;
    prefsState.current = {
      other_preference: { theme: 'dark', dashboard: { mode: 'custom', widgets: [], layouts: {} } },
    };
    const { getByTestId, queryByTestId } = renderRouter(makeClient());
    expect(getByTestId('classic-dashboard')).toBeInTheDocument();
    expect(queryByTestId('custom-dashboard')).toBeNull();
  });

  it('does not offer the toggle on mobile', () => {
    mockIsMobile = true;
    renderRouter(makeClient());
    expect(lastLayoutToggle.current).toBeNull();
  });

  it('defaults to classic when the stored dashboard block is absent or malformed', () => {
    prefsState.current = { other_preference: { theme: 'dark' } };
    const { getByTestId } = renderRouter(makeClient());
    expect(getByTestId('classic-dashboard')).toBeInTheDocument();
  });

  it('onModeChange reads the fresh cache, not the render-time copy', () => {
    const queryClient = makeClient();
    renderRouter(queryClient);
    expect(lastLayoutToggle.current).not.toBeNull();
    // Simulate a cross-tab edit: the cache gains a widget.
    act(() => {
      queryClient.setQueryData(queryKeys.user.preferences(), {
        other_preference: {
          theme: 'light',
          dashboard: {
            mode: 'classic',
            widgets: [{ id: 'w1', type: 'education.homeworkCalendar', config: {} }],
            layouts: { lg: [] },
          },
        },
      });
    });
    act(() => {
      lastLayoutToggle.current!.onModeChange('custom');
    });
    expect(mockMutate).toHaveBeenCalledTimes(1);
    const payload = mockMutate.mock.calls[0][0] as {
      other_preference: { theme?: string; dashboard?: { mode: string; widgets?: unknown[] } };
    };
    // Siblings stay out of the payload: the server merges, and replaying the
    // stale render-time copy is how a write used to revert them.
    expect(Object.keys(payload.other_preference)).toEqual(['dashboard']);
    expect(payload.other_preference.dashboard?.mode).toBe('custom');
    // The remote-added widget must survive the mode-toggle write.
    expect(payload.other_preference.dashboard?.widgets?.length).toBe(1);
  });

  it('seeds the family-desk preset on the first flip from an empty classic dashboard', () => {
    const queryClient = makeClient();
    renderRouter(queryClient);
    act(() => {
      lastLayoutToggle.current!.onModeChange('custom');
    });
    const payload = mockMutate.mock.calls[0][0] as {
      other_preference: { dashboard?: { mode: string; widgets?: unknown[] } };
    };
    expect(payload.other_preference.dashboard?.mode).toBe('custom');
    expect(payload.other_preference.dashboard?.widgets?.length ?? 0).toBeGreaterThan(0);
  });

  it('new-user warm cache: writes with seeded other_preference={dashboard:{...}}', () => {
    // Regression: the writer used to refuse when both freshOther and
    // fallbackOther were null, so a new user's first mode flip reverted on the
    // next refetch.
    prefsState.current = { other_preference: null };
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { retry: false } },
    });
    queryClient.setQueryData(queryKeys.user.preferences(), { other_preference: null });
    renderRouter(queryClient);
    act(() => {
      lastLayoutToggle.current!.onModeChange('custom');
    });
    expect(mockMutate).toHaveBeenCalledTimes(1);
    const payload = mockMutate.mock.calls[0][0] as {
      other_preference: { dashboard?: { mode: string; widgets?: unknown[] } };
    };
    expect(payload.other_preference.dashboard?.mode).toBe('custom');
    expect(payload.other_preference.dashboard?.widgets?.length ?? 0).toBeGreaterThan(0);
  });

  it('cold-cache gate: onModeChange is a no-op while preferences are loading', () => {
    // Regression: a fast click before the GET resolves would PUT a dashboard
    // built from nothing and wipe the saved layout (the server replaces the
    // dashboard key wholesale).
    loadingState.isLoading = true;
    prefsState.current = null;
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { retry: false } },
    });
    // Empty cache — simulates a cold load.
    renderRouter(queryClient);
    expect(lastLayoutToggle.current).not.toBeNull();
    act(() => {
      lastLayoutToggle.current!.onModeChange('custom');
    });
    expect(mockMutate).not.toHaveBeenCalled();
  });
});
