import { defineConfig, devices } from '@playwright/test';

// Use a dedicated port so E2E tests never collide with the user's dev server
// on :5177 or other local services.
const E2E_PORT = 5176;

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  retries: process.env.CI ? 1 : 0,
  // Serial execution: the mock SSE server is shared state, so parallel
  // workers would clobber each other's scenarios via resetMockServer().
  workers: 1,
  use: {
    baseURL: `http://127.0.0.1:${E2E_PORT}`,
    trace: 'on-first-retry',
    // Allows compatibility regressions to run against a real older Chromium.
    launchOptions: { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined },
  },
  webServer: [
    {
      command: `pnpm dev --port ${E2E_PORT}`,
      port: E2E_PORT,
      // Always start fresh so E2E tests don't reuse a developer's live server.
      reuseExistingServer: false,
      env: {
        VITE_HOST_MODE: 'oss',
        VITE_API_BASE_URL: 'http://127.0.0.1:4100',
      },
    },
    {
      command: 'node e2e/mock-sse-server.js',
      port: 4100,
      reuseExistingServer: !process.env.CI,
    },
  ],
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
    {
      name: 'documents-mobile',
      testMatch: /(documents|education-textbook-learning)\.spec\.js/,
      use: { ...devices['iPhone 13'], browserName: 'chromium' },
    },
  ],
});
