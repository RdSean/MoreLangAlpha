import { useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useIsMobile } from '@/hooks/useIsMobile';
import { usePreferences } from '@/hooks/usePreferences';
import { queryKeys } from '@/lib/queryKeys';
import type { UserPreferences } from '@/types/api';
import WorkspaceOverview from './WorkspaceOverview';
import DashboardCustom from './DashboardCustom';
import { useDashboardPrefsWriter } from './widgets/framework/dashboardPrefsWriter';
import { migrateDashboardPrefs } from './widgets/framework/migrations';
import { getPreset } from './widgets/presets';
import { DASHBOARD_PREFS_VERSION, type DashboardPrefs } from './widgets/types';

// Side-effect: ensure the widget registry is populated before any preset
// factory runs.
import './widgets/index';

/**
 * Dispatches between the classic workspace overview and the widget canvas.
 *
 * Upstream had the same shape with its finance dashboard as the classic
 * branch; here the classic branch is this branch's own `WorkspaceOverview`.
 *
 * Rules, all of which fix a real bug upstream:
 * - Mobile always renders classic and never sees the toggle.
 * - Absent or legacy prefs resolve to classic, so the first load after this
 *   ships cannot silently rearrange someone's dashboard.
 * - A write is refused until prefs load, and the toggle re-reads the freshest
 *   cache before writing, so a cross-tab edit (or a pending debounce in this
 *   tab) is not clobbered by a render-time snapshot.
 */
export default function DashboardRouter() {
  const isMobile = useIsMobile();
  const { preferences, isLoading } = usePreferences();
  const { writeDashboardPrefs } = useDashboardPrefsWriter();
  const queryClient = useQueryClient();

  const rawOther = (preferences as { other_preference?: { dashboard?: unknown } } | null)
    ?.other_preference;
  const parsed: DashboardPrefs | null = migrateDashboardPrefs(rawOther?.dashboard ?? null);
  const mode: 'classic' | 'custom' = parsed?.mode ?? 'classic';

  const onModeChange = useCallback(
    (next: 'classic' | 'custom') => {
      // Cold-cache gate: refuse the toggle until prefs load so we don't build
      // the dashboard payload from nothing and overwrite the user's saved
      // layout (the server replaces the dashboard key wholesale). The toggle
      // is disabled in the UI while isLoading, so this is defense-in-depth.
      if (isLoading) return;
      // Replay-aware: re-read the freshest cache so a cross-tab edit (or
      // pending debounce in this tab) that already updated the dashboard
      // sub-object isn't replaced with the render-time snapshot.
      const fresh = queryClient.getQueryData<UserPreferences>(queryKeys.user.preferences());
      const freshOther =
        (fresh?.other_preference as Record<string, unknown> | undefined) ?? rawOther;
      const freshDashboardRaw = (freshOther?.dashboard as unknown) ?? null;
      const baseDashboard: Partial<DashboardPrefs> =
        migrateDashboardPrefs(freshDashboardRaw) ?? parsed ?? {};
      const firstFlipToCustom =
        next === 'custom' && (!baseDashboard.widgets || baseDashboard.widgets.length === 0);
      const seed = firstFlipToCustom ? getPreset('family-desk') : null;
      const dashboard: DashboardPrefs = {
        version: DASHBOARD_PREFS_VERSION,
        mode: next,
        widgets: seed ? seed.widgets : (baseDashboard.widgets ?? []),
        layouts: seed ? seed.layouts : (baseDashboard.layouts ?? {}),
        lastBreakpoint: baseDashboard.lastBreakpoint,
        history: baseDashboard.history,
      };
      writeDashboardPrefs(dashboard, {
        // undefined = cold (writer refuses); null = warm, no saved prefs yet.
        fallbackOther:
          preferences === null
            ? undefined
            : ((rawOther as Record<string, unknown> | undefined) ?? null),
      });
    },
    [writeDashboardPrefs, parsed, preferences, rawOther, isLoading, queryClient],
  );

  // Mobile: classic always, and the toggle is not surfaced.
  if (isMobile) return <WorkspaceOverview />;

  if (mode === 'custom') return <DashboardCustom mode={mode} onModeChange={onModeChange} />;

  return <WorkspaceOverview layoutToggle={{ mode, onModeChange }} />;
}
