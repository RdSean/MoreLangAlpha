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

  test('mock: a parent generates a managed teaching package before publication', async ({ page }) => {
    let actingStudent = false;
    let created = false;
    let processingState = 'none';
    let teachingState = 'none';
    let assigned = false;
    let answered = false;
    const assignment = {
      assignment_id: 'assignment-1',
      publication_id: 'publication-1',
      textbook_title: '家庭英语',
      textbook_slug: 'family-english',
      version_sequence: 1,
      chapter_count: 1,
      completed_chapter_count: 0,
    };
    const chapter = {
      chapter_id: 'chapter-1',
      position: 1,
      slug: '01-overview',
      title: '导读',
      page_start: 1,
      page_end: 3,
      markdown: '# 导读\n\n完成阅读后做知识检查。',
      teaching_material: '# 学习目标\n\n- 完成知识检查。',
      questions: [{
        question_id: 'question-1',
        position: 1,
        prompt: '完成本章学习后，下一步应该做什么？',
        options: { A: '完成知识检查', B: '跳过所有材料' },
        correct_option: 'A',
        explanation: '本章需要完成检查。',
        knowledge_point: '学习证据',
      }],
    };
    const textbookDetail = () => ({
      textbook_id: 'textbook-1',
      household_id: 'household-1',
      title: '家庭英语',
      slug: 'family-english',
      versions: processingState === 'none' ? [] : [{
        version_id: 'version-1',
        sequence: 1,
        status: processingState === 'queued' ? 'processing' : processingState === 'review' ? 'review' : 'published',
        processing_job_id: 'job-1',
        processing_job_status: processingState === 'queued' ? 'queued' : 'completed',
        chapter_count: processingState === 'queued' ? 0 : 1,
        is_published: processingState === 'published',
        publication_id: processingState === 'published' ? 'publication-1' : null,
        teaching_packages: teachingState === 'none' ? [] : [{
          teaching_package_id: 'teaching-package-1',
          job_id: 'teaching-job-1',
          sequence: 1,
          status: teachingState === 'review' || teachingState === 'published' ? 'review' : 'generating_teaching',
          job_status: teachingState === 'review' || teachingState === 'published' ? 'completed' : 'running',
          chapter_count: teachingState === 'review' || teachingState === 'published' ? 1 : 0,
          question_count: teachingState === 'review' || teachingState === 'published' ? 1 : 0,
        }],
        sources: [{ asset_id: 'asset-1', original_filename: 'family-reader.pdf', content_type: 'application/pdf', size_bytes: 2048 }],
        chapters: processingState === 'queued' ? [] : [chapter],
        assignments: assigned ? [{ assignment_id: assignment.assignment_id, student_user_id: student.user_id, student_name: student.name }] : [],
      }],
    });
    const fulfillJSON = (route, body) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });

    await mockAPI(page, {
      'GET /auth/me': (route) => fulfillJSON(route, actingStudent ? student : parent),
      'GET /auth/members': [parent, student],
      'GET /education/tasks': [],
      'GET /education/assets': [{ asset_id: 'asset-1', original_filename: 'family-reader.pdf', content_type: 'application/pdf', size_bytes: 2048 }],
      'GET /education/textbooks': (route) => fulfillJSON(route, created ? [{
        textbook_id: 'textbook-1', household_id: 'household-1', title: '家庭英语', slug: 'family-english',
        latest_version_sequence: processingState === 'none' ? null : 1,
        latest_version_status: processingState === 'none' ? null : processingState === 'queued' ? 'processing' : processingState === 'review' ? 'review' : 'published',
        chapter_count: processingState === 'queued' || processingState === 'none' ? 0 : 1,
        assignment_count: assigned ? 1 : 0,
      }] : []),
      'POST /education/textbooks': async (route) => {
        created = true;
        await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ textbook_id: 'textbook-1', household_id: 'household-1', title: route.request().postDataJSON().title, slug: 'family-english', chapter_count: 0, assignment_count: 0 }) });
      },
      'GET /education/textbooks/textbook-1': (route) => fulfillJSON(route, textbookDetail()),
      'POST /education/textbooks/textbook-1/processing': async (route) => {
        processingState = 'queued';
        await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ job_id: 'job-1', version_id: 'version-1', status: 'queued' }) });
      },
      'POST /education/textbook-processing/job-1/run': async (route) => {
        processingState = 'review';
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ job_id: 'job-1', version_id: 'version-1', status: 'completed' }) });
      },
      'POST /education/textbook-versions/version-1/teaching-packages': async (route) => {
        teachingState = 'running';
        await route.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify({
          job_id: 'teaching-job-1', teaching_package_id: 'teaching-package-1', content_version_id: 'version-1',
          status: 'running', phase: 'generating_teaching', attempt_count: 1, completed_chapter_count: 0,
          total_chapter_count: 1, actions: ['cancel'], events: [], attempts: [],
        }) });
      },
      'GET /education/teaching-jobs/teaching-job-1': (route) => fulfillJSON(route, {
        job_id: 'teaching-job-1', teaching_package_id: 'teaching-package-1', content_version_id: 'version-1',
        status: teachingState === 'review' ? 'completed' : 'running',
        phase: teachingState === 'review' ? 'review' : 'generating_teaching',
        attempt_count: 1, completed_chapter_count: teachingState === 'review' ? 1 : 0, total_chapter_count: 1,
        actions: teachingState === 'review' ? [] : ['cancel'],
        events: teachingState === 'review' ? [{ sequence: 1, phase: 'generating_teaching', summary: '已完成第 1 章教学材料生成' }] : [],
        attempts: [{ attempt_id: 'attempt-1', root_run_id: 'root-run-1', status: teachingState === 'review' ? 'completed' : 'running' }],
      }),
      'POST /education/textbooks/textbook-1/versions/version-1/publish': async (route) => {
        processingState = 'published';
        await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ publication_id: 'publication-1', version_id: 'version-1' }) });
      },
      'POST /education/textbook-publications/publication-1/assignments': async (route) => {
        assigned = true;
        await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ assignment_id: assignment.assignment_id, publication_id: assignment.publication_id, student_user_id: student.user_id }) });
      },
      'GET /education/learning': (route) => fulfillJSON(route, actingStudent && assigned ? [assignment] : []),
      'GET /education/learning/assignment-1': (route) => fulfillJSON(route, { ...assignment, chapters: [{ ...chapter, progress_status: answered ? 'check_completed' : 'not_started' }] }),
      'GET /education/learning/assignment-1/chat-space': { assignment_id: assignment.assignment_id, workspace_id: 'workspace-1', conversation_thread_id: 'thread-1' },
      'POST /education/learning/*/chapters/*/progress': {},
      'POST /education/learning/*/questions/*/answers': async (route) => {
        answered = route.request().postDataJSON().selected_option === 'A';
        await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ is_correct: answered }) });
      },
      'GET /education/learning/assignment-1/records': (route) => fulfillJSON(route, { assignment_id: assignment.assignment_id, student_user_id: student.user_id, textbook_title: assignment.textbook_title, records: [{ chapter_id: chapter.chapter_id, chapter_title: chapter.title, status: answered ? 'check_completed' : 'learning', correct_count: answered ? 1 : 0, answer_count: answered ? 1 : 0 }] }),
      'GET /education/learning/assignment-1/chat-transcript': { assignment_id: assignment.assignment_id, student_user_id: student.user_id, textbook_title: assignment.textbook_title, conversation_thread_id: 'thread-1', messages: [] },
    });

    await page.goto('/education');
    await page.getByRole('link', { name: '家庭教材库' }).click();
    await page.getByRole('button', { name: '新建教材' }).click();
    await page.getByLabel('教材名称').fill('家庭英语');
    await page.getByRole('button', { name: '创建教材' }).click();
    await page.getByRole('link', { name: '打开 家庭英语' }).click();
    await page.getByRole('button', { name: '开始加工' }).click();
    await page.getByRole('checkbox', { name: 'family-reader.pdf' }).check();
    await page.getByRole('button', { name: '创建加工任务' }).click();
    await page.getByRole('button', { name: '执行本地加工' }).click();
    await page.getByRole('button', { name: '生成教学包' }).click();
    await expect(page.getByText('教学包正在加工')).toBeVisible();
    await expect(page.getByRole('dialog', { name: '教材教学包运行' })).toBeVisible();
    await expect(page.getByText('生成教学材料')).toBeVisible();
    await expect(page.getByRole('textbox')).toHaveCount(0);
    await expect(page.locator('body')).not.toContainText(/storage_key|\/managed\/|minio/i);
    await page.getByRole('button', { name: 'Close' }).click();
    teachingState = 'review';
    await page.reload();
    await page.getByRole('button', { name: '发布版本' }).click();
    await page.getByRole('button', { name: '分配学生' }).click();
    await page.getByLabel('学生').selectOption(student.user_id);
    await page.getByRole('button', { name: '分配教材' }).click();

    actingStudent = true;
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/education');
    await page.getByRole('button', { name: '继续学习' }).click();
    await page.getByRole('button', { name: '知识检查' }).click();
    await page.getByRole('radio', { name: 'A. 完成知识检查' }).check();
    await page.getByRole('button', { name: '提交答案' }).click();
    await expect(page.getByText('回答正确')).toBeVisible();
    await expect(page.getByRole('button', { name: '发布版本' })).toHaveCount(0);

    actingStudent = false;
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto('/education');
    await page.getByRole('link', { name: '家庭教材库' }).click();
    await page.getByRole('link', { name: '打开 家庭英语' }).click();
    await page.getByRole('tab', { name: '学生' }).click();
    await page.getByRole('button', { name: '查看记录：学生' }).click();
    await expect(page.getByRole('heading', { name: '学生的学习记录' })).toBeVisible();
    await expect(page.getByText('check_completed · 1/1')).toBeVisible();
    await expect(page.getByRole('button', { name: '提交答案' })).toHaveCount(0);
  });
});
