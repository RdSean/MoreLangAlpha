import { test, expect, mockAPI, resetMockServer } from './fixtures.js';

const parent = { user_id: 'parent-1', name: '家长', role: 'parent', household_id: 'family-1', onboarding_completed: true, has_api_key: true };
const student = { ...parent, user_id: 'student-1', name: '小明', role: 'student' };
const source = { source_id: '64f3e502-187c-47af-bbe2-ad38f914cc1f', household_id: 'family-1', name: '学校课表', filename: 'classes.ics', event_count: 2, updated_at: '2026-10-10T00:00:00Z' };
const events = [
  { event_id: 'lesson', uid: 'lesson', source_id: source.source_id, source_name: source.name, title: '阅读课：分享本周的阅读笔记', description: '带上阅读笔记和课外读物。\n结束后到图书馆还书。', location: '学校图书馆 · 二楼阅读室', all_day: false, start_at: '2026-10-10T09:00:00+09:00', end_at: '2026-10-10T10:00:00+09:00', dates: ['2026-10-10'] },
  { event_id: 'holiday', uid: 'holiday', source_id: source.source_id, source_name: source.name, title: '秋季假期', description: '', location: '', all_day: true, start_at: '2026-10-10', end_at: '2026-10-12', dates: ['2026-10-10', '2026-10-11'] },
];
const file = { name: 'classes.ics', mimeType: 'text/calendar', buffer: Buffer.from('BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:lesson\r\nDTSTART:20261010T090000Z\r\nSUMMARY:Lesson\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n') };

async function setup(page, role, state) {
  await resetMockServer();
  await page.clock.setFixedTime(new Date('2026-10-10T06:00:00Z'));
  await mockAPI(page, {
    'GET /auth/me': role === 'parent' ? parent : student,
    'GET /auth/members': [parent, student],
    'GET /auth/children': [],
    'GET /education/dictionaries': { timezone: 'Asia/Tokyo', subjects: [], grade_levels: [], practice_sources: [] },
    'GET /education/learning': [],
    'GET /education/tasks/calendar': { days: [], stats: { total_points: 4 } },
    'GET /education/calendar/sources': route => route.fulfill({ json: state.imported ? [source] : [] }),
    'POST /education/calendar/sources': async route => {
      expect(route.request().postData()).toContain('classes.ics');
      if (state.imported) expect(route.request().postData()).toContain(source.source_id);
      state.imported = true;
      await route.fulfill({ json: source });
    },
    [`DELETE /education/calendar/sources/${source.source_id}`]: async route => { state.imported = false; await route.fulfill({ status: 204 }); },
    'GET /education/calendar/events': route => route.fulfill({ json: { household_id: 'family-1', timezone: 'Asia/Tokyo', events: state.imported ? events : [] } }),
  });
}

for (const width of [375, 1440]) {
  test.describe(`${width}px household calendar`, () => {
  test.use({ isMobile: width === 375, hasTouch: width === 375 });
  test(`parent ${width}px imports, updates, shares and removes a household calendar`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 });
    const state = { imported: false };
    await setup(page, 'parent', state);
    await page.goto('/settings?tab=family', { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('heading', { name: '家庭日历', exact: true })).toBeVisible();
    await page.getByLabel('选择 ICS 文件').setInputFiles(file);
    await expect(page.getByRole('status').filter({ hasText: '已保存' })).toBeVisible();
    await expect(page.getByText('学校课表', { exact: true })).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath(`family-calendar-${width}.png`), animations: 'disabled' });
    await page.getByRole('button', { name: '更新学校课表' }).click();
    await page.getByLabel('选择 ICS 文件').setInputFiles(file);
    await expect(page.getByRole('status').filter({ hasText: '已保存' })).toBeVisible();
    await page.goto('/education', { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('button', { name: /2026-10-10.*2项日程/ })).toBeVisible();
    await page.getByLabel('选择孩子').selectOption('student-1');
    await expect(page.getByText(events[0].title)).toBeVisible();
    if (width === 375) await page.getByText(events[0].title).tap();
    else await page.getByText(events[0].title).click();
    await expect(page.getByText(events[0].location)).toBeVisible();
    expect(await page.getByTestId('education-page').evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`shared-calendar-${width}.png`), animations: 'disabled' });
    await page.getByRole('button', { name: /2026-10-11/ }).click();
    await expect(page.getByText('秋季假期')).toBeVisible();
    await expect(page.getByText(events[0].title)).toHaveCount(0);
    await page.goto('/settings?tab=family', { waitUntil: 'domcontentloaded' });
    await page.getByRole('button', { name: '移除学校课表' }).click();
    await page.getByRole('button', { name: '确认移除' }).click();
    await expect(page.getByText('暂无家庭日历')).toBeVisible();
    await page.goto('/education', { waitUntil: 'domcontentloaded' });
    await expect(page.getByText('秋季假期')).toHaveCount(0);
    await expect(page.getByLabel('累计积分', { exact: true })).toContainText('4');
  });

  test(`student ${width}px reads shared events and uses keyboard details`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 });
    await setup(page, 'student', { imported: true });
    await page.goto('/education', { waitUntil: 'domcontentloaded' });
    const summary = page.locator('summary').filter({ hasText: events[0].title });
    await expect(summary).toBeVisible();
    await summary.focus();
    await page.keyboard.press('Enter');
    await expect(page.getByText(events[0].location)).toBeVisible();
    await expect(page.getByLabel('选择孩子')).toHaveCount(0);
    expect(await page.getByTestId('education-page').evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`student-calendar-${width}.png`), animations: 'disabled' });
  });
  });
}
