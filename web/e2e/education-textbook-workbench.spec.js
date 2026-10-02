import { expect, mockAPI, resetMockServer, test } from './fixtures.js';

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
