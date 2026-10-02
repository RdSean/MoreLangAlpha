import { expect, mockAPI, resetMockServer, test } from './fixtures.js';

const parent = {
  user_id: 'parent-1',
  email: 'parent@example.test',
  name: 'Parent',
  role: 'parent',
  household_id: 'household-1',
};

const student = {
  user_id: 'student-1',
  email: null,
  name: 'Student',
  role: 'student',
  household_id: 'household-1',
};

test.beforeEach(async () => {
  await resetMockServer();
});

test('legacy textbook structure routes explain the one-workbench reset', async ({ page }) => {
  await mockAPI(page, {
    'GET /auth/me': parent,
  });

  await page.goto('/textbooks/textbook-1/versions/version-1/structure');

  await expect(page.getByRole('heading', { name: '旧教材流程已重置' })).toBeVisible();
  await expect(page.getByText('教材结构、讲义生成和处理活动现在都在教材工作台完成。')).toBeVisible();
  await expect(page.getByRole('link', { name: '返回教材列表' })).toHaveAttribute('href', '/textbooks');
});

test('student opens a published knowledge-point lesson', async ({ page }) => {
  await mockAPI(page, {
    'GET /auth/me': student,
    'GET /education/learning/assignment-1/structure': {
      assignment_id: 'assignment-1',
      publication_id: 'publication-1',
      textbook_id: 'textbook-1',
      textbook_title: 'Reading Explorer 3',
      textbook_slug: 're3',
      version_sequence: 1,
      structure_id: 'structure-1',
      structure_sequence: 1,
      units: [
        {
          unit_id: 'unit-1',
          position: 1,
          slug: 'unit-1-sports',
          title: 'Unit 1: Sports and Fitness',
          summary: 'Sports and fitness',
          unit_type: 'teaching',
          knowledge_points: [
            {
              knowledge_point_id: 'kp-1',
              position: 1,
              slug: 'world-game',
              title: '世界运动',
              summary: '',
              has_lesson: true,
            },
          ],
        },
      ],
    },
    'GET /education/learning/assignment-1/knowledge-points/kp-1': {
      assignment_id: 'assignment-1',
      knowledge_point_id: 'kp-1',
      knowledge_point_title: '世界运动',
      unit_id: 'unit-1',
      unit_title: 'Unit 1',
      revision_id: 'revision-1',
      revision: 1,
      format: 'markdown',
      content_sha256: 'd'.repeat(64),
      size_bytes: 20,
      content_markdown: '# 世界运动\n\n足球是一项简单的运动。',
    },
    'GET /education/learning/assignment-1/items': [],
    'GET /education/learning/assignment-1/chat-space': {
      assignment_id: 'assignment-1',
      workspace_id: 'workspace-1',
      conversation_thread_id: 'thread-1',
    },
  });

  await page.goto('/education/learn/assignment-1/knowledge/kp-1');

  await expect(page.getByRole('heading', { name: '世界运动' }).first()).toBeVisible();
  await expect(page.getByText('足球是一项简单的运动。')).toBeVisible();
  if ((page.viewportSize()?.width ?? 0) < 1024) {
    await page.getByRole('button', { name: '笔记' }).click();
    await expect(page.getByRole('heading', { name: '便携笔记本' })).toBeVisible();
  } else {
    await expect(page.getByRole('region', { name: '学习笔记' })).toBeVisible();
  }
});
