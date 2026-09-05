// Chunk thunks are shared by lazy routes and startup preloading. import() is
// deduplicated by the module system, so both paths reuse the same fetch.
export const routeChunks = {
  dashboard: () => import('../../pages/Dashboard/DashboardRouter'),
  chat: () => import('../../pages/ChatAgent/ChatAgent'),
  documents: () => import('../../pages/Documents/DocumentsPage'),
  automations: () => import('../../pages/Automations/Automations'),
  education: () => import('../../pages/Education/EducationPage'),
  createHomework: () => import('../../pages/Education/EducationPage'),
  textbookLibrary: () => import('../../pages/Education/TextbooksPage'),
  textbookDetail: () => import('../../pages/Education/TextbookDetailPage'),
  studentLearning: () => import('../../pages/Education/StudentLearningPage'),
  settings: () => import('../../pages/Settings/Settings'),
};

/** Warm a route chunk while the authenticated-user gate is resolving. */
export function preloadRouteChunk(pathname: string): void {
  const chunkFor: Record<string, () => Promise<unknown>> = routeChunks;
  const segment = pathname.split('/')[1] || 'dashboard';
  void (chunkFor[segment] ?? routeChunks.dashboard)();
}
