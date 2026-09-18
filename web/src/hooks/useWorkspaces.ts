import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { queryKeys } from '../lib/queryKeys';
import { getWorkspaces } from '../pages/ChatAgent/utils/api';

interface UseWorkspacesOptions {
  limit?: number;
  offset?: number;
  sortBy?: string;
  includeFlash?: boolean;
  enabled?: boolean;
}

function isManagedExecutionWorkspace(workspace: { config?: unknown }): boolean {
  const config = workspace.config;
  return (
    typeof config === 'object'
    && config !== null
    && 'managed_execution' in config
  );
}

/**
 * Shared hook for workspace list queries.
 * Uses keepPreviousData for smooth pagination transitions.
 * All consumers with the same params share one cached entry.
 */
export function useWorkspaces({ limit = 20, offset = 0, sortBy = 'custom', includeFlash = false, enabled = true }: UseWorkspacesOptions = {}) {
  const params = { limit, offset, sortBy, includeFlash };
  return useQuery({
    queryKey: queryKeys.workspaces.list(params),
    queryFn: () => getWorkspaces(limit, offset, sortBy, includeFlash),
    select: (data) => {
      const workspaces = data.workspaces.filter(
        (workspace) => !isManagedExecutionWorkspace(workspace),
      );
      return {
        ...data,
        workspaces,
        total: Math.max(0, (data.total ?? workspaces.length) - (data.workspaces.length - workspaces.length)),
      };
    },
    enabled,
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  });
}
