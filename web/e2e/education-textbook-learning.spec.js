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

test('student opens the current knowledge-point lesson', async ({ page }) => {
  await mockAPI(page, {
    'GET /auth/me': student,
    'GET /education/learning/assignment-1/structure': {
      assignment_id: 'assignment-1',
      textbook_id: 'textbook-1',
      textbook_title: 'Reading Explorer 3',
      structure_id: 'structure-1',
      schema_version: '2.1.0',
      warnings: [],
      structure: {
        schema_version: '2.1.0',
        book: { title: 'Reading Explorer 3' },
        source: { path: 'source.md', total_lines: 80 },
        coverage: {},
        nodes: [{
          id: 'unit-1',
          title: 'Unit 1: Sports and Fitness',
          anchor: { start_line: 1, end_line: 80 },
          children: [],
        }],
      },
      knowledge_points: [{
        knowledge_point_id: 'kp-1',
        skill_kp_id: 'world-game',
        position: 1,
        title: '世界运动',
        unit_skill_node_id: 'unit-1',
        node_skill_ids: [],
        start_line: 10,
        end_line: 20,
        content_file: 'materials/kp-1.md',
        material_available: true,
      }],
    },
    'GET /education/textbooks/textbook-1/source': {
      textbook_id: 'textbook-1',
      start_line: 1,
      end_line: 32,
      total_lines: 80,
      markdown: '# Unit 1: Sports and Fitness\n\nFootball is played around the world.',
    },
    'GET /education/learning/assignment-1/knowledge-points/kp-1': {
      assignment_id: 'assignment-1',
      textbook_id: 'textbook-1',
      knowledge_point_id: 'kp-1',
      skill_kp_id: 'world-game',
      material_available: true,
      markdown: '# 世界运动\n\n足球是一项简单的运动。',
      generated_at: '2026-10-02T08:00:00Z',
      depth: 'lesson',
      requirements: null,
      content_sha256: 'd'.repeat(64),
    },
    'GET /education/learning/assignment-1/items': [],
    'GET /education/learning/assignment-1/chat-space': {
      assignment_id: 'assignment-1',
      workspace_id: 'workspace-1',
      conversation_thread_id: 'thread-1',
    },
    'GET /education/textbooks/textbook-1/knowledge-points/kp-1/conversation/replay': [],
    'GET /education/textbooks/textbook-1/knowledge-points/kp-1/conversation/status': { status: 'completed', can_reconnect: false, lesson_active: true },
  });

  await page.goto('/education/learn/assignment-1?kp=world-game&view=material');

  await expect(page.getByRole('heading', { name: '世界运动' }).first()).toBeVisible();
  await expect(page.getByText('足球是一项简单的运动。')).toBeVisible();
  await page.getByRole('button', { name: '打开学习笔记' }).click();
  await expect(page.getByRole('heading', { name: '学习笔记' })).toBeVisible();
});
