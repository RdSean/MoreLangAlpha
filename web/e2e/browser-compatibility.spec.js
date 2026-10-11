import { test, expect, mockAPI, configureSSE, resetMockServer } from './fixtures.js';
import { sampleThread, sampleWorkspace, sseEvents } from './helpers/mockResponses.js';

const parent = { user_id: 'compat-parent', name: 'Parent', role: 'parent', household_id: 'compat-family' };

test.use({ viewport: { width: 820, height: 1180 }, hasTouch: true });

for (const theme of ['quiet', 'nasa']) for (const capability of ['array-at', 'media-events']) {
  test(`${theme} tablet opens chat without ${capability}`, async ({ page }) => {
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.addInitScript(({ value, theme }) => {
      localStorage.setItem('theme', theme);
      if (value === 'array-at') delete Array.prototype.at;
      if (value === 'media-events') {
        const matchMedia = window.matchMedia.bind(window);
        window.matchMedia = query => {
          const media = matchMedia(query);
          media.addEventListener = undefined;
          media.removeEventListener = undefined;
          return media;
        };
      }
    }, { value: capability, theme });
    await mockAPI(page, { 'GET /auth/me': parent });
    await page.goto('/chat');
    await expect(page.getByRole('heading', { name: 'Workspaces', exact: true })).toBeVisible();
    expect(errors).toEqual([]);
    await page.setViewportSize({ width: 600, height: 1000 });
    await expect(page.locator('.bottom-tab-bar')).toBeVisible();
    await page.setViewportSize({ width: 820, height: 1180 });
    await expect(page.locator('.bottom-tab-bar')).toHaveCount(0);
    expect(errors).toEqual([]);
  });
}

test('Chrome 90 capabilities render existing chat Markdown', async ({ page }) => {
  await resetMockServer();
  const workspace = sampleWorkspace({ status: 'flash' });
  const thread = sampleThread();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => {
    delete Array.prototype.at;
    delete Object.hasOwn;
    delete window.structuredClone;
    delete crypto.randomUUID;
    delete Promise.withResolvers;
  });
  await mockAPI(page, {
    'GET /auth/me': parent,
    'GET /workspaces': { workspaces: [workspace], total: 1, limit: 20, offset: 0 },
    [`GET /workspaces/${workspace.workspace_id}`]: workspace,
    'GET /threads': { threads: [thread], total: 1 },
    [`GET /threads/${thread.thread_id}`]: thread,
    [`GET /threads/${thread.thread_id}/status`]: { status: 'completed', can_reconnect: false },
    [`GET /threads/${thread.thread_id}/turns`]: { turns: [] },
    [`GET /threads/${thread.thread_id}/feedback`]: [],
    [`GET /workspaces/${workspace.workspace_id}/files`]: { files: [] },
  });
  await configureSSE({
    method: 'GET', path: `/api/v1/threads/${thread.thread_id}/messages/replay`, delay: 10,
    events: [sseEvents.userMessage('Read this lesson'), sseEvents.messageChunk('# Browser compatibility\n\nLesson text is visible.'),
      sseEvents.messageChunk('', 'text'), sseEvents.replayDone(thread.thread_id)],
  });
  await page.goto(`/chat/t/${thread.thread_id}`);
  await expect(page.getByText('Lesson text is visible.', { exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});
