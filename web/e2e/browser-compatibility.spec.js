import { test, expect, mockAPI } from './fixtures.js';

const parent = { user_id: 'compat-parent', name: 'Parent', role: 'parent', household_id: 'compat-family' };

test.use({ viewport: { width: 820, height: 1180 }, hasTouch: true });

for (const theme of ['quiet', 'nasa']) for (const capability of ['array-at', 'media-events']) {
  test(`${theme} tablet opens chat without ${capability}`, async ({ page }) => {
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.addInitScript(({ value, theme }) => {
      localStorage.setItem('theme', theme);
      if (value === 'array-at') delete Array.prototype.at;
      if (value === 'media-events') {
        const matchMedia = window.matchMedia.bind(window);
        window.matchMedia = query => {
          const media = matchMedia(query);
          media.addEventListener = undefined;
          media.removeEventListener = undefined;
          return media;
        };
      }
    }, { value: capability, theme });
    await mockAPI(page, { 'GET /auth/me': parent });
    await page.goto('/chat');
    await expect(page.getByRole('heading', { name: 'Workspaces', exact: true })).toBeVisible();
    expect(errors).toEqual([]);
    await page.setViewportSize({ width: 600, height: 1000 });
    await expect(page.locator('.bottom-tab-bar')).toBeVisible();
    await page.setViewportSize({ width: 820, height: 1180 });
    await expect(page.locator('.bottom-tab-bar')).toHaveCount(0);
    expect(errors).toEqual([]);
  });
}
