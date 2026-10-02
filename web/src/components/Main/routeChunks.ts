// Chunk thunks are shared by lazy routes and startup preloading. import() is
// deduplicated by the module system, so both paths reuse the same fetch.
export const routeChunks = {
  dashboard: () => import('../../pages/Dashboard/DashboardRouter'),
  chat: () => import('../../pages/ChatAgent/ChatAgent'),
  documents: () => import('../../pages/Documents/DocumentsPage'),
  documentDetail: () => import('../../pages/Documents/DocumentDetailPage'),
  automations: () => import('../../pages/Automations/Automations'),
  education: () => import('../../pages/Education/EducationPage'),
  plugins: () => import('../../pages/Plugins/Plugins'),
  connectors: () => import('../../pages/Plugins/Plugins'),
  createHomework: () => import('../../pages/Education/EducationPage'),
  textbooks: () => import('../../pages/Education/TextbooksPage'),
  textbookLibrary: () => import('../../pages/Education/TextbooksPage'),
  textbookWorkbench: () => import('../../pages/Education/TextbookWorkbenchPage'),
  legacyTextbookReset: () => import('../../pages/Education/LegacyTextbookRouteReset'),
  studentTextbookLearning: () => import('../../pages/Education/StudentTextbookLearningPage'),
  personalizedSummary: () => import('../../pages/Education/PersonalizedSummaryPage'),
  settings: () => import('../../pages/Settings/Settings'),
};

/** Warm a route chunk while the authenticated-user gate is resolving. */
export function preloadRouteChunk(pathname: string): void {
  const chunkFor: Record<string, () => Promise<unknown>> = routeChunks;
  const segments = pathname.split('/').filter(Boolean);
  const segment = segments[0] || 'dashboard';
  if (segment === 'documents' && segments[1]) {
    void routeChunks.documentDetail().catch(() => {});
    return;
  }
  if (segment === 'textbooks' && segments[1]) {
    const legacy = segments.includes('versions');
    void (legacy ? routeChunks.legacyTextbookReset() : routeChunks.textbookWorkbench()).catch(() => {});
    return;
  }
  void (chunkFor[segment] ?? routeChunks.dashboard)().catch(() => {});
}
