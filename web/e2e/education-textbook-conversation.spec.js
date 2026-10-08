import { configureSSE, expect, getCapturedRequests, mockAPI, resetMockServer, test } from './fixtures.js';
import { Buffer } from 'node:buffer';

test.use({ locale: 'zh-CN' });
const book = 'book-conversation';
const kp = 'kp-conversation';
const thread = 'b0000010-0000-4000-8000-000000000010';
const workspace = 'a0000010-0000-4000-8000-000000000010';
const parent = { user_id: 'parent-conversation', name: '教材作者', email: 'lesson@example.test', role: 'parent', household_id: 'family-conversation', avatar_url: '/test-avatar.png', has_api_key: true, onboarding_completed: true };
const point = { knowledge_point_id: kp, skill_kp_id: 'lesson', position: 1, title: '学习会话', unit_skill_node_id: 'unit', node_skill_ids: [], start_line: 1, end_line: 20, material_available: true, content_file: 'materials/lesson.md' };
const userEvent = { event: 'user_message', data: { turn_index: 0, content: '请制作学习作品', timestamp: '2026-10-08T08:00:00Z', metadata: { education_knowledge_point_id: kp } } };
const textEvent = { event: 'message_chunk', data: { turn_index: 0, role: 'assistant', content_type: 'text', content: '这份讲义的补充回答。' } };
const widgetEvent = { event: 'artifact', data: { turn_index: 0, artifact_type: 'html_widget', artifact_id: 'lesson-widget', payload: { title: '学习作品', html: '<main style="color:var(--color-text-primary);padding:20px"><h1>学习作品</h1><button onclick="this.textContent=\'已互动\'">开始</button></main>' } } };
const interruptEvent = { event: 'interrupt', data: { interrupt_id: 'lesson-confirm', action_requests: [{ type: 'create_workspace', workspace_name: '学习作品项目', workspace_description: '练习作品' }] } };
const baseStatus = { status: 'completed', can_reconnect: false, latest_turn_index: 0, active_tasks: [], pending_report_back: false, lesson_active: true };

async function setup(page, { replay = [], status = baseStatus, markdown = '# 学习讲义\n\n这是原始讲义。' } = {}, sharedState, apiOrigin) {
  await mockAPI(page, {
    'GET /auth/me': parent,
    'GET /users/me': parent,
    [`GET /education/textbooks/${book}`]: { textbook_id: book, title: '教材学习会话', structure_status: 'ready', materials: { total: 1, ready: 1 }, current_job: null, recent_job: null, current_structure_id: 'structure', assigned_student_count: 0, source: null },
    [`GET /education/textbooks/${book}/structure`]: { textbook_id: book, structure_id: 'structure', schema_version: '2.1.0', warnings: [], structure: { schema_version: '2.1.0', book: { title: '教材学习会话' }, source: { path: 'source.md', total_lines: 20 }, coverage: {}, nodes: [{ id: 'unit', title: '第一课', anchor: { start_line: 1, end_line: 20 }, children: [] }] }, knowledge_points: [point] },
    [`GET /education/textbooks/${book}/knowledge-points/${kp}/material`]: { textbook_id: book, knowledge_point_id: kp, material_available: true, markdown, generated_at: '2026-10-08T08:00:00Z', depth: 'lesson' },
    [`GET /education/textbooks/${book}/reading-state`]: [],
    [`POST /education/textbooks/${book}/knowledge-points/${kp}/reading-state`]: {},
    [`POST /education/textbooks/${book}/knowledge-points/${kp}/chat-space`]: { workspace_id: workspace, conversation_thread_id: thread },
    [`GET /education/textbooks/${book}/knowledge-points/${kp}/conversation/replay`]: () => {},
    [`GET /education/textbooks/${book}/knowledge-points/${kp}/conversation/status`]: () => {},
    [`GET /threads/${thread}/status`]: () => {},
    [`GET /threads/${thread}/feedback`]: [],
    [`GET /threads/${thread}/turns`]: { turns: [] },
    [`GET /threads/${thread}`]: { thread_id: thread, workspace_id: workspace, title: '教材问答', msg_type: 'flash' },
    [`GET /workspaces/${workspace}`]: { workspace_id: workspace, name: 'Flash', status: 'flash', config: {} },
    'POST /workspaces/flash': { workspace_id: workspace, name: 'Flash', status: 'flash', config: {} },
    'GET /threads': { threads: [{ thread_id: thread, workspace_id: workspace, title: '教材问答', msg_type: 'flash' }], total: 1 },
  }, apiOrigin);
  // Mutable fixture state lets refresh and the second page observe the same durable result.
  const state = sharedState ?? { replay, status };
  await page.route(`**/api/v1/education/textbooks/${book}/knowledge-points/${kp}/conversation/replay`, (route) => route.fulfill({ json: state.replay }));
  await page.route(`**/api/v1/education/textbooks/${book}/knowledge-points/${kp}/conversation/status`, (route) => route.fulfill({ json: state.status }));
  await page.route(`**/api/v1/threads/${thread}/status*`, (route) => route.fulfill({ json: { thread_id: thread, ...state.status } }));
  await page.route(`**/api/v1/threads/${thread}/messages/replay*`, (route) => route.fulfill({ contentType: 'text/event-stream', body: [...state.replay, { event: 'replay_done', data: {} }].map((item) => `event: ${item.event}\ndata: ${JSON.stringify(item.data)}\n\n`).join('') }));
  await page.route('**/test-avatar.png', (route) => route.fulfill({ contentType: 'image/png', body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jT1sAAAAASUVORK5CYII=', 'base64') }));
  return state;
}

async function openLesson(page) {
  await page.goto(`/textbooks/${book}?kp=lesson&view=material`);
  await expect(page.getByText('这是原始讲义。')).toBeVisible();
}

test.beforeEach(async () => resetMockServer());

test('restores HTML and pending HITL, submits a scoped rejection once, and keeps the lesson', async ({ page }) => {
  const state = await setup(page, { replay: [userEvent, textEvent, widgetEvent, interruptEvent], status: { ...baseStatus, status: 'interrupted', run_id: 'paused-run' } });
  await openLesson(page);
  await expect(page.getByText('学习作品项目', { exact: true })).toBeVisible();
  await expect(page.getByRole('textbox', { name: '讲义问题' })).toBeDisabled();
  await expect(page.getByRole('heading', { name: '请制作学习作品' })).toHaveCount(0);
  const timestamp = await page.locator('[data-testid="message-timestamp"]').getAttribute('datetime');
  await page.reload();
  await expect(page.getByText('学习作品项目', { exact: true })).toBeVisible();
  expect(await page.locator('[data-testid="message-timestamp"]').getAttribute('datetime')).toBe(timestamp);
  await expect(page.locator('.lesson-turn-question img')).toHaveAttribute('src', '/test-avatar.png');
  await expect(page.getByText('这是原始讲义。')).toBeVisible();
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await page.screenshot({ path: `/tmp/langalpha-hitl-${width}.png` });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  const iframe = page.locator('.lesson-turn iframe').first();
  await expect(iframe).toBeVisible();
  expect(await iframe.getAttribute('sandbox')).not.toContain('allow-same-origin');
  await iframe.contentFrame().getByRole('button', { name: '开始' }).click();
  await expect(iframe.contentFrame().getByRole('button', { name: '已互动' })).toBeVisible();
  await configureSSE({ method: 'POST', path: `/api/v1/threads/${thread}/messages`, delay: 10, events: [
    { event: 'metadata', data: { thread_id: thread, run_id: 'rejected-run' } },
    { event: 'message_chunk', data: { role: 'assistant', content_type: 'text', content: '已取消创建。' } },
  ] });
  await page.getByRole('button', { name: 'Decline', exact: true }).click();
  await expect(page.getByText('已取消创建。')).toBeVisible();
  const requests = (await getCapturedRequests()).filter((r) => r.method === 'POST' && r.url === `/api/v1/threads/${thread}/messages`);
  expect(requests).toHaveLength(1);
  expect(requests[0].body.education_textbook_id).toBe(book);
  expect(requests[0].body.education_knowledge_point_id).toBe(kp);
  expect(requests[0].body.hitl_response['lesson-confirm'].decisions[0].type).toBe('reject');
  expect(requests[0].body.request_key).toBeTruthy();
  await expect(page.getByText('这是原始讲义。')).toBeVisible();
  state.status = baseStatus;
});

test('renders synthetic pending history on the existing LAN development server without backend writes', async ({ page }) => {
  const devOrigin = 'http://127.0.0.1:5177';
  // Catch unmatched API traffic before the fixture routes; this browser must
  // never send a test mutation to the developer's live backend.
  await page.route('**/api/v1/**', (route) => route.fulfill({ status: 403, json: { detail: 'Unmocked live backend request blocked' } }));
  await setup(page, { replay: [userEvent, textEvent, widgetEvent, interruptEvent], status: { ...baseStatus, status: 'interrupted', run_id: 'paused-run' } }, undefined, devOrigin);
  for (const width of [390, 1440]) {
    for (const theme of ['light', 'dark']) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(`${devOrigin}/textbooks/${book}?kp=lesson&view=material`);
      await expect(page.getByText('这是原始讲义。')).toBeVisible();
      await expect(page.getByText('学习作品项目', { exact: true })).toBeVisible();
      await page.evaluate((value) => document.documentElement.setAttribute('data-theme', value), theme);
      await expect(page.getByRole('textbox', { name: '讲义问题' })).toBeDisabled();
      await expect(page.locator('.lesson-turn-question img')).toHaveAttribute('src', '/test-avatar.png');
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: `/tmp/langalpha-live5177-${width}-${theme}.png` });
    }
  }
});

test('synchronizes a confirmation handled in Flash into the open textbook page', async ({ page, context }) => {
  const state = await setup(page, { replay: [userEvent, textEvent, interruptEvent], status: { ...baseStatus, status: 'interrupted', run_id: 'paused-run' } });
  const flash = await context.newPage();
  await setup(flash, {}, state);
  let publish;
  const published = new Promise((resolve) => { publish = resolve; });
  const feed = async (route) => {
    await published;
    await route.fulfill({ contentType: 'text/event-stream', body: `event: thread_lifecycle\ndata: ${JSON.stringify({ type: 'run_settled', thread_id: thread, workspace_id: workspace, run_id: 'remote-reject', run_seq: 2, status: 'completed' })}\n\n` });
  };
  await page.route('**/api/v1/users/me/thread-events*', feed);
  await flash.route('**/api/v1/users/me/thread-events*', feed);
  await openLesson(page);
  await flash.goto(`/chat/t/${thread}`);
  await expect(page.getByRole('button', { name: 'Decline', exact: true })).toBeVisible();
  await expect(flash.getByRole('button', { name: 'Decline', exact: true })).toBeVisible();
  await configureSSE({ method: 'POST', path: `/api/v1/threads/${thread}/messages`, delay: 10, events: [
    { event: 'metadata', data: { thread_id: thread, run_id: 'remote-reject' } },
    { event: 'message_chunk', data: { role: 'assistant', content_type: 'text', content: '跨页面取消完成。' } },
  ] });
  await flash.getByRole('button', { name: 'Decline', exact: true }).click();
  await expect(flash.getByText('跨页面取消完成。')).toBeVisible();
  state.replay = [userEvent, textEvent, { event: 'message_chunk', data: { turn_index: 0, role: 'assistant', content_type: 'text', content: '跨页面取消完成。' } }];
  state.status = baseStatus;
  publish();
  await expect(page.getByText('跨页面取消完成。')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Decline', exact: true })).toHaveCount(0);
  await expect(page.getByRole('textbox', { name: '讲义问题' })).toBeEnabled();
  expect((await getCapturedRequests()).filter((request) => request.method === 'POST' && request.url === `/api/v1/threads/${thread}/messages`)).toHaveLength(1);
});

test('recovers file and preview references, resolves on demand, and retries preview failures', async ({ page }) => {
  await setup(page, { replay: [userEvent, { event: 'artifact', data: { turn_index: 0, artifact_type: 'file_operation', artifact_id: 'lesson-file', payload: { file_path: 'work/lesson.md' } } },
    { event: 'artifact', data: { turn_index: 0, artifact_type: 'preview_url', artifact_id: 'lesson-preview', payload: { port: 3000, title: '动态练习', command: 'pnpm dev', path: '/lesson' } } }] });
  const previewRequests = [];
  await page.route(`**/api/v1/workspaces/${workspace}/sandbox/preview-url`, async (route) => {
    previewRequests.push(route.request().postDataJSON());
    await route.fulfill(previewRequests.length === 1 ? { status: 503, json: { detail: 'Offline' } } : { json: { url: 'https://lesson-preview.example.test/' } });
  });
  await page.route('https://lesson-preview.example.test/**', (route) => route.fulfill({ contentType: 'text/html; charset=utf-8', body: '<p>已恢复动态练习</p>' }));
  await openLesson(page);
  await expect(page.getByRole('button', { name: 'work/lesson.md' })).toBeVisible();
  await expect(page.getByRole('button', { name: '动态练习' })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('button', { name: '动态练习' })).toBeVisible();
  expect(previewRequests).toHaveLength(0);
  await page.getByRole('button', { name: '动态练习' }).click();
  await expect(page.getByRole('alert')).toContainText('预览暂不可用或没有访问权限');
  await page.getByRole('button', { name: '重试预览' }).click();
  const preview = page.getByRole('dialog').locator('iframe');
  await expect(preview).toHaveAttribute('src', 'https://lesson-preview.example.test/lesson');
  await expect(preview.contentFrame().getByText('已恢复动态练习')).toBeVisible();
  expect(previewRequests).toEqual([{ port: 3000, command: 'pnpm dev' }, { port: 3000, command: 'pnpm dev' }]);
});

test('a failed confirmation can be recovered and retransmitted with the same request key', async ({ page }) => {
  await setup(page, { replay: [userEvent, textEvent, interruptEvent], status: { ...baseStatus, status: 'interrupted', run_id: 'paused-run' } });
  const requests = [];
  await page.route(`**/api/v1/threads/${thread}/messages`, async (route) => {
    requests.push(route.request().postDataJSON());
    await route.fulfill(requests.length === 1 ? { status: 503, json: { detail: 'Temporarily offline' } } : {
      contentType: 'text/event-stream', body: 'event: message_chunk\ndata: {"role":"assistant","content_type":"text","content":"确认已恢复。"}\n\n',
    });
  });
  await openLesson(page);
  await page.getByRole('button', { name: 'Decline', exact: true }).click();
  await page.getByRole('button', { name: '恢复会话' }).click();
  await expect(page.getByRole('button', { name: 'Decline', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Decline', exact: true }).click();
  await expect(page.getByText('确认已恢复。')).toBeVisible();
  expect(requests).toHaveLength(2);
  expect(requests[1].request_key).toBe(requests[0].request_key);
  expect(requests[1].education_knowledge_point_id).toBe(kp);
});

test('bounds long code in desktop/mobile themes, preserves full copy, and prints full text', async ({ page }) => {
  test.setTimeout(90_000);
  const code = Array.from({ length: 180 }, (_, i) => `const lesson_${i} = ${i};`).join('\n');
  await setup(page, { markdown: `# 学习讲义\n\n这是原始讲义。\n\n\`\`\`js\n${code}\n\`\`\`` });
  await page.addInitScript(() => { navigator.clipboard.writeText = async (text) => { window.copiedLessonCode = text; }; });
  for (const width of [375, 390, 768, 1440]) {
    for (const theme of ['light', 'dark']) {
      await page.setViewportSize({ width, height: 900 });
      await openLesson(page);
      await page.evaluate((value) => document.documentElement.setAttribute('data-theme', value), theme);
      const body = page.locator('.code-block-body').first();
      const toggle = page.getByRole('button', { name: '展开代码', exact: true }).first();
      await expect(toggle).toBeVisible();
      expect(await body.evaluate((el) => el.clientHeight)).toBeLessThanOrEqual(width < 768 ? 240 : 320);
      await toggle.click();
      await expect(page.getByRole('button', { name: '收起代码' }).first()).toHaveAttribute('aria-expanded', 'true');
      expect(await body.evaluate((el) => el.clientHeight)).toBeGreaterThan(1000);
      await page.getByRole('button', { name: '收起代码' }).first().click();
      await page.getByRole('button', { name: 'Copy', exact: true }).first().click();
      expect(await page.evaluate(() => window.copiedLessonCode)).toBe(code);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: `/tmp/langalpha-conversation-${width}-${theme}.png` });
    }
  }
  await page.emulateMedia({ media: 'print' });
  expect(await page.locator('.code-block-body').first().evaluate((el) => getComputedStyle(el).maxHeight)).toBe('none');
});
