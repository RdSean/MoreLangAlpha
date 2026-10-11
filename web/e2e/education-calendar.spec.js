import { test, expect, mockAPI, resetMockServer } from './fixtures.js';
import { Buffer } from 'node:buffer';

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
  await page.addInitScript(() => {
    const send = window.XMLHttpRequest.prototype.send;
    window.XMLHttpRequest.prototype.send = function (body) {
      if (body instanceof FormData && body.get('file') instanceof File) {
        window.__educationCalendarUpload = Object.fromEntries([...body.entries()].map(([key, value]) => [key, value instanceof File ? value.name : value]));
      }
      return send.call(this, body);
    };
  });
  await mockAPI(page, {
    'GET /auth/me': role === 'parent' ? parent : student,
    'GET /auth/members': [parent, student],
    'GET /auth/children': [],
    'GET /education/dictionaries': { timezone: 'Asia/Tokyo', subjects: [], grade_levels: [], practice_sources: [] },
    'GET /education/learning': [],
    'GET /education/tasks/calendar': { days: [], stats: { total_points: 4 } },
    'GET /education/calendar/sources': route => route.fulfill({ json: state.imported ? [source] : [] }),
    'POST /education/calendar/sources': async route => {
      // Chromium 90 omits multipart file bodies from the intercepted request.
      const upload = await page.evaluate(() => window.__educationCalendarUpload);
      expect(upload.file).toBe('classes.ics');
      if (state.imported) expect(upload.source_id).toBe(source.source_id);
      const body = route.request().postData();
      if (body !== null) {
        expect(body).toContain('classes.ics');
        if (state.imported) expect(body).toContain(source.source_id);
      }
      state.imported = true;
      await route.fulfill({ json: source });
    },
    [`DELETE /education/calendar/sources/${source.source_id}`]: async route => { state.imported = false; await route.fulfill({ status: 204 }); },
    'GET /education/calendar/events': route => route.fulfill({ json: { household_id: 'family-1', timezone: 'Asia/Tokyo', events: state.imported ? events : [] } }),
  });
}

for (const theme of ['light', 'nasa']) for (const width of [375, 1440]) {
  test.describe(`${theme} ${width}px household calendar`, () => {
  test.use({ isMobile: width === 375, hasTouch: width === 375 });
  test(`parent ${width}px imports, updates, shares and removes a household calendar`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.addInitScript(value => localStorage.setItem('theme', value), theme);
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
    const day = page.getByRole('button', { name: /2026-10-10.*2项日程/ });
    const preview = day.getByText(events[0].title);
    await expect(preview).toBeVisible();
    const truncation = await preview.evaluate(element => ({ overflow: getComputedStyle(element).textOverflow, fits: element.clientWidth <= element.parentElement.clientWidth, clipped: element.scrollWidth > element.clientWidth }));
    expect(truncation.overflow).toBe('ellipsis');
    expect(truncation.fits).toBe(true);
    expect(truncation.clipped).toBe(true);
    const cellHeight = await day.evaluate(element => element.getBoundingClientRect().height);
    if (width === 375) expect(cellHeight).toBe(128);
    else {
      expect(cellHeight).toBeGreaterThan(100);
      const emptyHeight = await page.getByRole('button', { name: '2026-10-09' }).evaluate(element => element.getBoundingClientRect().height);
      expect(cellHeight).toBeCloseTo(emptyHeight, 1);
      const calendar = await page.getByRole('region', { name: '作业日历', exact: true }).boundingBox();
      const notebook = await page.getByRole('region', { name: '当天作业本' }).boundingBox();
      expect(notebook.x).toBeGreaterThan(calendar.x + calendar.width);
      expect(Math.abs(calendar.y - notebook.y)).toBeLessThan(2);
    }
    expect(await day.locator('[title]').first().locator('span').first().evaluate(element => getComputedStyle(element).backgroundColor)).toBe(theme === 'nasa' ? 'rgb(214, 58, 44)' : await day.evaluate(element => {
      const sample = document.createElement('span');
      sample.style.backgroundColor = 'var(--color-accent-primary)';
      element.append(sample);
      const color = getComputedStyle(sample).backgroundColor;
      sample.remove();
      return color;
    }));
    const summary = page.locator('summary').filter({ hasText: events[0].title });
    if (width === 375) await summary.tap();
    else await summary.click();
    await expect(page.getByText(events[0].location)).toBeVisible();
    expect(await page.getByTestId('education-page').evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`shared-calendar-${width}.png`), animations: 'disabled' });
    await page.getByRole('button', { name: /2026-10-11/ }).click();
    await expect(page.getByRole('region', { name: '当天家庭日程' }).getByText('秋季假期')).toBeVisible();
    await expect(page.locator('summary').filter({ hasText: events[0].title })).toHaveCount(0);
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
    await page.addInitScript(value => localStorage.setItem('theme', value), theme);
    await setup(page, 'student', { imported: true });
    await page.goto('/education', { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('heading', { name: '我的作业' })).toHaveCount(0);
    const calendar = page.getByRole('region', { name: '作业日历', exact: true });
    await expect(calendar).toBeVisible();
    const calendarBounds = await calendar.boundingBox();
    expect(calendarBounds.y + calendarBounds.height).toBeGreaterThan(1000);
    const calendarScroll = await page.getByTestId('education-page').evaluate(element => ({ scroll: element.scrollHeight, visible: element.clientHeight }));
    expect(calendarScroll.scroll).toBeGreaterThan(calendarScroll.visible);
    await page.screenshot({ path: testInfo.outputPath(`student-calendar-top-${width}.png`), animations: 'disabled' });
    const summary = page.locator('summary').filter({ hasText: events[0].title });
    await expect(summary).toBeVisible();
    await summary.focus();
    await page.keyboard.press('Enter');
    await expect(page.getByText(events[0].location)).toBeVisible();
    await expect(page.getByLabel('选择孩子')).toHaveCount(0);
    await expect(page.locator('a[href="/education/learn"]').last()).toBeVisible();
    expect(await page.getByTestId('education-page').evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`student-calendar-${width}.png`), animations: 'disabled' });
  });
  });
}

for (const theme of ['light', 'nasa']) test.describe(`${theme} tablet gestures and homework drawer`, () => {
  test.use({ hasTouch: true });
  test('swipes real touch input and opens the drawer without navigating away', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 820, height: 1180 });
    await page.addInitScript(value => localStorage.setItem('theme', value), theme);
    await setup(page, 'parent', { imported: true });
    await page.goto('/education', { waitUntil: 'domcontentloaded' });
    const grid = page.getByLabel('选择作业日期');
    await expect(page.getByRole('button', { name: /2026-10-10/ })).toBeVisible();
    const box = await grid.boundingBox();
    const cdp = await page.context().newCDPSession(page);
    const swipe = async (dx, dy = 0) => {
      const x = box.x + box.width / 2, y = box.y + 60;
      await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y }] });
      for (let step = 1; step <= 5; step++) await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: x + dx * step / 5, y: y + dy * step / 5 }] });
      await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    };
    await swipe(-180);
    await expect(page.getByRole('button', { name: '2026-11-01' })).toHaveAttribute('aria-pressed', 'true');
    await swipe(180);
    await expect(page.getByRole('button', { name: '2026-10-01' })).toHaveAttribute('aria-pressed', 'true');
    await swipe(10, 100);
    await expect(page.getByRole('button', { name: '2026-10-01' })).toHaveAttribute('aria-pressed', 'true');
    await page.getByRole('button', { name: '2026-10-23' }).dblclick();
    const drawer = page.getByRole('dialog');
    await expect(drawer.getByLabel('截止时间')).toHaveValue('2026-10-23T20:00');
    expect(await drawer.evaluate(element => Math.round(element.getBoundingClientRect().right))).toBe(820);
    await page.screenshot({ path: testInfo.outputPath('homework-drawer.png'), animations: 'disabled' });
    await page.keyboard.press('Escape');
    await expect(drawer).toHaveCount(0);
    await page.getByRole('button', { name: '创建作业', exact: true }).click();
    await expect(drawer.getByLabel('截止时间')).toHaveValue('2026-10-23T20:00');
    await expect(page).toHaveURL(/\/education$/);
    await cdp.detach();
  });

  test('student tablet scrolls the calendar and swipes months', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 820, height: 1180 });
    await page.addInitScript(value => localStorage.setItem('theme', value), theme);
    await setup(page, 'student', { imported: true });
    await page.goto('/education');
    const calendar = page.getByRole('region', { name: '作业日历', exact: true });
    await expect(page.getByRole('button', { name: /2026-10-10/ })).toBeVisible();
    const box = await calendar.boundingBox();
    expect(box.y + box.height).toBeGreaterThan(1180);
    await page.screenshot({ path: testInfo.outputPath('student-tablet-calendar.png'), animations: 'disabled' });
    const cdp = await page.context().newCDPSession(page);
    const x = box.x + box.width / 2, y = box.y + 160;
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y }] });
    for (let step = 1; step <= 5; step++) await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: x - 180 * step / 5, y }] });
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    await expect(page.getByRole('button', { name: '2026-11-01' })).toHaveAttribute('aria-pressed', 'true');
    const sixWeekBox = await calendar.boundingBox();
    const rows = page.getByLabel('选择作业日期').locator('button');
    const heights = await rows.evaluateAll(elements => elements.map(element => element.getBoundingClientRect().height));
    expect(Math.max(...heights) - Math.min(...heights)).toBeLessThan(1);
    expect(sixWeekBox.y + sixWeekBox.height).toBeGreaterThan(1180);
    const shell = page.getByTestId('education-page');
    await shell.evaluate(element => { element.scrollTop = 300; });
    await expect.poll(() => shell.evaluate(element => element.scrollTop)).toBeGreaterThan(0);
    await expect(page.getByRole('button', { name: '2026-11-01' })).toHaveAttribute('aria-pressed', 'true');
    await cdp.detach();
  });

  for (const role of ['parent', 'student']) test(`${role} scrolls long homework independently and keeps a six-week calendar bounded`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.addInitScript(value => localStorage.setItem('theme', value), theme);
    await setup(page, role, { imported: true });
    const tasks = Array.from({ length: 24 }, (_, i) => ({ task_id: `long-${i}`, assigned_student_id: 'student-1', title: `数学练习 ${i + 1}`, description: '家庭作业内容。'.repeat(30), subject_code: 'math', status: 'open', due_at: '2026-11-01T11:00:00Z', occurrence_date: '2026-11-01' }));
    await mockAPI(page, { 'GET /education/tasks/calendar': { days: [{ date: '2026-11-01', tasks, task_count: 24, completed_count: 0 }], stats: { total_points: 4 } } });
    await page.goto('/education', { waitUntil: 'domcontentloaded' });
    await page.getByRole('button', { name: '下个月' }).click();
    const calendar = page.getByRole('region', { name: '作业日历', exact: true });
    const before = await calendar.boundingBox();
    const pane = page.getByLabel('作业与教材', { exact: true });
    await expect(pane.getByText('数学练习 1', { exact: true })).toBeVisible();
    expect(await pane.evaluate(element => element.scrollHeight > element.clientHeight)).toBe(true);
    await pane.hover();
    await page.mouse.wheel(0, 900);
    await expect.poll(() => pane.evaluate(element => element.scrollTop)).toBeGreaterThan(0);
    expect(await calendar.boundingBox()).toEqual(before);
    if (role === 'parent') expect(before.y + before.height).toBeLessThanOrEqual(800);
    else expect(before.y + before.height).toBeGreaterThan(800);
    expect(await page.getByTestId('education-page').evaluate(element => element.scrollWidth <= element.clientWidth && element.scrollTop === 0)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath('six-week-calendar.png'), animations: 'disabled' });
  });
});
