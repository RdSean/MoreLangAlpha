import { test, expect, mockAPI, resetMockServer } from './fixtures.js';
import { sampleWorkspace } from './helpers/mockResponses.js';

const workspace = sampleWorkspace({
  name: 'Family Learning',
  description: 'Shared learning workspace',
});

async function loadWorkspaceOverview(page) {
  await mockAPI(page, {
    'GET /workspaces': { workspaces: [workspace], total: 1, limit: 20, offset: 0 },
    'GET /threads/recent': { threads: [], total: 0 },
  });
  await page.goto('/dashboard');
  await expect(page.getByTestId('workspace-overview')).toBeVisible();
}

test.beforeEach(async () => {
  await resetMockServer();
});

test.describe('Generic workspace surface', () => {
  test('desktop dashboard has workspace actions and no finance surface', async ({ page }) => {
    await loadWorkspaceOverview(page);

    await expect(page.getByRole('heading', { name: 'Workspace', exact: true })).toBeVisible();
    await expect(page.getByText('Family Learning', { exact: true })).toBeVisible();
    await expect(page.locator('a[href*="/market"]')).toHaveCount(0);
    await expect(page.getByText('Portfolio', { exact: true })).toHaveCount(0);
    await expect(page.getByText('Watchlist', { exact: true })).toHaveCount(0);

    await page.getByRole('button', { name: /Start a chat/i }).click();
    await expect(page).toHaveURL(/\/chat$/);

    await page.goto('/dashboard');
    await page.getByRole('button', { name: /Manage automations/i }).click();
    await expect(page).toHaveURL(/\/automations$/);
  });

  test('mobile workspace actions reach chat and automations', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await loadWorkspaceOverview(page);

    await page.getByRole('button', { name: /Start a chat/i }).click();
    await expect(page).toHaveURL(/\/chat$/);

    await page.goto('/dashboard');
    await page.getByRole('button', { name: /Manage automations/i }).click();
    await expect(page).toHaveURL(/\/automations$/);
  });
});
