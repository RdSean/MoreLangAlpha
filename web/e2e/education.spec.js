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

test.beforeEach(async () => {
  await resetMockServer();
});

test.describe('Family education roles', () => {
  test('a parent opens the reusable textbook library', async ({ page }) => {
    await mockAPI(page, {
      'GET /auth/me': parent,
      'GET /auth/members': [parent, student],
      'GET /education/tasks': [],
      'GET /education/textbooks': [{
        textbook_id: 'textbook-1',
        household_id: 'household-1',
        title: '英语第二册',
        slug: 'english-2',
        latest_version_sequence: 1,
        latest_version_status: 'review',
        chapter_count: 2,
        assignment_count: 1,
      }],
    });

    await page.goto('/education');
    await page.getByRole('link', { name: '家庭教材库' }).click();

    await expect(page.getByRole('heading', { name: '家庭教材库' })).toBeVisible();
    await expect(page.getByText('英语第二册')).toBeVisible();
    await expect(page.getByText('待审阅')).toBeVisible();
  });

  test('a parent creates homework for a household student', async ({ page }) => {
    let created;
    await mockAPI(page, {
      'GET /auth/me': parent,
      'GET /auth/members': [parent, student],
      'GET /education/tasks': [],
      'POST /education/tasks': async (route) => {
        created = route.request().postDataJSON();
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify(task('open')),
        });
      },
    });

    await page.goto('/education');
    await expect(page.getByRole('heading', { name: '家庭作业' })).toBeVisible();
    await page.getByRole('button', { name: '创建作业' }).click();
    await page.getByLabel('学生').selectOption(student.user_id);
    await page.getByLabel('标题').fill('新的阅读任务');
    await page.getByLabel('截止时间').fill('2026-08-10T10:00');
    await page.getByRole('button', { name: '创建作业' }).click();

    await expect.poll(() => created).toMatchObject({
      assigned_student_id: student.user_id,
      title: '新的阅读任务',
      frequency: 'once',
      material_asset_ids: [],
    });
  });

  test('a student can resubmit an attachment but has no parent controls', async ({ page }) => {
    let submitted;
    await mockAPI(page, {
      'GET /auth/me': student,
      'GET /education/tasks': [task('revision_requested')],
      'POST /education/assets': {
        asset_id: 'asset-1',
        original_filename: 'homework.pdf',
        content_type: 'application/pdf',
        size_bytes: 16,
      },
      'POST /education/tasks/*/submissions': async (route) => {
        submitted = route.request().postDataJSON();
        await route.fulfill({ status: 201, contentType: 'application/json', body: '{}' });
      },
    });

    await page.goto('/education');
    await expect(page.getByRole('heading', { name: '我的作业' })).toBeVisible();
    await expect(page.getByRole('button', { name: '创建作业' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: '反馈' })).toHaveCount(0);

    await page.getByRole('button', { name: '提交作业' }).click();
    await page.getByPlaceholder('写下完成情况').fill('已按建议补充。');
    await page.getByLabel('附件').setInputFiles({
      name: 'homework.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.from('student homework'),
    });
    await page.getByRole('button', { name: '提交' }).click();

    await expect.poll(() => submitted).toMatchObject({
      submission_text: '已按建议补充。',
      asset_ids: ['asset-1'],
    });
    expect(submitted.idempotency_key).toMatch(/^[0-9a-f-]{36}$/i);
  });

  test('a student reads an assigned published chapter and submits a check', async ({ page }) => {
    let answer;
    const assignment = {
      assignment_id: 'assignment-1',
      publication_id: 'publication-1',
      textbook_title: '英语第二册',
      textbook_slug: 'english-2',
      version_sequence: 1,
      chapter_count: 1,
      completed_chapter_count: 0,
    };
    await mockAPI(page, {
      'GET /auth/me': student,
      'GET /education/tasks': [],
      'GET /education/learning': [assignment],
      'GET /education/learning/assignment-1': {
        ...assignment,
        chapters: [{
          chapter_id: 'chapter-1',
          position: 1,
          slug: '01-overview',
          title: '导读',
          markdown: '# 导读\n\n完成阅读后做知识检查。',
          teaching_material: '# 学习目标\n\n- 完成知识检查。',
          progress_status: 'not_started',
          questions: [{
            question_id: 'question-1',
            position: 1,
            prompt: '完成本章学习后，下一步应该做什么？',
            options: { A: '完成知识检查', B: '跳过所有材料' },
            knowledge_point: '学习证据',
          }],
        }],
      },
      'GET /education/learning/assignment-1/chat-space': {
        assignment_id: 'assignment-1',
        workspace_id: 'workspace-1',
        conversation_thread_id: 'thread-1',
      },
      'POST /education/learning/*/chapters/*/progress': {},
      'POST /education/learning/*/questions/*/answers': async (route) => {
        answer = route.request().postDataJSON();
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify({ is_correct: true }),
        });
      },
    });

    await page.goto('/education');
    await page.getByRole('button', { name: '继续学习' }).click();

    await expect(page.getByRole('heading', { name: '英语第二册' })).toBeVisible();
    await expect(page.getByText('完成阅读后做知识检查。')).toBeVisible();
    await expect(page.getByRole('button', { name: '发布版本' })).toHaveCount(0);
    await page.getByRole('radio', { name: 'A. 完成知识检查' }).check();
    await page.getByRole('button', { name: '提交答案' }).click();

    await expect.poll(() => answer).toMatchObject({ selected_option: 'A' });
    await expect(page.getByText('回答正确')).toBeVisible();
  });
});
