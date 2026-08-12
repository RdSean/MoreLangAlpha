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
vi.mock('@/pages/Education/EducationPage', () => ({
  default: () => <div data-testid="education-page" />,
}));
vi.mock('@/pages/Education/StudentFlashChat', () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

import Main from '../Main';

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
      '/automations',
      '/education',
    ]);
  });

  it.each(['/market', '/news/article-1'])('redirects retired finance route %s to the dashboard', async (pathname) => {
    renderAt(pathname);

    expect(await screen.findByTestId('dashboard-page')).toBeInTheDocument();
  });

  it.each([
    ['/chat', 'chat-page'],
    ['/automations', 'automations-page'],
    ['/education', 'education-page'],
    ['/settings', 'settings-page'],
  ])('preserves the %s route', async (pathname, pageTestId) => {
    renderAt(pathname);

    expect(await screen.findByTestId(pageTestId)).toBeInTheDocument();
  });
});
