import { expect, mockAPI, resetMockServer, test } from './fixtures.js';

const parent = { user_id: 'theme-parent', name: 'Mission Test', email: 'theme@example.test', role: 'parent', household_id: 'theme-family', has_api_key: true, onboarding_completed: true };
test.beforeEach(async () => resetMockServer());

for (const width of [375, 768, 1024, 1440]) {
  test(`${width}px switches themes in settings and persists across pages`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await page.emulateMedia({ colorScheme: 'dark' });
    await mockAPI(page, { 'GET /auth/me': parent, 'GET /users/me': parent });
    await page.goto('/settings');
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'quiet');
    await page.getByRole('button', { name: /NASA Mission/ }).click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'nasa');
    await page.reload();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'nasa');
    expect(await page.evaluate(() => getComputedStyle(document.body).fontFamily)).toContain('Helvetica');
    expect(await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--color-accent-primary').trim())).toBe('#D63A2C');
    for (const path of ['/chat', '/documents', '/plugins', '/automations', '/dashboard']) {
      await page.goto(path, { waitUntil: 'domcontentloaded' });
      await expect(page.locator('html')).toHaveAttribute('data-theme', 'nasa');
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    }
    await page.goto('/settings');
    await page.screenshot({ path: testInfo.outputPath(`settings-nasa-${width}.png`), animations: 'disabled' });
    await page.getByRole('button', { name: /Quiet Workspace/ }).click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'quiet');
    await page.reload();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'quiet');
  });
}
