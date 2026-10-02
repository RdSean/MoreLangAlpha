import { configureSSE, expect, getCapturedRequests, mockAPI, resetMockServer, test } from './fixtures.js';

const parent = {
  user_id: 'parent-1',
  email: 'parent@example.test',
  name: 'Parent',
  role: 'parent',
  household_id: 'household-1',
};

const recentJob = {
  job_id: 'job-1',
  kind: 'materials',
  status: 'succeeded',
  total_items: 2,
  succeeded_items: 2,
  failed_items: 0,
  cancelled_items: 0,
  not_run_items: 0,
  high_water_seq: 8,
  activity_status: 'available',
  created_at: '2026-10-02T06:00:00Z',
  started_at: '2026-10-02T06:00:01Z',
  finished_at: '2026-10-02T06:01:00Z',
  safe_error: null,
};

const workbench = {
  textbook_id: 'book-1',
  title: 'Reading Explorer 3',
  structure_status: 'ready',
  materials: { total: 2, ready: 1 },
  current_job: null,
  recent_job: recentJob,
  current_structure_id: 'structure-1',
  assigned_student_count: 0,
  updated_at: '2026-10-02T06:01:00Z',
  source: {
    document_id: 'document-1',
    parse_job_id: 'parse-1',
    primary_artifact_id: 'artifact-1',
    filename: 'reading-explorer.md',
    media_type: 'text/markdown',
    parser_id: 'markdown',
    parser_name: 'Markdown',
    completed_at: '2026-10-02T05:00:00Z',
    frozen_at: '2026-10-02T05:30:00Z',
    content_sha256: 'a'.repeat(64),
    size_bytes: 1200,
    image_count: 0,
  },
};

const structure = {
  textbook_id: 'book-1',
  structure_id: 'structure-1',
  schema_version: '2.1.0',
  warnings: [],
  structure: {
    schema_version: '2.1.0',
    book: { title: 'Reading Explorer 3' },
    source: { path: 'source.md', total_lines: 120 },
    coverage: {},
    nodes: [
      {
        id: 'unit-1',
        title: 'Sports and Fitness',
        anchor: { start_line: 1, end_line: 80 },
        children: [],
      },
      {
        id: 'appendix',
        title: 'Vocabulary Index',
        anchor: { start_line: 81, end_line: 120 },
        children: [],
      },
    ],
  },
  knowledge_points: [
    {
      knowledge_point_id: 'kp-db-1',
      skill_kp_id: 'sports-global-game',
      position: 1,
      title: '足球如何成为全球运动',
      unit_skill_node_id: 'unit-1',
      node_skill_ids: [],
      start_line: 10,
      end_line: 22,
      content_file: null,
      material_available: false,
    },
    {
      knowledge_point_id: 'kp-db-2',
      skill_kp_id: 'sports-training',
      position: 2,
      title: '冠军的训练方法',
      unit_skill_node_id: 'unit-1',
      node_skill_ids: [],
      start_line: 23,
      end_line: 40,
      content_file: 'materials/kp-db-2.md',
      material_available: true,
    },
  ],
};

const sourceMarkdown = [
  '# Sports and Fitness',
  '',
  'Opening context before the selected knowledge point.',
  '',
  'More introductory context.',
  '',
  '## The world game',
  '',
  'Football is played around the world.',
  '',
  'Teams learn positioning, passing, and shared decision making.',
  '',
  'The sport connects local practice with international competition.',
  '',
  'Players develop endurance through repeated training.',
  '',
  'Coaches adapt tactics to each opponent.',
  '',
  'Supporters bring different traditions to the same match.',
  '',
  'The rules provide a common language.',
  '',
  '## Training methods',
  '',
  'Champions combine deliberate practice with recovery.',
  '',
  'They review performance and adjust the next session.',
  '',
  'Closing context after the selected knowledge point.',
].join('\n');

const job = {
  ...recentJob,
  textbook_id: 'book-1',
  depth: 'lesson',
  requirements: null,
  replace_existing: false,
  include_supplementary: false,
  items: [
    {
      item_id: 'item-1',
      kind: 'material',
      position: 1,
      knowledge_point_id: 'kp-db-1',
      skill_kp_id: 'sports-global-game',
      status: 'succeeded',
      attempt: 1,
      safe_error: null,
      started_at: '2026-10-02T06:00:01Z',
      finished_at: '2026-10-02T06:00:30Z',
    },
    {
      item_id: 'item-2',
      kind: 'material',
      position: 2,
      knowledge_point_id: 'kp-db-2',
      skill_kp_id: 'sports-training',
      status: 'succeeded',
      attempt: 1,
      safe_error: null,
      started_at: '2026-10-02T06:00:31Z',
      finished_at: '2026-10-02T06:01:00Z',
    },
  ],
};

function sourceSlice(route) {
  const url = new URL(route.request().url());
  return route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      textbook_id: 'book-1',
      start_line: Number(url.searchParams.get('start_line')),
      end_line: Number(url.searchParams.get('end_line')),
      total_lines: 120,
      markdown: sourceMarkdown,
    }),
  });
}

function material(route) {
  const knowledgePointId = route.request().url().includes('kp-db-2') ? 'kp-db-2' : 'kp-db-1';
  const available = knowledgePointId === 'kp-db-2';
  return route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      textbook_id: 'book-1',
      knowledge_point_id: knowledgePointId,
      skill_kp_id: available ? 'sports-training' : 'sports-global-game',
      material_available: available,
      markdown: available
        ? '# 已有冠军训练讲义\n\n训练需要稳定反馈。\n\n[回到全球运动](materials/kp-db-1.md)'
        : null,
      generated_at: available ? '2026-10-02T06:00:00Z' : null,
      depth: available ? 'lesson' : null,
      requirements: null,
      content_sha256: available ? 'b'.repeat(64) : null,
    }),
  });
}

async function mockWorkbench(page) {
  await mockAPI(page, {
    'GET /auth/me': parent,
    'GET /education/textbooks/book-1': workbench,
    'GET /education/textbooks/book-1/structure': structure,
    'GET /education/textbooks/book-1/source': sourceSlice,
    'GET /education/textbooks/book-1/knowledge-points/*/material': material,
    'GET /education/book-jobs/job-1': job,
  });
}

function runningJob(overrides = {}) {
  return {
    ...job,
    status: 'running',
    succeeded_items: 0,
    finished_at: null,
    items: job.items.map((item, index) => ({
      ...item,
      status: index === 0 ? 'running' : 'queued',
      finished_at: null,
    })),
    ...overrides,
  };
}

function activityEvent(seq, overrides = {}) {
  return {
    seq,
    job_id: 'job-1',
    item_id: 'item-1',
    kind: 'tool',
    status: 'running',
    message: `Running Read ${seq}`,
    metadata: {},
    created_at: '2026-10-02T06:00:00Z',
    ...overrides,
  };
}

function activityPage(events = [], overrides = {}) {
  return {
    job_id: 'job-1',
    status: 'running',
    high_water_seq: 500,
    activity_status: 'available',
    cursor_expired: false,
    has_more: false,
    events,
    ...overrides,
  };
}

function activityFrame(events = [], overrides = {}) {
  const activity = activityPage(events, overrides);
  const id = events.at(-1)?.seq ?? 0;
  return `id: ${id}\nevent: snapshot\ndata: ${JSON.stringify(activity)}\n\n`;
}

function fulfillJSON(route, data) {
  return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) });
}

function fulfillActivity(route, body) {
  return route.fulfill({ status: 200, contentType: 'text/event-stream', body });
}

async function mockRunningWorkbench(page, getJob, getActivity, overrides = {}) {
  await mockWorkbench(page);
  await mockAPI(page, {
    'GET /education/textbooks/book-1': {
      ...workbench,
      current_job: runningJob(),
      ...overrides,
    },
    'GET /education/book-jobs/job-1': (route) => fulfillJSON(route, getJob()),
    'GET /education/book-jobs/job-1/events': getActivity,
  });
}

async function setPageVisibility(page, state) {
  await page.evaluate((visibilityState) => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: visibilityState });
    document.dispatchEvent(new Event('visibilitychange'));
  }, state);
}

async function expectNoHorizontalOverflow(page) {
  await expect.poll(() => page.evaluate(() => ({
    documentWidth: document.documentElement.scrollWidth,
    viewportWidth: window.innerWidth,
  }))).toEqual(expect.objectContaining({
    documentWidth: await page.evaluate(() => window.innerWidth),
  }));
}

test.beforeEach(async () => {
  await resetMockServer();
});

test.afterEach(async ({ page }) => {
  await page.close();
  await resetMockServer();
});

test('desktop workbench keeps reading, batch controls, links, and activity in one page', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockWorkbench(page);

  await page.goto('/textbooks/book-1?kp=sports-global-game&view=source');

  await expect(page.getByRole('heading', { name: '足球如何成为全球运动' })).toBeVisible();
  await expect(page.getByText('第 10–22 行，共 120 行')).toBeVisible();
  const highlighted = page.locator('[data-source-highlight="true"]');
  await expect(highlighted.first()).toBeVisible();
  expect(await highlighted.count()).toBeGreaterThan(0);
  await expectNoHorizontalOverflow(page);

  await page.getByText('冠军的训练方法', { exact: true }).click();
  await expect(page).toHaveURL(/kp=sports-training.*view=material/);
  await expect(page.getByText('训练需要稳定反馈。')).toBeVisible();
  await page.getByRole('tab', { name: '原文' }).click();
  await expect(page).toHaveURL(/kp=sports-training.*view=source/);
  await page.getByRole('tab', { name: '讲义' }).click();
  await page.getByRole('link', { name: '回到全球运动' }).click();
  await expect(page).toHaveURL(/kp=sports-global-game.*view=source/);

  await page.getByRole('button', { name: '批量选择' }).click();
  await page.getByRole('checkbox', { name: '选择 Sports and Fitness 全部知识点' }).check();
  await page.getByRole('button', { name: '生成所选讲义' }).click();
  await expect(page.getByRole('heading', { name: '生成未生成的 1 份讲义' })).toBeVisible();
  await page.getByRole('button', { name: '取消' }).click();

  await page.getByRole('button', { name: '活动' }).click();
  const activity = page.getByRole('complementary', { name: '教材处理活动' });
  await expect(activity).toBeVisible();
  await expect(activity.getByText('已完成 2/2 份讲义')).toBeVisible();
  await expectNoHorizontalOverflow(page);
});

test('375px workbench keeps the directory drawer and actions reachable without overflow', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await mockWorkbench(page);

  await page.goto('/textbooks/book-1?kp=sports-global-game&view=source');

  await expect(page.getByRole('button', { name: '打开教材目录' })).toBeVisible();
  await expect(page.getByRole('button', { name: '活动' })).toBeVisible();
  await expectNoHorizontalOverflow(page);

  await page.getByRole('button', { name: '打开教材目录' }).click();
  const navigator = page.getByRole('navigation', { name: '教材导航' });
  await expect(navigator).toBeVisible();
  await navigator.getByText('冠军的训练方法', { exact: true }).click();
  await expect(page).toHaveURL(/kp=sports-training.*view=material/);
  await expect(page.getByText('训练需要稳定反馈。')).toBeVisible();

  await page.getByRole('button', { name: '打开教材目录' }).click();
  await navigator.getByRole('button', { name: '批量选择' }).click();
  await navigator.getByRole('checkbox', { name: '选择 Sports and Fitness 全部知识点' }).check();
  await page.getByRole('button', { name: '生成所选讲义' }).click();
  await expect(page.getByRole('heading', { name: '生成未生成的 1 份讲义' })).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await page.getByRole('button', { name: '取消' }).click();

  await page.getByRole('button', { name: '活动' }).click();
  await expect(page.getByRole('complementary', { name: '教材处理活动' })).toBeVisible();
  await expect(page.getByRole('button', { name: '关闭处理活动' })).toBeVisible();
  await expectNoHorizontalOverflow(page);
});

test('activity reconnects after the first 200 of 500 events without skipping or duplicating details', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 700 });
  const cursors = [];
  let releaseRemainder;
  const remainderReady = new Promise((resolve) => { releaseRemainder = resolve; });
  const events = Array.from({ length: 500 }, (_, index) => activityEvent(index + 1));
  await mockRunningWorkbench(page, () => runningJob(), async (route) => {
    cursors.push(Number(new URL(route.request().url()).searchParams.get('after_seq')));
    if (cursors.length === 1) {
      return fulfillActivity(route, activityFrame(events.slice(0, 200), { has_more: true }));
    }
    if (cursors.length === 2) return route.fulfill({ status: 503, body: 'temporarily offline' });
    if (cursors.length === 3) {
      await remainderReady;
      return fulfillActivity(route, activityFrame(events.slice(150)));
    }
    return route.fulfill({ status: 403 });
  });
  await mockAPI(page, {
    'GET /education/textbooks/book-1/source': (route) => fulfillJSON(route, {
      textbook_id: 'book-1', start_line: 1, end_line: 120, total_lines: 120,
      markdown: Array(3).fill(sourceMarkdown).join('\n\n'),
    }),
  });

  await page.goto('/textbooks/book-1?kp=sports-global-game&view=source&activity=job-1');
  const panel = page.getByRole('complementary', { name: '教材处理活动' });
  await expect(panel.getByText('运行明细（200）')).toBeVisible();
  await expect(panel.getByText('正在重新连接活动流')).toBeVisible();
  releaseRemainder();
  await expect(panel.getByText('运行明细（500）')).toBeVisible();
  expect(cursors.slice(0, 3)).toEqual([0, 200, 200]);
  const readingURL = page.url();
  const reader = page.getByTestId('book-reader-scroll');
  await reader.evaluate((element) => { element.scrollTop = 180; });
  await expect.poll(() => reader.evaluate((element) => element.scrollTop)).toBeGreaterThan(0);
  const readingScroll = await reader.evaluate((element) => element.scrollTop);
  await panel.locator('summary').click();
  await expect(panel.getByText('Running Read 500', { exact: true })).toBeVisible();
  await expect(panel.getByText('Running Read 200', { exact: true })).toHaveCount(1);
  expect(page.url()).toBe(readingURL);
  expect(await reader.evaluate((element) => element.scrollTop)).toBe(readingScroll);
  await expect(panel.getByText('处理失败', { exact: true })).toHaveCount(0);
});

for (const activityStatus of ['available', 'unavailable']) {
  test(`snapshot updates material counts and current item with ${activityStatus} open silent activity`, async ({ page }) => {
    let snapshot = runningJob({ high_water_seq: 1000, activity_status: activityStatus });
    let jobRequests = 0;
    await configureSSE({
      path: '/api/v1/education/book-jobs/job-1/events',
      keepOpen: true,
      events: [{ id: 1, event: 'snapshot', data: activityPage([activityEvent(1, {
          kind: 'progress',
          message: '正在撰写讲义',
          metadata: { stage: 'material_writing' },
        })], { high_water_seq: 1000, activity_status: activityStatus }) }],
    });
    await mockRunningWorkbench(page, () => { jobRequests += 1; return snapshot; }, (route) => route.continue());

    await page.goto('/textbooks/book-1?kp=sports-global-game&view=source&activity=job-1');
    const panel = page.getByRole('complementary', { name: '教材处理活动' });
    await expect(panel.getByText('已完成 0/2 份讲义')).toBeVisible();
    if (activityStatus === 'available') await expect(panel.getByText('正在撰写讲义', { exact: true })).toBeVisible();
    else await expect(panel.getByText('活动暂不可用，任务状态仍会继续更新。')).toBeVisible();
    await expect.poll(() => jobRequests).toBeGreaterThanOrEqual(2);
    const previousRequests = jobRequests;
    snapshot = runningJob({
      high_water_seq: 1000,
      activity_status: activityStatus,
      succeeded_items: 1,
      items: job.items.map((item, index) => ({ ...item, status: index === 0 ? 'succeeded' : 'running' })),
    });

    await expect(panel.getByText('已完成 1/2 份讲义')).toBeVisible({ timeout: 8000 });
    expect(jobRequests).toBeGreaterThan(previousRequests);
    await expect(panel.getByText('正在撰写讲义', { exact: true })).toHaveCount(0);
    await expect(panel.getByText(activityStatus === 'available' ? '正在生成讲义' : '活动暂不可用，讲义生成仍在继续', { exact: true })).toBeVisible();
    const activityRequests = (await getCapturedRequests()).filter((request) => request.url.startsWith('/api/v1/education/book-jobs/job-1/events'));
    expect(activityRequests).toHaveLength(1);
    await expect(panel.getByText('正在重新连接活动流')).toHaveCount(0);
    await expect(panel.getByText('处理失败', { exact: true })).toHaveCount(0);
  });
}

test('closing activity still discovers committed material through job snapshots', async ({ page }) => {
  let completed = false;
  await mockRunningWorkbench(page, () => completed ? job : runningJob(), (route) => route.fulfill({ status: 503 }));
  await mockAPI(page, {
    'GET /education/textbooks/book-1': (route) => fulfillJSON(route, {
      ...workbench,
      materials: { total: 2, ready: completed ? 2 : 1 },
      current_job: completed ? null : runningJob(),
      recent_job: completed ? job : null,
    }),
    'GET /education/textbooks/book-1/structure': (route) => fulfillJSON(route, {
      ...structure,
      knowledge_points: structure.knowledge_points.map((kp) => completed
        ? { ...kp, material_available: true, content_file: `materials/${kp.knowledge_point_id}.md` }
        : kp),
    }),
    'GET /education/textbooks/book-1/knowledge-points/kp-db-1/material': (route) => fulfillJSON(route, {
      textbook_id: 'book-1', knowledge_point_id: 'kp-db-1', skill_kp_id: 'sports-global-game',
      material_available: completed, markdown: completed ? '# 新提交的讲义' : null,
      generated_at: completed ? '2026-10-02T06:00:00Z' : null,
      depth: 'lesson', requirements: null, content_sha256: completed ? 'a'.repeat(64) : null,
    }),
  });
  await page.goto('/textbooks/book-1?kp=sports-global-game&view=source&activity=job-1');
  await expect(page.getByRole('complementary', { name: '教材处理活动' })).toBeVisible();
  await page.getByRole('button', { name: '关闭处理活动' }).click();
  await expect(page).not.toHaveURL(/activity=/);
  completed = true;
  await expect(page.getByRole('button', { name: '取消本次生成' })).toHaveCount(0, { timeout: 12_000 });
  await expect(page.getByText('结构已就绪 · 讲义 2/2')).toBeVisible();
  await expect(page.getByRole('tab', { name: '讲义', exact: true })).toBeEnabled();
  await page.getByRole('tab', { name: '讲义', exact: true }).click();
  await expect(page.getByRole('heading', { name: '新提交的讲义' })).toBeVisible();
  await expect(page.getByRole('complementary', { name: '教材处理活动' })).toHaveCount(0);
});

test('returning from the background refreshes the job immediately without waiting for activity', async ({ page }) => {
  let snapshot = runningJob();
  let jobRequests = 0;
  await mockRunningWorkbench(page, () => { jobRequests += 1; return snapshot; }, (route) => route.fulfill({ status: 503 }));
  await page.goto('/textbooks/book-1?kp=sports-global-game&view=source&activity=job-1');
  const panel = page.getByRole('complementary', { name: '教材处理活动' });
  await expect(panel.getByText('已完成 0/2 份讲义')).toBeVisible();
  await setPageVisibility(page, 'hidden');
  const previousRequests = jobRequests;
  snapshot = { ...job, high_water_seq: 0 };
  await setPageVisibility(page, 'visible');

  await expect(panel.getByText('已完成 2/2 份讲义')).toBeVisible({ timeout: 3000 });
  expect(jobRequests).toBeGreaterThan(previousRequests);
  await expect(panel.getByText('正在生成讲义', { exact: true })).toHaveCount(0);
});

test('a delayed old job response does not overwrite the activity after switching jobs', async ({ page }) => {
  let releaseOldResponse;
  let oldRefreshStarted = false;
  let requests = 0;
  await mockRunningWorkbench(page, () => runningJob(), (route) => fulfillActivity(route, activityFrame()));
  await mockAPI(page, {
    'GET /education/book-jobs/job-1': async (route) => {
      requests += 1;
      if (requests === 1) return fulfillJSON(route, runningJob());
      oldRefreshStarted = true;
      await new Promise((resolve) => { releaseOldResponse = resolve; });
      return fulfillJSON(route, { ...job, safe_error: '旧任务迟到状态' });
    },
    'GET /education/book-jobs/job-2': runningJob({ job_id: 'job-2', succeeded_items: 1, items: [
      { ...job.items[0], status: 'succeeded' },
      { ...job.items[1], item_id: 'item-new', status: 'running' },
    ] }),
    'GET /education/book-jobs/job-2/events': (route) => fulfillActivity(route, activityFrame([
      activityEvent(1, { job_id: 'job-2', item_id: 'item-new', kind: 'progress', message: '正在组织讲义内容', metadata: { stage: 'material_organizing' } }),
    ], { job_id: 'job-2' })),
  });

  await page.goto('/textbooks/book-1?kp=sports-global-game&view=source&activity=job-1');
  await expect.poll(() => oldRefreshStarted).toBe(true);
  await page.evaluate(() => {
    const url = new URL(window.location.href);
    url.searchParams.set('activity', 'job-2');
    window.history.pushState({}, '', url);
    window.dispatchEvent(new PopStateEvent('popstate'));
  });
  const panel = page.getByRole('complementary', { name: '教材处理活动' });
  await expect(panel.getByText('已完成 1/2 份讲义')).toBeVisible();
  await expect(panel.getByText('正在组织讲义内容')).toBeVisible();
  const lateResponse = page.waitForResponse((response) => new URL(response.url()).pathname === '/api/v1/education/book-jobs/job-1');
  releaseOldResponse();
  await (await lateResponse).finished();
  await expect(panel.getByText('旧任务迟到状态')).toHaveCount(0);
  await expect(panel.getByText('已完成 1/2 份讲义')).toBeVisible();
  await expect(panel.getByText('正在组织讲义内容')).toBeVisible();
});

test('375px long activity and titles keep cancellation, reader, and directory controls reachable', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 375, height: 812 });
  const longMessage = '已完成教材材料校验并保留当前成功讲义'.repeat(30).slice(0, 512);
  const longKnowledgePointTitle = '足球如何成为全球运动：跨地区文化与团队训练方法'.repeat(12);
  await mockRunningWorkbench(page, () => runningJob(), (route) => fulfillActivity(route, activityFrame([
    activityEvent(1, { kind: 'item_succeeded', status: 'succeeded', message: longMessage }),
  ])), { title: 'Reading Explorer 3 教材与阅读训练'.repeat(12) });
  await mockAPI(page, {
    'GET /education/textbooks/book-1/structure': {
      ...structure,
      knowledge_points: structure.knowledge_points.map((point, index) => index === 0 ? { ...point, title: longKnowledgePointTitle } : point),
    },
  });
  await page.goto('/textbooks/book-1?kp=sports-global-game&view=source&activity=job-1');
  const panel = page.getByRole('complementary', { name: '教材处理活动' });
  await expect(panel.getByText(longMessage)).toBeVisible();
  await expect(page.getByRole('heading', { name: longKnowledgePointTitle })).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await expect(page.getByRole('button', { name: '取消本次生成' })).toBeVisible();
  await expect(page.getByRole('button', { name: '取消本次生成' })).toBeEnabled();
  await page.getByRole('button', { name: '取消本次生成' }).click({ trial: true });
  await testInfo.attach('mobile-control-layout', {
    contentType: 'application/json',
    body: JSON.stringify(await page.evaluate(() => {
      const selectors = ['.textbook-workbench', '.textbook-workbench-header', '.textbook-workbench-grid', '.textbook-workbench-menu', '.textbook-workbench article', '.textbook-workbench-header > div'];
      return selectors.map((selector) => {
        const element = document.querySelector(selector);
        const rect = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        return { selector, x: rect.x, width: rect.width, scrollLeft: element.scrollLeft, clientWidth: element.clientWidth, scrollWidth: element.scrollWidth, minWidth: style.minWidth, overflowX: style.overflowX, gridTemplateColumns: style.gridTemplateColumns };
      });
    }), null, 2),
  });
  await page.screenshot({ path: testInfo.outputPath('activity-long-mobile.png'), animations: 'disabled' });
  await expect(page.getByRole('button', { name: '打开教材目录' })).toBeInViewport();
  await expect(page.getByRole('button', { name: '取消本次生成' })).toBeInViewport();
  await page.getByRole('button', { name: '打开教材目录' }).click();
  const navigator = page.getByRole('navigation', { name: '教材导航' });
  await expect(navigator).toBeVisible();
  await expect(navigator.getByText('冠军的训练方法', { exact: true })).toBeInViewport();
  await page.screenshot({ path: testInfo.outputPath('activity-directory-mobile.png'), animations: 'disabled' });
  await navigator.getByText('冠军的训练方法', { exact: true }).click();
  await page.getByRole('button', { name: '关闭处理活动' }).click();
  await expect(page.getByText('训练需要稳定反馈。')).toBeVisible();
  await expectNoHorizontalOverflow(page);
});
