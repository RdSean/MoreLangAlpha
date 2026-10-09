import { configureSSE, expect, getCapturedRequests, mockAPI, resetMockServer, test } from './fixtures.js';
import { activityPage, event, installProcessingMocks, json, processingJob } from './helpers/textbookProcessingFixtures.js';

test.use({ screenshot: 'only-on-failure', locale: 'zh-CN' });

test.beforeEach(async () => { await resetMockServer(); });
test.afterEach(async ({ page }) => { await page.close(); await resetMockServer(); });

async function layoutBounds(page) {
  return page.evaluate(() => ({ viewport: innerWidth, page: document.documentElement.scrollWidth,
    timeline: document.querySelector('[aria-label="教材处理时间线"]')?.getBoundingClientRect().width ?? 0 }));
}

for (const theme of ['quiet', 'nasa']) {
  for (const width of [375, 768, 1440]) {
    test(`${theme} ${width}px processing stays readable with long titles and stable timing`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: width === 375 ? 812 : 900 });
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await page.addInitScript((value) => localStorage.setItem('theme', value), theme);
      const snapshot = processingJob({ kind: 'materials' });
      await installProcessingMocks(page, { getJob: () => snapshot, ready: true });
      await page.goto('/textbooks/book-1?activity=job-1&panel=processing&kp=reading&view=source');
      const timeline = page.getByRole('region', { name: '教材处理时间线' });
      await expect(timeline).toBeVisible();
      await expect(timeline.getByRole('button', { name: '取消本次生成' })).toBeVisible();
      await expect(page.locator('.textbook-workbench-header').getByRole('button', { name: '取消本次生成' })).toHaveCount(0);
      await expect(timeline.getByText('可以离开此页面，任务会在后台继续；返回后可查看进度。')).toBeVisible();
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
      const bounds = await layoutBounds(page);
      expect(bounds.page).toBe(bounds.viewport);
      expect(bounds.timeline).toBeGreaterThan(200);
      const frame = await timeline.locator('.book-processing-frame').evaluate((element) => {
        const style = getComputedStyle(element);
        return { border: style.borderTopWidth, background: style.backgroundColor, y: element.getBoundingClientRect().y };
      });
      expect(frame.border).toBe('1px');
      expect(frame.background).not.toBe('rgba(0, 0, 0, 0)');
      expect(frame.y - (await timeline.boundingBox()).y).toBeLessThanOrEqual(32);
      const ptc = timeline.getByRole('listitem', { name: 'PTC 执行' });
      const phase = await ptc.locator('.book-service-phase').boundingBox();
      const status = await ptc.locator('.book-service-status').boundingBox();
      const duration = await ptc.locator('.book-service-duration').boundingBox();
      expect(status.x).toBeGreaterThan(phase.x + phase.width);
      expect(duration.x).toBeGreaterThan(status.x + status.width);
      await page.evaluate(() => document.fonts.ready);
      const elapsed = timeline.getByTestId('book-processing-elapsed');
      const initial = await elapsed.textContent();
      const box = await elapsed.boundingBox();
      await expect.poll(() => elapsed.textContent()).not.toBe(initial);
      const updated = await elapsed.boundingBox();
      expect(updated.y).toBe(box.y);
      expect(updated.height).toBe(box.height);
      const screen = await timeline.getByTestId('book-processing-scroll').evaluate((element) => ({ content: element.scrollHeight, available: element.clientHeight }));
      expect(screen.content).toBeLessThanOrEqual(screen.available + 2);
      await expect(timeline.getByText('PDF · 24 页', { exact: true })).toBeVisible();
      await expect(timeline.getByRole('button', { name: /诊断明细/ })).toHaveCount(0);
      const back = timeline.getByRole('button', { name: '返回阅读' });
      const hit = await back.boundingBox();
      expect(hit.height).toBeGreaterThanOrEqual(44);
      await back.focus();
      await expect(back).toBeFocused();
      await page.screenshot({ path: testInfo.outputPath(`processing-${theme}-${width}.png`), animations: 'disabled' });
      await back.press('Enter');
      await expect(page.getByRole('article', { name: '阅读 原文阅读' })).toBeVisible();
      await expect(page).toHaveURL(/kp=reading.*view=source/);
    });
  }
}

test('verified N/N waits for source commit and refresh retains the processing view', async ({ page }) => {
  let snapshot = processingJob();
  await installProcessingMocks(page, { getJob: () => snapshot });
  await page.goto('/textbooks/book-1');
  const timeline = page.getByRole('region', { name: '教材处理时间线' });
  await expect(timeline.getByText('已校验 2/3 个资源')).toBeVisible();
  await expect(page.getByRole('button', { name: '给学生使用' })).toHaveCount(0);
  await expect(page).toHaveURL(/panel=processing/);
  snapshot = { ...snapshot, items: [{ ...snapshot.items[0], preparation_progress: { verified_resources: 3, total_resources: 3 } }] };
  await expect(timeline.getByText('已校验 3/3 个资源')).toBeVisible({ timeout: 8000 });
  await expect(timeline.getByText('等待来源清单确认')).toBeVisible();
  await page.reload();
  await expect(timeline.getByText('等待来源清单确认')).toBeVisible();
  await expect(page).toHaveURL(/panel=processing/);
});

test('reading, compact and full layouts share one stream and restore reading position', async ({ page }) => {
  const snapshot = processingJob({ kind: 'materials' });
  let streamRequests = 0;
  page.on('request', (request) => {
    if (request.url().includes('/book-jobs/job-1/events') && request.headers().accept?.includes('text/event-stream')) streamRequests += 1;
  });
  await installProcessingMocks(page, { getJob: () => snapshot, ready: true });
  await page.goto('/textbooks/book-1?kp=reading&view=source&activity=job-1');
  const reader = page.getByRole('article', { name: '阅读 原文阅读' });
  await expect(reader).toBeVisible();
  await expect.poll(() => streamRequests).toBe(1);
  const scroller = reader.locator('div.overflow-y-auto');
  await scroller.evaluate((element) => { element.scrollTop = 450; element.dispatchEvent(new Event('scroll')); });
  await expect.poll(() => scroller.evaluate((element) => element.scrollTop)).toBeGreaterThan(400);
  const before = await scroller.evaluate((element) => element.scrollTop);
  const compact = page.getByRole('complementary', { name: '教材处理活动' });
  await compact.getByRole('button', { name: '打开整页时间线' }).click();
  await expect(page.getByRole('region', { name: '教材处理时间线' })).toBeVisible();
  await page.getByRole('button', { name: '返回阅读' }).click();
  await expect(reader).toBeVisible();
  await expect.poll(() => scroller.evaluate((element) => element.scrollTop)).toBeGreaterThanOrEqual(before - 2);
  expect(streamRequests).toBe(1);
});

test('cancel remains reachable when the activity snapshot fails', async ({ page }) => {
  const snapshot = processingJob({ kind: 'materials' });
  await installProcessingMocks(page, { getJob: () => snapshot, ready: true });
  let cancelled = false;
  await mockAPI(page, {
    'GET /education/book-jobs/job-1': (route) => route.fulfill({ status: 503, body: '{}' }),
    'POST /education/book-jobs/job-1/cancel': (route) => {
      cancelled = true;
      return json(route, { ...snapshot, status: 'cancelled' });
    },
  });
  await page.goto('/textbooks/book-1?activity=job-1&panel=processing');
  await expect(page.getByRole('alert')).toHaveText('处理活动暂不可用');
  await page.locator('.textbook-workbench-header').getByRole('button', { name: '取消本次生成' }).click();
  await expect.poll(() => cancelled).toBe(true);
});

test('activity updates replace the latest report without growing the timeline', async ({ page }) => {
  const snapshot = processingJob({ kind: 'materials' });
  const events = Array.from({ length: 70 }, (_, index) => event(index + 1, { kind: 'progress', message: `服务记录 ${index + 1}`, metadata: { origin: 'agent', stage: 'material_reading', scope: 'knowledge_point', kp_id: 'reading' } }));
  snapshot.high_water_seq = 70;
  await installProcessingMocks(page, { getJob: () => snapshot, ready: true, getEvents: () => events });
  await configureSSE({ path: '/api/v1/education/book-jobs/job-1/events', keepOpen: true, delay: 2500,
    events: [
      { id: 70, event: 'snapshot', data: activityPage(events, { highWater: 70 }) },
      { id: 71, event: 'snapshot', data: activityPage([event(71, { kind: 'progress', message: '新的服务记录', metadata: { origin: 'agent', stage: 'material_reading', scope: 'knowledge_point', kp_id: 'reading' } })], { highWater: 71 }) },
    ] });
  await page.goto('/textbooks/book-1?activity=job-1&panel=processing');
  const scroll = page.getByTestId('book-processing-scroll');
  await expect(scroll).toBeVisible();
  await expect(page.getByText('服务记录 70', { exact: true })).toBeVisible();
  const height = await scroll.evaluate((element) => element.scrollHeight);
  await expect(page.getByText('新的服务记录', { exact: true })).toBeVisible();
  await expect(page.getByText('服务记录 70', { exact: true })).toHaveCount(0);
  await expect(page.getByText('服务记录 1', { exact: true })).toHaveCount(0);
  expect(await scroll.evaluate((element) => element.scrollHeight)).toBe(height);
});

test('source resource activity triggers one quote pool and ticks do not reload it', async ({ page }) => {
  const snapshot = processingJob();
  const requests = [];
  page.on('request', (request) => { if (request.url().includes('/education-quotes/')) requests.push(request.url()); });
  await installProcessingMocks(page, { getJob: () => snapshot });
  await configureSSE({ path: '/api/v1/education/book-jobs/job-1/events', keepOpen: true, delay: 1200,
    events: [
      { id: 0, event: 'snapshot', data: activityPage() },
      { id: 1, event: 'snapshot', data: activityPage([event(1)], { highWater: 1 }) },
      { id: 2, event: 'snapshot', data: activityPage([event(2)], { highWater: 2 }) },
    ] });
  await page.goto('/textbooks/book-1?activity=job-1&panel=processing');
  const quote = page.getByLabel('等待时的名句');
  await expect(quote.locator('blockquote')).not.toHaveText('');
  const first = await quote.textContent();
  await expect(page.getByText('最近活动', { exact: true })).toBeAttached();
  await expect.poll(async () => (await getCapturedRequests()).filter((request) => request.url.includes('/book-jobs/job-1/events')).length).toBe(1);
  await expect.poll(() => page.getByTestId('book-processing-elapsed').textContent()).not.toBe('12 秒');
  expect(await quote.textContent()).toBe(first);
  expect(requests).toHaveLength(2);
});

test('a terminal failure retains the timeline and stops the displayed clock', async ({ page }) => {
  let snapshot = processingJob({ kind: 'materials' });
  await installProcessingMocks(page, { getJob: () => snapshot, ready: true });
  await page.goto('/textbooks/book-1?activity=job-1&panel=processing&kp=reading&view=source');
  const now = new Date().toISOString();
  snapshot = { ...snapshot, status: 'failed', failed_items: 1, finished_at: now, safe_error: '验收未通过',
    items: [{ ...snapshot.items[0], status: 'failed', finished_at: now,
      timing_summary: { ...snapshot.items[0].timing_summary, terminal_at: now, total_ms: 20_000 } }] };
  const timeline = page.getByRole('region', { name: '教材处理时间线' });
  await expect(timeline.getByText('验收未通过')).toBeVisible({ timeout: 8000 });
  const elapsed = timeline.getByTestId('book-processing-elapsed');
  const final = await elapsed.textContent();
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' });
    document.dispatchEvent(new Event('visibilitychange'));
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  expect(await elapsed.textContent()).toBe(final);
  await expect(page).toHaveURL(/panel=processing/);
  await expect(page.getByRole('button', { name: '重试未完成项' })).toBeVisible();
});

test('a submitted lesson remains readable while the batch runs without activity history', async ({ page }) => {
  const snapshot = processingJob({ kind: 'materials', title: '首份讲义' });
  const completed = { ...snapshot.items[0], status: 'succeeded', finished_at: snapshot.server_now,
    timing_summary: { ...snapshot.items[0].timing_summary, terminal_at: snapshot.server_now, total_ms: 12_000 } };
  snapshot.items = [completed, { ...snapshot.items[0], item_id: 'item-2', position: 2,
    knowledge_point_id: 'kp-2', skill_kp_id: 'second', knowledge_point_title: '后续讲义' }];
  snapshot.total_items = 2;
  snapshot.succeeded_items = 1;
  snapshot.activity_status = 'unavailable';
  await installProcessingMocks(page, { getJob: () => snapshot, ready: true, materialAvailable: false });
  await configureSSE({ path: '/api/v1/education/book-jobs/job-1/events', keepOpen: true,
    events: [{ id: 0, event: 'snapshot', data: activityPage([], { availability: 'unavailable' }) }] });
  await page.goto('/textbooks/book-1?activity=job-1&panel=processing');
  const timeline = page.getByRole('region', { name: '教材处理时间线' });
  await expect(timeline.getByText('已完成 1/2 份讲义')).toBeVisible();
  await expect(timeline.getByText('活动暂不可用，任务状态仍会继续更新。')).toBeVisible();
  await timeline.getByRole('button', { name: '阅读讲义：首份讲义', exact: true }).click();
  await expect(page).toHaveURL(/kp=reading.*view=material/);
  await expect(page.getByRole('heading', { name: '已提交的讲义' })).toBeVisible();
});

test('the next queued lesson keeps service milestones waiting after the first submission', async ({ page }) => {
  const snapshot = processingJob({ kind: 'materials', title: '已提交知识点' });
  const completed = { ...snapshot.items[0], status: 'succeeded', finished_at: snapshot.server_now,
    timing_summary: { ...snapshot.items[0].timing_summary, terminal_at: snapshot.server_now, total_ms: 12_000 } };
  snapshot.items = [completed, { ...snapshot.items[0], item_id: 'item-2', position: 2,
    knowledge_point_id: 'kp-2', skill_kp_id: 'second', knowledge_point_title: '等待容量的知识点',
    status: 'queued', attempt: 0, started_at: null, execution_phase: 'initial_queue', timing_summary: null }];
  snapshot.total_items = 2;
  snapshot.succeeded_items = 1;
  await installProcessingMocks(page, { getJob: () => snapshot, ready: true });
  await page.goto('/textbooks/book-1?activity=job-1&panel=processing');
  const timeline = page.getByRole('region', { name: '教材处理时间线' });
  await expect(timeline.getByText('知识点：等待容量的知识点', { exact: true })).toBeVisible();
  await expect(timeline.getByRole('listitem', { name: '受理等待', exact: true })).toContainText('等待');
  const milestone = timeline.getByRole('list', { name: '服务里程碑' }).getByRole('listitem', { name: 'PTC 执行', exact: true });
  await expect(milestone).toContainText('等待');
  await expect(milestone).toContainText('未记录');
});

test('cancel and retry switch to a new request round without leaving the timeline', async ({ page }) => {
  let snapshot = processingJob({ kind: 'materials', title: '本轮知识点' });
  await installProcessingMocks(page, { getJob: () => snapshot, ready: true });
  let cancelled = 0;
  let retried = 0;
  await mockAPI(page, {
    'POST /education/book-jobs/job-1/cancel': (route) => {
      cancelled += 1;
      const now = new Date().toISOString();
      snapshot = { ...snapshot, status: 'cancelled', cancelled_items: 1, finished_at: now,
        items: [{ ...snapshot.items[0], status: 'cancelled', finished_at: now,
          timing_summary: { ...snapshot.items[0].timing_summary, terminal_at: now, total_ms: 14_000 } }] };
      return json(route, snapshot);
    },
    'POST /education/book-jobs/job-1/retry': async (route) => {
      retried += 1;
      const fresh = processingJob({ kind: 'materials', title: '本轮知识点' });
      const now = new Date().toISOString();
      snapshot = { ...fresh, job_id: 'job-2', request_round: 2, round_accepted_at: now, server_now: now,
        items: [{ ...fresh.items[0], item_id: 'item-retry', timing_summary: {
          ...fresh.items[0].timing_summary, request_round: 2, queued_at: now } }] };
      await configureSSE({ path: '/api/v1/education/book-jobs/job-2/events', keepOpen: true,
        events: [{ id: 0, event: 'snapshot', data: { ...activityPage(), job_id: 'job-2' } }] });
      return json(route, snapshot);
    },
    'GET /education/book-jobs/job-2': (route) => json(route, snapshot),
    'GET /education/book-jobs/job-2/events': (route) => route.continue(),
  });
  await page.goto('/textbooks/book-1?activity=job-1&panel=processing&kp=reading&view=source');
  await page.getByRole('button', { name: '取消本次生成', exact: true }).click();
  await expect.poll(() => cancelled).toBe(1);
  const timeline = page.getByRole('region', { name: '教材处理时间线' });
  await expect(timeline.getByText('已取消', { exact: true }).first()).toBeVisible();
  await page.getByRole('button', { name: '重试未完成项', exact: true }).click();
  await expect.poll(() => retried).toBe(1);
  await expect(page).toHaveURL(/activity=job-2/);
  await expect(page).toHaveURL(/panel=processing/);
  await expect(timeline.getByTestId('book-processing-elapsed')).toHaveText(/^[0-3] 秒$/);
  await timeline.getByRole('button', { name: '返回阅读' }).click();
  await expect(page).toHaveURL(/kp=reading.*view=source/);
});

test('disconnect freezes confirmed timing and reconnect keeps the processing selection', async ({ page }) => {
  let snapshot = processingJob({ kind: 'materials' });
  await installProcessingMocks(page, { getJob: () => snapshot, ready: true });
  let offline = false;
  await page.route('**/book-jobs/job-1/events?*', async (route) => {
    if (offline) return route.fulfill({ status: 503, body: 'offline' });
    return route.fallback();
  });
  await configureSSE({ path: '/api/v1/education/book-jobs/job-1/events',
    events: [{ id: 0, event: 'snapshot', data: activityPage() }] });
  await page.goto('/textbooks/book-1?activity=job-1&panel=processing&kp=reading&view=source');
  const timeline = page.getByRole('region', { name: '教材处理时间线' });
  await expect(timeline).toBeVisible();
  offline = true;
  await expect(timeline.getByText(/正在重新连接活动流/)).toBeVisible();
  const elapsed = timeline.getByTestId('book-processing-elapsed');
  const value = await elapsed.textContent();
  await page.waitForTimeout(1500);
  expect(await elapsed.textContent()).toBe(value);
  snapshot = { ...snapshot, server_now: new Date().toISOString() };
  await configureSSE({ path: '/api/v1/education/book-jobs/job-1/events', keepOpen: true,
    events: [{ id: 0, event: 'snapshot', data: activityPage() }] });
  offline = false;
  await expect(timeline.getByText(/正在重新连接活动流/)).toHaveCount(0);
  await expect.poll(() => elapsed.textContent()).not.toBe(value);
  await expect(page).toHaveURL(/panel=processing.*kp=reading.*view=source/);
});

test('a job from another textbook is rejected before any activity subscription', async ({ page }) => {
  const snapshot = { ...processingJob(), textbook_id: 'other-book' };
  const subscriptions = [];
  page.on('request', (request) => { if (request.url().includes('/book-jobs/job-1/events')) subscriptions.push(request.url()); });
  await installProcessingMocks(page, { getJob: () => snapshot, ready: true, withCurrentJob: false });
  await page.goto('/textbooks/book-1?activity=job-1&panel=processing&kp=reading&view=source');
  await expect(page.getByText(/不属于当前教材/)).toBeVisible();
  expect(subscriptions).toHaveLength(0);
  await page.getByRole('button', { name: '返回当前教材', exact: true }).click();
  await expect(page.getByRole('article', { name: '阅读 原文阅读' })).toBeVisible();
});

test('access loss after a connected stream stops subscription and offers legal reading', async ({ page }) => {
  const snapshot = processingJob({ kind: 'materials' });
  await installProcessingMocks(page, { getJob: () => snapshot, ready: true });
  let requests = 0;
  await page.route('**/book-jobs/job-1/events?*', async (route) => {
    requests += 1;
    if (requests > 1) return route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"Book job not found"}' });
    return route.fallback();
  });
  await configureSSE({ path: '/api/v1/education/book-jobs/job-1/events',
    events: [{ id: 0, event: 'snapshot', data: activityPage() }] });
  await page.goto('/textbooks/book-1?activity=job-1&panel=processing&kp=reading&view=source');
  await expect(page.getByText(/不可访问/)).toBeVisible();
  expect(requests).toBe(2);
  await page.waitForTimeout(1500);
  expect(requests).toBe(2);
  await page.getByRole('button', { name: '返回当前教材', exact: true }).click();
  await expect(page.getByRole('article', { name: '阅读 原文阅读' })).toBeVisible();
});

test('a missing job provides a reading exit instead of trapping a ready textbook', async ({ page }) => {
  const snapshot = processingJob();
  await installProcessingMocks(page, { getJob: () => snapshot, ready: true, withCurrentJob: false });
  await mockAPI(page, {
    'GET /education/book-jobs/job-1': (route) => route.fulfill({ status: 404,
      contentType: 'application/json', body: '{"detail":"Book job not found"}' }),
  });
  await page.goto('/textbooks/book-1?activity=job-1&panel=processing&kp=reading&view=source');
  await expect(page.getByRole('button', { name: '返回当前教材', exact: true })).toBeVisible({ timeout: 15_000 });
  await page.getByRole('button', { name: '返回当前教材', exact: true }).click();
  await expect(page.getByRole('article', { name: '阅读 原文阅读' })).toBeVisible();
});

test('recovery refreshes the current attempt without exposing statistics history', async ({ page }) => {
  let snapshot = processingJob({ kind: 'materials', title: '恢复中的讲义' });
  await installProcessingMocks(page, { getJob: () => snapshot, ready: true });
  let statisticsRequests = 0;
  await mockAPI(page, {
    'GET /education/book-jobs/job-1/statistics': (route) => {
      statisticsRequests += 1;
      const timing = snapshot.items[0].timing_summary;
      const current = { item_id: 'item-1', kind: 'material', position: 1, knowledge_point_title: '恢复中的讲义',
        status: 'running', timing };
      const attempts = timing.attempt === 1 ? [current] : [
        { ...current, status: 'interrupted', timing: { ...timing, attempt: 1, terminal_at: snapshot.server_now, total_ms: 12_000 } }, current,
      ];
      return json(route, { job_id: 'job-1', request_round: 1, server_now: snapshot.server_now,
        status: 'partial', round_total_ms: 12_000, material_sample_count: 0,
        material_median_ms: null, material_longest_ms: null, supplementary: [], attempts, next_cursor: null });
    },
  });
  await page.goto('/textbooks/book-1?activity=job-1&panel=processing');
  const timeline = page.getByRole('region', { name: '教材处理时间线' });
  await expect(timeline.getByRole('button', { name: '尝试与批量统计', exact: true })).toHaveCount(0);
  await expect(timeline.getByText('知识点：恢复中的讲义', { exact: true })).toBeVisible();
  expect(statisticsRequests).toBe(0);
  snapshot = { ...snapshot, items: [{ ...snapshot.items[0], attempt: 2,
    execution_phase: 'input_staging', timing_summary: { ...snapshot.items[0].timing_summary, attempt: 2,
      phases: [{ phase: 'input_staging', status: 'available', started_at: snapshot.server_now, ended_at: null, measured_ms: null, segment_count: 1 }] } }] };
  await expect(timeline.getByRole('listitem', { name: '输入文件准备', exact: true })).toContainText('进行中', { timeout: 8000 });
  expect(statisticsRequests).toBe(0);
});
