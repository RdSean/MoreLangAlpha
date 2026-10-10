import { test, expect, mockAPI, resetMockServer } from './fixtures.js';
import { Buffer } from 'node:buffer';

const parent = {
  user_id: 'parent-1',
  email: 'parent@example.test',
  name: '家长',
  role: 'parent',
  household_id: 'household-1',
};

const student = {
  user_id: 'student-1',
  email: null,
  name: '学生',
  role: 'student',
  household_id: 'household-1',
  grade_code: 'g4',
};

const dictionaries = {
  timezone: 'Asia/Tokyo',
  subjects: [{
    code: 'math', name: '数学', color: '#277DA1', sort_order: 1,
    homework_types: [{ code: 'practice', name: '练习', sort_order: 1 }],
  }],
  grade_levels: [{ code: 'g4', name: '四年级', stage: 'primary', sort_order: 4 }],
  practice_sources: [
    { code: 'schoolwork', name: '校内作业', sort_order: 1 },
    { code: 'homework', name: '校外作业', sort_order: 2 },
  ],
};

const task = (status) => ({
  task_id: 'task-1',
  task_rule_id: 'rule-1',
  household_id: 'household-1',
  assigned_student_id: student.user_id,
  occurrence_date: '2026-08-09',
  due_at: '2026-08-10T01:00:00.000Z',
  title: '读书笔记',
  description: '记录三个发现。',
  status,
});

const textbookWorkbench = {
  textbook_id: 'textbook-1',
  title: '英语第二册',
  structure_status: 'ready',
  materials: { total: 1, ready: 1 },
  current_job: null,
  recent_job: null,
  current_structure_id: 'structure-1',
  assigned_student_count: 0,
  updated_at: '2026-10-02T06:01:00Z',
  source: {
    document_id: 'document-1',
    parse_job_id: 'parse-1',
    primary_artifact_id: 'artifact-1',
    filename: 'english-2.md',
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

const textbookStructure = {
  textbook_id: 'textbook-1',
  structure_id: 'structure-1',
  schema_version: '2.1.0',
  warnings: [],
  structure: {
    schema_version: '2.1.0',
    book: { title: '英语第二册' },
    source: { path: 'source.md', total_lines: 40 },
    coverage: {},
    nodes: [{
      id: 'unit-1',
      title: '第一单元',
      anchor: { start_line: 1, end_line: 40 },
      children: [],
    }],
  },
  knowledge_points: [{
    knowledge_point_id: 'kp-1',
    skill_kp_id: 'overview',
    position: 1,
    title: '导读',
    unit_skill_node_id: 'unit-1',
    node_skill_ids: [],
    start_line: 5,
    end_line: 12,
    content_file: 'materials/kp-1.md',
    material_available: true,
  }],
};

const textbookMaterial = {
  textbook_id: 'textbook-1',
  knowledge_point_id: 'kp-1',
  skill_kp_id: 'overview',
  material_available: true,
  markdown: '# 学习目标\n\n理解课文的核心内容。',
  generated_at: '2026-10-02T06:00:00Z',
  depth: 'lesson',
  requirements: null,
  content_sha256: 'b'.repeat(64),
};

test.beforeEach(async ({ page }) => {
  await resetMockServer();
  await page.clock.setFixedTime(new Date('2026-08-09T06:00:00Z'));
});

test.describe('Family education roles', () => {
  test('a parent opens the reusable textbook library', async ({ page }) => {
    await mockAPI(page, {
      'GET /auth/me': parent,
      'GET /education/textbooks': [{
        textbook_id: 'textbook-1',
        title: '英语第二册',
        structure_status: 'ready',
        materials: { total: 2, ready: 1 },
        current_job: null,
        updated_at: '2026-10-02T06:01:00Z',
      }],
    });

    await page.goto('/textbooks', { waitUntil: 'domcontentloaded' });

    await expect(page.getByRole('heading', { name: '教材' })).toBeVisible();
    await expect(page.getByText('英语第二册')).toBeVisible();
    await expect(page.getByText('结构已就绪')).toBeVisible();
    await expect(page.getByText('1 / 2')).toBeVisible();
  });

  test('textbook sources do not overflow at mobile or desktop widths', async ({ page }) => {
    const unbroken = `source-${'x'.repeat(240)}`;
    await mockAPI(page, {
      'GET /auth/me': parent,
      'GET /education/textbooks/textbook-1': textbookWorkbench,
      'GET /education/textbooks/textbook-1/structure': textbookStructure,
      'GET /education/textbooks/textbook-1/source': {
        textbook_id: 'textbook-1',
        start_line: 1,
        end_line: 24,
        total_lines: 40,
        markdown: `# 导读\n\n${unbroken}`,
      },
      'GET /education/textbooks/textbook-1/knowledge-points/kp-1/material': textbookMaterial,
    });

    for (const width of [390, 1280]) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto('/textbooks/textbook-1?kp=overview&view=source', { waitUntil: 'domcontentloaded' });

      const panel = page.getByTestId('book-reader-scroll');
      await expect(panel.getByText(unbroken)).toBeVisible();
      const dimensions = await panel.evaluate((element) => ({
        scrollWidth: element.scrollWidth,
        clientWidth: element.clientWidth,
      }));
      expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth);
    }
  });

  test('a parent creates homework for a household student', async ({ page }) => {
    let created;
    await mockAPI(page, {
      'GET /auth/me': parent,
      'GET /auth/members': [parent, student],
      'GET /education/tasks/calendar': { days: [], stats: { total_points: 0 } },
      'GET /education/dictionaries': dictionaries,
      'POST /education/tasks': async (route) => {
        created = route.request().postDataJSON();
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify(task('open')),
        });
      },
    });

    await page.goto('/education', { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('heading', { name: '家庭作业' })).toBeVisible();
    await page.getByRole('link', { name: '创建作业' }).click();
    await page.getByRole('button', { name: student.name, exact: true }).click();
    await expect(page.getByText('当前年级：四年级')).toBeVisible();
    await page.getByLabel('说明').fill('比较十位数字。');
    await page.getByLabel('截止时间').fill('2026-08-10T10:00');
    await page.getByRole('button', { name: '创建作业' }).click();

    await expect.poll(() => created).toMatchObject({
      assigned_student_id: student.user_id,
      title: '数学练习',
      description: '比较十位数字。',
      subject_code: 'math',
      type_code: 'practice',
      practice_source_code: 'homework',
      due_at: '2026-08-10T01:00:00.000Z',
      frequency: 'once',
      material_asset_ids: [],
    });
  });

  test('a student can resubmit an attachment but has no parent controls', async ({ page }) => {
    let submitted;
    await mockAPI(page, {
      'GET /auth/me': student,
      'GET /education/tasks/calendar': { days: [{ date: '2026-08-09', task_count: 1, completed_count: 1, tasks: [task('completed')] }], stats: { total_points: 1 } },
      'GET /education/dictionaries': dictionaries,
      'GET /education/learning': [],
      'POST /education/assets': {
        asset_id: 'asset-1',
        original_filename: 'homework.pdf',
        content_type: 'application/pdf',
        size_bytes: 16,
      },
      'POST /education/tasks/*/revisions': async (route) => {
        submitted = route.request().postDataJSON();
        await route.fulfill({ status: 201, contentType: 'application/json', body: '{}' });
      },
    });

    await page.goto('/education', { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('heading', { name: '我的作业' })).toBeVisible();
    await expect(page.getByRole('button', { name: '创建作业' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: '反馈' })).toHaveCount(0);

    await page.getByRole('button', { name: '补充提交' }).click();
    await page.getByPlaceholder('补充说明或修改内容').fill('已按建议补充。');
    await page.getByLabel('附件').setInputFiles({
      name: 'homework.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.from('student homework'),
    });
    await page.getByRole('button', { name: '提交补充' }).click();

    await expect.poll(() => submitted).toMatchObject({
      submission_text: '已按建议补充。',
      asset_ids: ['asset-1'],
    });
    expect(submitted.idempotency_key).toMatch(/^[0-9a-f-]{36}$/i);
  });

  test('a student reads the current assigned lesson and marks it learned', async ({ page }) => {
    let progress;
    const assignment = {
      assignment_id: 'assignment-1',
      textbook_id: 'textbook-1',
      textbook_title: '英语第二册',
      structure_id: 'structure-1',
      knowledge_point_count: 1,
      completed_knowledge_point_count: 0,
    };
    await mockAPI(page, {
      'GET /auth/me': student,
      'GET /education/tasks/calendar': { days: [], stats: { total_points: 0 } },
      'GET /education/learning': [assignment],
      'GET /education/learning/assignment-1/structure': {
        ...textbookStructure,
        assignment_id: 'assignment-1',
        textbook_title: '英语第二册',
      },
      'GET /education/textbooks/textbook-1/source': {
        textbook_id: 'textbook-1',
        start_line: 1,
        end_line: 24,
        total_lines: 40,
        markdown: '# 导读\n\n这是原书内容。',
      },
      'GET /education/learning/assignment-1/knowledge-points/kp-1': {
        ...textbookMaterial,
        assignment_id: 'assignment-1',
      },
      'GET /education/learning/assignment-1/items': [],
      'GET /education/learning/assignment-1/chat-space': {
        assignment_id: 'assignment-1',
        workspace_id: 'workspace-1',
        conversation_thread_id: 'thread-1',
      },
      'POST /education/learning/assignment-1/knowledge-points/kp-1/progress': async (route) => {
        progress = route.request().postDataJSON();
        await route.fulfill({ status: 204, body: '' });
      },
    });

    await page.goto('/education', { waitUntil: 'domcontentloaded' });
    await page.getByRole('button', { name: '继续学习' }).click();

    await expect(page.getByRole('heading', { name: '英语第二册' })).toBeVisible();
    await expect(page.getByRole('heading', { name: '导读' })).toBeVisible();
    await expect(page.getByText('理解课文的核心内容。')).toBeVisible();
    await page.getByRole('button', { name: '标记已学' }).click();

    await expect.poll(() => progress).toEqual({ status: 'read' });
  });

  test('a parent grants a ready textbook to a student without publication', async ({ page }) => {
    let assignmentRequest;
    await mockAPI(page, {
      'GET /auth/me': parent,
      'GET /auth/members': [parent, student],
      'GET /education/textbooks': [textbookWorkbench],
      'GET /education/textbooks/textbook-1': textbookWorkbench,
      'GET /education/textbooks/textbook-1/structure': textbookStructure,
      'GET /education/textbooks/textbook-1/source': {
        textbook_id: 'textbook-1',
        start_line: 1,
        end_line: 24,
        total_lines: 40,
        markdown: '# 导读\n\n这是原书内容。',
      },
      'GET /education/textbooks/textbook-1/knowledge-points/kp-1/material': textbookMaterial,
      'GET /education/textbooks/textbook-1/assignments': [],
      'POST /education/textbooks/textbook-1/assignments': async (route) => {
        assignmentRequest = route.request().postDataJSON();
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify([{
            textbook_id: 'textbook-1',
            student_user_id: student.user_id,
            assigned_at: '2026-10-02T07:00:00Z',
          }]),
        });
      },
    });

    await page.goto('/textbooks', { waitUntil: 'domcontentloaded' });
    await page.getByRole('button', { name: '英语第二册 更多' }).click();
    await page.getByRole('menuitem', { name: '给学生使用' }).click();
    await page.getByRole('checkbox', { name: '学生' }).check();
    await page.getByRole('button', { name: '保存' }).click();

    await expect.poll(() => assignmentRequest).toEqual({ student_user_ids: [student.user_id] });
  });
});
