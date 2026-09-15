import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ArrowUpRight, BotMessageSquare, FolderOpen, TimerReset } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Loader } from '@/components/ui/loader';
import { useWorkspaces } from '@/hooks/useWorkspaces';
import { queryKeys } from '@/lib/queryKeys';
import { relativeTime } from '@/lib/format';
import { getRecentThreads } from '@/pages/ChatAgent/utils/api';
import type { Thread, ThreadsResponse, Workspace } from '@/types/api';
import LayoutModeToggle, { type LayoutToggle } from './components/LayoutModeToggle';

const RECENT_THREAD_LIMIT = 6;

interface WorkspaceOverviewProps {
  /**
   * Supplied by `DashboardRouter` on desktop. When absent — mobile, or the
   * page rendered on its own — the canvas switch is not shown.
   */
  layoutToggle?: LayoutToggle;
}

function threadTitle(thread: Thread, fallback: string): string {
  return thread.title || (thread as { first_query_content?: string }).first_query_content || fallback;
}

function WorkspaceRow({ workspace }: { workspace: Workspace }) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <button
      type="button"
      onClick={() => navigate(`/chat/${workspace.workspace_id}`)}
      className="flex min-w-0 items-center justify-between gap-3 border-b px-0 py-3 text-left transition-colors hover:bg-[var(--color-bg-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      style={{ borderColor: 'var(--color-border-muted)' }}
    >
      <span className="min-w-0">
        <span className="block truncate text-sm font-medium" style={{ color: 'var(--color-text-primary)' }}>
          {workspace.name || t('dashboard.overview.untitledWorkspace')}
        </span>
        {workspace.description ? (
          <span className="mt-0.5 block truncate text-sm" style={{ color: 'var(--color-text-secondary)' }}>
            {workspace.description}
          </span>
        ) : null}
      </span>
      <ArrowUpRight className="size-4 shrink-0" aria-hidden="true" style={{ color: 'var(--color-text-tertiary)' }} />
    </button>
  );
}

function RecentThreadRow({ thread }: { thread: Thread }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const updated = relativeTime(thread.updated_at);

  return (
    <button
      type="button"
      onClick={() => navigate(`/chat/t/${thread.thread_id}`)}
      className="flex min-w-0 items-center justify-between gap-3 border-b px-0 py-3 text-left transition-colors hover:bg-[var(--color-bg-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      style={{ borderColor: 'var(--color-border-muted)' }}
    >
      <span className="min-w-0 truncate text-sm" style={{ color: 'var(--color-text-primary)' }}>
        {threadTitle(thread, t('dashboard.overview.untitledThread'))}
      </span>
      {updated ? (
        <span className="shrink-0 text-xs tabular-nums" style={{ color: 'var(--color-text-tertiary)' }}>
          {updated}
        </span>
      ) : null}
    </button>
  );
}

export default function WorkspaceOverview({ layoutToggle }: WorkspaceOverviewProps = {}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { data: workspacesData, isLoading: workspacesLoading } = useWorkspaces({ limit: 20 });
  const { data: threadsData, isLoading: threadsLoading } = useQuery<ThreadsResponse>({
    queryKey: queryKeys.threads.recent(RECENT_THREAD_LIMIT),
    queryFn: () => getRecentThreads(RECENT_THREAD_LIMIT),
    staleTime: 30_000,
  });

  const workspaces = useMemo(() => workspacesData?.workspaces ?? [], [workspacesData]);
  const recentThreads = useMemo(() => threadsData?.threads ?? [], [threadsData]);
  const fileWorkspace = workspaces.find((workspace) => workspace.status !== 'flash');
  const isLoading = workspacesLoading || threadsLoading;

  return (
    <main
      data-testid="workspace-overview"
      className="h-full min-h-0 overflow-y-auto"
      style={{ backgroundColor: 'var(--color-bg-canvas)' }}
    >
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-10 px-4 py-8 sm:px-6 lg:px-8 lg:py-10">
        <header className="flex flex-col gap-3 border-b pb-6 sm:flex-row sm:items-end sm:justify-between" style={{ borderColor: 'var(--color-border-muted)' }}>
          <div className="max-w-2xl">
            <p className="text-xs font-medium uppercase" style={{ color: 'var(--color-text-tertiary)' }}>
              {t('dashboard.overview.eyebrow')}
            </p>
            <h1 className="title-font mt-2 text-2xl font-semibold sm:text-3xl" style={{ color: 'var(--color-text-primary)' }}>
              {t('dashboard.overview.heading')}
            </h1>
            <p className="mt-2 text-sm leading-6" style={{ color: 'var(--color-text-secondary)' }}>
              {t('dashboard.overview.description')}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-3">
            <span className="font-mono text-xs tabular-nums" style={{ color: 'var(--color-text-tertiary)' }}>
              {t('dashboard.overview.workspaceCount', { count: workspaces.length })}
            </span>
            {layoutToggle ? (
              <LayoutModeToggle mode={layoutToggle.mode} onModeChange={layoutToggle.onModeChange} />
            ) : null}
          </div>
        </header>

        <section aria-label={t('dashboard.overview.actionsLabel')} className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <Button className="h-auto min-h-24 justify-start gap-3 whitespace-normal px-4 py-4 text-left" onClick={() => navigate('/chat')}>
            <BotMessageSquare className="size-5 shrink-0" aria-hidden="true" />
            <span className="flex min-w-0 flex-col items-start gap-1">
              <span>{t('dashboard.overview.actions.chat.title')}</span>
              <span className="text-xs font-normal opacity-75">{t('dashboard.overview.actions.chat.description')}</span>
            </span>
          </Button>
          <Button variant="outline" className="h-auto min-h-24 justify-start gap-3 whitespace-normal px-4 py-4 text-left" onClick={() => navigate('/automations')}>
            <TimerReset className="size-5 shrink-0" aria-hidden="true" />
            <span className="flex min-w-0 flex-col items-start gap-1">
              <span>{t('dashboard.overview.actions.automations.title')}</span>
              <span className="text-xs font-normal" style={{ color: 'var(--color-text-secondary)' }}>{t('dashboard.overview.actions.automations.description')}</span>
            </span>
          </Button>
          <Button
            variant="outline"
            className="h-auto min-h-24 justify-start gap-3 whitespace-normal px-4 py-4 text-left"
            onClick={() => fileWorkspace && navigate(`/chat/${fileWorkspace.workspace_id}?panel=files`)}
            disabled={!fileWorkspace}
          >
            <FolderOpen className="size-5 shrink-0" aria-hidden="true" />
            <span className="flex min-w-0 flex-col items-start gap-1">
              <span>{t('dashboard.overview.actions.files.title')}</span>
              <span className="text-xs font-normal" style={{ color: 'var(--color-text-secondary)' }}>
                {fileWorkspace
                  ? t('dashboard.overview.actions.files.description')
                  : t('dashboard.overview.actions.files.unavailable')}
              </span>
            </span>
          </Button>
        </section>

        <div className="grid grid-cols-1 gap-10 lg:grid-cols-[minmax(0,1.4fr)_minmax(16rem,0.8fr)]">
          <section aria-labelledby="recent-work-heading">
            <div className="flex items-baseline justify-between gap-4">
              <h2 id="recent-work-heading" className="title-font text-lg font-semibold" style={{ color: 'var(--color-text-primary)' }}>
                {t('dashboard.overview.recentWork')}
              </h2>
              <Button variant="ghost" size="sm" onClick={() => navigate('/chat')}>
                {t('dashboard.overview.viewAll')}
              </Button>
            </div>
            <div className="mt-3 border-t" style={{ borderColor: 'var(--color-border-muted)' }}>
              {isLoading ? (
                <div className="flex items-center gap-2 py-6 text-sm" style={{ color: 'var(--color-text-secondary)' }}>
                  <Loader size={16} />
                  {t('dashboard.overview.loading')}
                </div>
              ) : recentThreads.length > 0 ? (
                recentThreads.map((thread) => <RecentThreadRow key={thread.thread_id} thread={thread} />)
              ) : (
                <p className="py-6 text-sm" style={{ color: 'var(--color-text-secondary)' }}>
                  {t('dashboard.overview.recentEmpty')}
                </p>
              )}
            </div>
          </section>

          <section aria-labelledby="workspaces-heading">
            <h2 id="workspaces-heading" className="title-font text-lg font-semibold" style={{ color: 'var(--color-text-primary)' }}>
              {t('dashboard.overview.workspaces')}
            </h2>
            <div className="mt-3 border-t" style={{ borderColor: 'var(--color-border-muted)' }}>
              {isLoading ? (
                <div className="flex items-center gap-2 py-6 text-sm" style={{ color: 'var(--color-text-secondary)' }}>
                  <Loader size={16} />
                  {t('dashboard.overview.loading')}
                </div>
              ) : workspaces.length > 0 ? (
                workspaces.slice(0, 5).map((workspace) => <WorkspaceRow key={workspace.workspace_id} workspace={workspace} />)
              ) : (
                <p className="py-6 text-sm" style={{ color: 'var(--color-text-secondary)' }}>
                  {t('dashboard.overview.workspacesEmpty')}
                </p>
              )}
            </div>
          </section>
        </div>
      </div>
    </main>
  );
}
