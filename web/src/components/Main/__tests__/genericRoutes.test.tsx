import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { NAV_ITEMS } from '@/components/nav/navItems';

vi.mock('@/hooks/useIsMobile', () => ({ useIsMobile: () => true }));
vi.mock('@/hooks/useSyncUserLocale', () => ({ useSyncUserLocale: () => undefined }));
vi.mock('@/components/PageLoading/PageLoading', () => ({
  default: () => <div data-testid="page-loading" />,
}));
vi.mock('@/components/ui/ContextOverflowPill', () => ({
  ContextOverflowPill: () => null,
}));
vi.mock('@/pages/Dashboard/DashboardRouter', () => ({
  default: () => <div data-testid="dashboard-page" />,
}));
vi.mock('@/pages/ChatAgent/ChatAgent', () => ({
  default: () => <div data-testid="chat-page" />,
}));
vi.mock('@/pages/Automations/Automations', () => ({
  default: () => <div data-testid="automations-page" />,
}));
vi.mock('@/pages/Settings/Settings', () => ({
  default: () => <div data-testid="settings-page" />,
}));
vi.mock('@/pages/Documents/DocumentsPage', () => ({
  default: () => <div data-testid="documents-page" />,
}));
vi.mock('@/pages/Documents/DocumentDetailPage', () => ({
  default: () => <div data-testid="document-detail-page" />,
}));
vi.mock('@/pages/Education/EducationPage', () => ({
  default: () => <div data-testid="education-page" />,
}));
vi.mock('@/pages/Education/TextbooksPage', () => ({
  default: () => <div data-testid="textbook-library-page" />,
}));
vi.mock('@/pages/Education/TextbookWorkbenchPage', () => ({
  default: () => <div data-testid="textbook-workbench-page" />,
}));
vi.mock('@/pages/Education/LegacyTextbookRouteReset', () => ({
  default: () => <div data-testid="legacy-textbook-reset-page" />,
}));
vi.mock('@/pages/Education/StudentFlashChat', () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

import Main from '../Main';
import { preloadRouteChunk, routeChunks } from '../routeChunks';

function renderAt(pathname: string) {
  return render(
    <MemoryRouter initialEntries={[pathname]} future={{ v7_startTransition: true }}>
      <Main />
    </MemoryRouter>,
  );
}

describe('generic application routes', () => {
  it('keeps generic primary navigation plus the first-party education entry', () => {
    expect(NAV_ITEMS.map((item) => item.key)).toEqual([
      '/dashboard',
      '/chat',
      '/documents',
      '/textbooks',
      '/automations',
      '/education',
      // Added by the platform-core merge: the Plugins/MCP/Skills/Vault
      // configuration surface has its own entry.
      '/plugins',
    ]);
  });

  it.each(['/market', '/news/article-1'])('redirects retired finance route %s to the dashboard', async (pathname) => {
    renderAt(pathname);

    expect(await screen.findByTestId('dashboard-page')).toBeInTheDocument();
  });

  it.each([
    ['/chat', 'chat-page'],
    ['/documents', 'documents-page'],
    ['/documents/doc-1', 'document-detail-page'],
    ['/textbooks', 'textbook-library-page'],
    ['/automations', 'automations-page'],
    ['/education', 'education-page'],
    ['/settings', 'settings-page'],
  ])('preserves the %s route', async (pathname, pageTestId) => {
    renderAt(pathname);

    expect(await screen.findByTestId(pageTestId)).toBeInTheDocument();
  });

  it('opens a textbook directly in the workbench', async () => {
    renderAt('/textbooks/book-1');

    expect(await screen.findByTestId('textbook-workbench-page')).toBeInTheDocument();
  });

  it.each([
    '/textbooks/book-1/versions/version-1/processing',
    '/textbooks/book-1/versions/version-1/structure',
    '/textbooks/book-1/versions/version-1/candidates',
    '/textbooks/book-1/versions/version-1/knowledge/kp-1',
  ])('resets the retired textbook route %s', async (pathname) => {
    renderAt(pathname);

    expect(await screen.findByTestId('legacy-textbook-reset-page')).toBeInTheDocument();
  });

  it('preloads the documents route chunk', () => {
    const load = vi.spyOn(routeChunks, 'documents').mockResolvedValue({ default: () => <div /> });

    preloadRouteChunk('/documents');

    expect(load).toHaveBeenCalledOnce();
  });

  it('preloads the document detail route chunk for a nested document URL', () => {
    const load = vi.spyOn(routeChunks, 'documentDetail').mockResolvedValue({ default: () => <div /> });

    preloadRouteChunk('/documents/doc-1');

    expect(load).toHaveBeenCalledOnce();
  });

  it('preloads the workbench chunk for a nested textbook URL', () => {
    const load = vi.spyOn(routeChunks, 'textbookWorkbench').mockResolvedValue({ default: () => <div /> });

    preloadRouteChunk('/textbooks/book-1');

    expect(load).toHaveBeenCalledOnce();
  });

  it('preloads the reset chunk for a retired textbook URL', () => {
    const load = vi.spyOn(routeChunks, 'legacyTextbookReset').mockResolvedValue({ default: () => <div /> });

    preloadRouteChunk('/textbooks/book-1/versions/version-1/processing');

    expect(load).toHaveBeenCalledOnce();
  });
});
