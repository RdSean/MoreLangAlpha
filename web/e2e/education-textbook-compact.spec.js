import { expect, resetMockServer, test } from './fixtures.js';
import { installProcessingMocks, processingJob } from './helpers/textbookProcessingFixtures.js';

test.use({ locale: 'zh-CN' });

test.beforeEach(async () => { await resetMockServer(); });
test.afterEach(async ({ page }) => { await page.close(); await resetMockServer(); });

for (const theme of ['light', 'dark']) {
  for (const width of [375, 1440]) {
    test(`${theme} ${width}px completed batch has one screen summary and manual learning entry`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: width === 375 ? 812 : 900 });
      await page.addInitScript((value) => localStorage.setItem('theme', value), theme);
      const base = processingJob({ kind: 'materials' });
      const now = new Date().toISOString();
      const snapshot = { ...base, status: 'succeeded', succeeded_items: 400, total_items: 400, finished_at: now,
        token_usage: { status: 'available', input_tokens: 24000, output_tokens: 4000, total_tokens: 28000, recorded_calls: 40 },
        items: Array.from({ length: 400 }, (_, index) => ({ ...base.items[0], item_id: `item-${index + 1}`,
          position: index + 1, skill_kp_id: index ? `kp-${index}` : 'reading', status: 'succeeded', finished_at: now,
          timing_summary: { ...base.items[0].timing_summary, terminal_at: now, total_ms: 12000 } })) };
      await installProcessingMocks(page, { getJob: () => snapshot, ready: true });
      await page.goto('/textbooks/book-1?activity=job-1&panel=processing&kp=reading&view=source');
      const timeline = page.getByRole('region', { name: '教材处理时间线' });
      const enter = timeline.getByRole('button', { name: '进入学习空间', exact: true });
      await expect(enter).toBeVisible();
      await expect(timeline.getByText('28,000', { exact: true })).toBeVisible();
      await expect(timeline.getByText('总耗时', { exact: true })).toBeVisible();
      const fit = await timeline.getByTestId('book-processing-scroll').evaluate((element) => element.scrollHeight <= element.clientHeight + 2);
      expect(fit).toBe(true);
      await expect(page.getByRole('button', { name: '活动', exact: true })).toHaveCount(0);
      await expect(timeline.getByRole('list', { name: '服务里程碑' }).getByRole('listitem')).toHaveCount(6);
      await page.screenshot({ path: testInfo.outputPath(`completed-${theme}-${width}.png`), animations: 'disabled' });
      await expect(page).toHaveURL(/panel=processing/);
      await enter.click();
      await expect(page).not.toHaveURL(/activity=|panel=/);
      await expect(page.getByRole('complementary', { name: '教材处理活动' })).toHaveCount(0);
      await expect(page.getByRole('article', { name: '阅读 原文阅读' })).toBeVisible();
      await expect(page.getByRole('tab', { name: '知识点', exact: true })).toBeVisible();
      await expect(page.getByText('Reading（1）', { exact: true })).toBeVisible();
    });
  }
}

test('English locale, reduced motion and missing tokens remain explicit', async ({ page }) => {
  await page.context().addCookies([{ name: 'locale', value: 'en-US', domain: '127.0.0.1', path: '/' }]);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  const base = processingJob({ kind: 'materials' });
  const now = new Date().toISOString();
  const snapshot = { ...base, status: 'succeeded', succeeded_items: 1, finished_at: now,
    items: [{ ...base.items[0], status: 'succeeded', finished_at: now }] };
  await installProcessingMocks(page, { getJob: () => snapshot, ready: true });
  await page.goto('/textbooks/book-1?activity=job-1&panel=processing');
  const timeline = page.getByRole('region', { name: 'Textbook processing timeline' });
  await expect(timeline.getByRole('button', { name: 'Enter learning space', exact: true })).toBeVisible();
  await expect(timeline.getByText('Token usage', { exact: true })).toBeVisible();
  await expect(timeline.locator('.book-processing-completion dd').last()).toHaveText('Not recorded');
  await expect(timeline.getByText('PDF · 24 pages', { exact: true })).toBeVisible();
});

test('short viewport allows safe scrolling to completion actions', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 420 });
  const base = processingJob({ kind: 'materials' });
  const snapshot = { ...base, status: 'partially_succeeded', succeeded_items: 1, finished_at: new Date().toISOString(),
    token_usage: { status: 'partial', input_tokens: 20, output_tokens: 7, total_tokens: 27, recorded_calls: 1 },
    items: [{ ...base.items[0], status: 'succeeded' }] };
  await installProcessingMocks(page, { getJob: () => snapshot, ready: true });
  await page.goto('/textbooks/book-1?activity=job-1&panel=processing');
  const timeline = page.getByRole('region', { name: '教材处理时间线' });
  await expect(timeline.getByText('部分未记录', { exact: true })).toBeVisible();
  const enter = timeline.getByRole('button', { name: '进入学习空间', exact: true });
  await enter.scrollIntoViewIfNeeded();
  await expect(enter).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(375);
});
