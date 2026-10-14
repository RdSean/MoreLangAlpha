import { expect, mockAPI, resetMockServer, test } from './fixtures.js';

test.use({ locale: 'zh-CN' });
test.beforeEach(async () => resetMockServer());
test.afterEach(async ({ page }) => { await page.close(); await resetMockServer(); });
const quote = 'Throughout history, humans have played some kind of kicking game.';

async function setup(page) {
  const member = { user_id: 'student-annotations', name: '学生', role: 'student', household_id: 'household', onboarding_completed: true, has_api_key: true };
  const markdown = `# 世界运动：足球的历史\n\n阅读时记录重要句子与自己的理解。\n\n> Throughout **history**, humans have played some kind of kicking game.\n\n人类历史上一直在玩某种踢球游戏。\n\n现代足球起源于英国。\n\n${Array.from({ length: 10 }, (_, index) => `## 阅读段落 ${index + 1}\n\n学习阅读需要理解原文，积累素材并记录自己的想法。`).join('\n\n')}`;
  const points = [{ knowledge_point_id: 'kp', skill_kp_id: 'reading', position: 1, title: '足球的历史', unit_skill_node_id: 'unit', node_skill_ids: ['unit'], start_line: 1, end_line: 20, material_available: true }];
  await mockAPI(page, {
    'GET /auth/me': member,
    'GET /users/me': member,
    'GET /education/learning/assignment/structure': { assignment_id: 'assignment', textbook_id: 'book', textbook_title: '阅读与学习笔记', structure_id: 'structure', schema_version: '2.1.0', warnings: [], structure: { schema_version: '2.1.0', book: { title: '阅读与学习笔记' }, source: { path: 'source.md', total_lines: 20 }, coverage: {}, nodes: [{ id: 'unit', title: '第一课', anchor: { start_line: 1, end_line: 20 }, children: [] }] }, knowledge_points: points },
    'GET /education/learning/assignment/knowledge-points/kp': { assignment_id: 'assignment', textbook_id: 'book', knowledge_point_id: 'kp', material_available: true, markdown, generated_at: '2026-10-13T00:00:00Z' },
    'GET /education/learning/assignment/chat-space': { assignment_id: 'assignment', workspace_id: 'workspace-1', conversation_thread_id: 'thread-1' },
    'GET /education/textbooks/book/reading-state': [],
    'POST /education/learning/assignment/knowledge-points/kp/reading-state': {},
    'POST /education/textbooks/book/knowledge-points/kp/reading-state': {},
    'GET /education/textbooks/book/knowledge-points/kp/conversation/replay': [],
    'GET /education/textbooks/book/knowledge-points/kp/conversation/status': { status: 'completed', can_reconnect: false, lesson_active: true },
  });
  const state = { items: [], counter: 0, failSave: false, failDelete: false, chatSpaces: 0 };
  await page.route('**/api/v1/education/learning/assignment/chat-space', (route) => { state.chatSpaces++; return route.fulfill({ json: { assignment_id: 'assignment', workspace_id: 'workspace-1', conversation_thread_id: 'thread-1' } }); });
  await page.route(/\/api\/v1\/education\/learning\/assignment\/items(?:\/[^?]+)?(?:\?.*)?$/, async (route) => {
    const request = route.request();
    if (request.method() === 'GET') return route.fulfill({ json: state.items });
    const id = new URL(request.url()).pathname.split('/').at(-1);
    if (request.method() === 'DELETE') {
      if (state.failDelete) { state.failDelete = false; return route.fulfill({ status: 500, json: { detail: 'offline' } }); }
      state.items = state.items.filter((item) => item.item_id !== id);
      return route.fulfill({ status: 204 });
    }
    const body = request.postDataJSON();
    const item = state.items.find((item) => item.item_id === id);
    Object.assign(item, body);
    return route.fulfill({ json: item });
  });
  await page.route('**/api/v1/education/learning/assignment/knowledge-points/kp/items', (route) => {
    if (state.failSave) { state.failSave = false; return route.fulfill({ status: 500, json: { detail: 'offline' } }); }
    const item = { ...route.request().postDataJSON(), item_id: `item-${++state.counter}`, assignment_id: 'assignment', knowledge_point_id: 'kp', created_at: '2026-10-13T00:00:00Z', updated_at: '2026-10-13T00:00:00Z' };
    state.items.unshift(item);
    return route.fulfill({ json: item });
  });
  return state;
}

async function selectQuote(page) {
  await page.locator('.lesson-annotation-prose blockquote').evaluate((node) => {
    const range = document.createRange(); range.selectNodeContents(node);
    const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
    document.dispatchEvent(new Event('selectionchange'));
  });
  await expect(page.getByRole('button', { name: '批注选段' })).toHaveCount(0);
  await page.locator('.lesson-annotation-prose blockquote').dispatchEvent('pointerup');
  await expect(page.getByRole('button', { name: '批注选段' })).toBeVisible();
  const toolbar = await page.locator('.lesson-selection-toolbar').boundingBox();
  const width = page.viewportSize().width;
  expect(toolbar.x).toBeGreaterThanOrEqual(0);
  expect(toolbar.x + toolbar.width).toBeLessThanOrEqual(width);
  expect(toolbar.height).toBeGreaterThanOrEqual(44);
}

for (const theme of ['quiet', 'nasa']) {
  for (const width of [375, 768, 1600]) {
    test(`${theme} ${width}px persists student marks and notes with Chat drafts`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: 1000 });
      await page.addInitScript((value) => localStorage.setItem('theme', value), theme);
      const state = await setup(page);
      await page.goto('/education/learn/assignment?kp=reading&view=material&nav=knowledge', { waitUntil: 'domcontentloaded' });
      const input = page.getByRole('textbox', { name: '讲义问题' });
      await expect(input).toBeEnabled();
      await input.fill('我的问题草稿');
      const spacesBefore = state.chatSpaces;
      await selectQuote(page);
      await page.getByRole('button', { name: '标记选段' }).click();
      await page.getByRole('button', { name: '赭黄色', exact: true }).click();
      await page.getByRole('button', { name: '保存标记', exact: true }).click();
      await expect(page.locator('.lesson-text-mark[data-annotation-color="ochre"]')).toHaveCount(3);
      expect(state.items[0].content).toBe(quote);
      expect(state.items[0].skill_node_id).toBe('unit');
      await expect(input).toHaveValue('我的问题草稿');
      expect(state.chatSpaces).toBe(spacesBefore);
      await selectQuote(page);
      await page.getByRole('button', { name: '批注选段' }).click();
      await page.getByRole('textbox', { name: '批注内容' }).fill('这个句子写得好。');
      state.failSave = true;
      await page.getByRole('button', { name: '保存批注', exact: true }).click();
      await expect(page.getByRole('alert')).toContainText('保存失败');
      await expect(page.getByRole('textbox', { name: '批注内容' })).toHaveValue('这个句子写得好。');
      await page.getByRole('button', { name: '保存批注', exact: true }).click();
      await expect(page.getByRole('dialog')).toHaveCount(0);
      await expect(input).toHaveValue('我的问题草稿');
      await expect(page.locator('.lesson-text-mark.has-note')).toHaveCount(3);
      if (width === 1600) {
        const note = page.getByRole('article', { name: '批注 1', exact: true });
        await expect(page.getByRole('complementary', { name: '正文批注' })).toBeVisible();
        await page.getByRole('button', { name: '查看批注', exact: true }).first().hover();
        await expect(note).toHaveAttribute('data-active', 'true');
        await note.hover();
        await expect(page.locator('.lesson-text-mark.has-note').first()).toHaveAttribute('data-active', 'true');
        await expect(page.locator('.lesson-text-mark.has-note').first()).toHaveCSS('text-decoration-style', 'dashed');
        await page.getByRole('button', { name: '定位批注 1 原文', exact: true }).click();
        await expect(page.getByRole('dialog')).toHaveCount(0);
        await expect(page.locator('.lesson-text-mark.has-note').first()).toBeFocused();
        await expect(page.getByRole('button', { name: '编辑批注 1', exact: true })).toBeVisible();
        await expect(page.getByRole('button', { name: '删除批注 1', exact: true })).toBeVisible();
      } else await expect(page.getByRole('complementary', { name: '正文批注' })).toBeHidden();
      await page.screenshot({ path: testInfo.outputPath(`annotations-${theme}-${width}.png`) });
      await page.reload({ waitUntil: 'domcontentloaded' });
      await expect(page.locator('.lesson-text-mark.has-note')).toHaveCount(3);
      await page.getByRole('button', { name: '查看批注', exact: true }).first().click();
      await expect(page.getByRole('textbox', { name: '批注内容' })).toHaveValue('这个句子写得好。');
      if (width === 375) {
        const dialog = await page.getByRole('dialog', { name: '批注', exact: true }).boundingBox();
        expect(dialog.x).toBeGreaterThanOrEqual(0);
        expect(dialog.x + dialog.width).toBeLessThanOrEqual(width);
        await page.screenshot({ path: testInfo.outputPath(`annotation-popup-${theme}.png`) });
      }
      await page.getByRole('textbox', { name: '批注内容' }).fill('重新理解这段话。');
      await page.getByRole('button', { name: '蓝灰色', exact: true }).click();
      await page.getByRole('button', { name: '保存批注', exact: true }).click();
      await expect(page.getByRole('dialog')).toHaveCount(0);
      if (width === 1600) {
        await expect(page.getByRole('article', { name: '批注 1', exact: true })).toHaveAttribute('data-annotation-color', 'slate');
        await page.getByRole('button', { name: '删除批注 1', exact: true }).click();
        await expect(page.getByRole('dialog', { name: '删除批注', exact: true })).toContainText('重新理解这段话。');
        await page.getByRole('button', { name: '取消', exact: true }).click();
        await expect(page.getByRole('article', { name: '批注 1', exact: true })).toBeVisible();
      }
      await page.getByRole('button', { name: '打开学习笔记', exact: true }).click();
      const notebook = page.getByRole('dialog', { name: '学习笔记', exact: true });
      await expect(notebook).toContainText('重新理解这段话。');
      await expect(notebook.getByRole('button', { name: '编辑 / 删除', exact: true })).toHaveCount(2);
      await notebook.getByRole('button', { name: '编辑 / 删除', exact: true }).first().click();
      state.failDelete = true;
      await page.getByRole('button', { name: '删除批注', exact: true }).click();
      await expect(page.getByRole('alert')).toContainText('删除失败');
      await page.getByRole('button', { name: '删除批注', exact: true }).click();
      await expect(page.getByRole('dialog', { name: '批注', exact: true })).toHaveCount(0);
      await expect(notebook).not.toContainText('重新理解这段话。');
      await page.keyboard.press('Escape');
      await expect(notebook).toHaveCount(0);
      await expect(page.locator('.lesson-text-mark.has-note')).toHaveCount(0);
      await page.getByRole('button', { name: '查看标记', exact: true }).first().click();
      await page.getByRole('button', { name: '删除标记', exact: true }).click();
      await expect(page.locator('.lesson-text-mark')).toHaveCount(0);
      await page.reload({ waitUntil: 'domcontentloaded' });
      await expect(page.locator('.lesson-text-mark')).toHaveCount(0);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    });
  }
}

test('mouse dragging waits for release and cancelled annotation keeps the Chat draft', async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 900 });
  await setup(page);
  await page.goto('/education/learn/assignment?kp=reading&view=material', { waitUntil: 'domcontentloaded' });
  const input = page.getByRole('textbox', { name: '讲义问题' });
  await expect(input).toBeEnabled();
  await input.fill('继续保留的问题');
  const bounds = await page.locator('.lesson-annotation-prose').getByText('阅读时记录重要句子与自己的理解。', { exact: true }).evaluate((node) => {
    const range = document.createRange(); range.setStart(node.firstChild, 0); range.setEnd(node.firstChild, 5);
    const rect = range.getBoundingClientRect(); return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
  });
  // Dispatch real mouse input without Playwright's newer drag-interception CDP API.
  const inputSession = await page.context().newCDPSession(page);
  const y = bounds.y + bounds.height / 2;
  await inputSession.send('Input.dispatchMouseEvent', { type: 'mousePressed', x: bounds.x + 1, y, button: 'left', buttons: 1, clickCount: 1 });
  for (let step = 1; step <= 5; step++) {
    await inputSession.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: bounds.x + 1 + (bounds.width - 2) * step / 5, y, button: 'left', buttons: 1 });
  }
  await expect(page.getByRole('button', { name: '批注选段' })).toHaveCount(0);
  await inputSession.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: bounds.x + bounds.width - 1, y, button: 'left', buttons: 0, clickCount: 1 });
  await inputSession.detach();
  await page.getByRole('button', { name: '批注选段' }).click();
  await page.getByRole('textbox', { name: '批注内容' }).fill('未保存的批注');
  await page.getByRole('button', { name: '取消', exact: true }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(input).toHaveValue('继续保留的问题');
  await expect(page.locator('.lesson-text-mark')).toHaveCount(0);
  const last = page.locator('.lesson-annotation-prose p').last();
  await last.scrollIntoViewIfNeeded();
  await last.evaluate((node) => {
    node.scrollIntoView({ block: 'center', behavior: 'instant' });
    return new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  });
  await last.evaluate((node) => {
    const range = document.createRange(); range.selectNodeContents(node);
    const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
    node.dispatchEvent(new PointerEvent('pointerup', { bubbles: true }));
  });
  await page.getByRole('button', { name: '批注选段' }).click();
  await page.getByRole('textbox', { name: '批注内容' }).fill(Array.from({ length: 20 }, () => '较长的批注也不应遮挡后面的问答。').join('\n'));
  await page.getByRole('button', { name: '保存批注', exact: true }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect.poll(() => page.locator('.lesson-annotation-layout').evaluate((layout) => {
    const note = layout.querySelector('.lesson-margin-note');
    return Boolean(note) && note.getBoundingClientRect().bottom <= layout.getBoundingClientRect().bottom;
  })).toBe(true);
});

for (const theme of ['quiet', 'nasa']) {
  test(`${theme} margin notes follow their source, avoid collisions and confirm deletion`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1600, height: 1000 });
    await page.addInitScript((value) => localStorage.setItem('theme', value), theme);
    const state = await setup(page);
    await page.goto('/education/learn/assignment?kp=reading&view=material', { waitUntil: 'domcontentloaded' });
    await selectQuote(page);
    await page.getByRole('button', { name: '批注选段' }).click();
    await page.getByRole('textbox', { name: '批注内容' }).fill(Array.from({ length: 16 }, () => '长批注保留完整内容，并在框内滚动。').join('\n'));
    await page.getByRole('button', { name: '保存批注', exact: true }).click();
    await expect(page.getByRole('dialog')).toHaveCount(0);
    const paragraph = page.locator('.lesson-annotation-prose').getByText('人类历史上一直在玩某种踢球游戏。', { exact: true });
    await paragraph.evaluate((node) => {
      const range = document.createRange(); range.selectNodeContents(node);
      const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
      node.dispatchEvent(new PointerEvent('pointerup', { bubbles: true }));
    });
    await page.getByRole('button', { name: '批注选段' }).click();
    await page.getByRole('textbox', { name: '批注内容' }).fill('第二条批注自动避让。');
    await page.getByRole('button', { name: '保存批注', exact: true }).click();
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await expect(page.locator('.lesson-margin-note')).toHaveCount(2);
    await expect.poll(() => page.locator('.lesson-margin-note').evaluateAll((notes) => notes[1].getBoundingClientRect().top - notes[0].getBoundingClientRect().bottom)).toBeGreaterThanOrEqual(11);
    const source = page.locator('.lesson-text-mark').first();
    const note = page.getByRole('article', { name: '批注 1', exact: true });
    const sourceTop = (await source.boundingBox()).y;
    const offsetBefore = (await note.boundingBox()).y - (await source.boundingBox()).y;
    await page.locator('.lesson-annotation-prose').evaluate((node) => {
      let scroll = node.parentElement;
      while (scroll && (scroll.scrollHeight <= scroll.clientHeight || !/auto|scroll/.test(getComputedStyle(scroll).overflowY))) scroll = scroll.parentElement;
      if (scroll) scroll.scrollTop += 100;
    });
    await expect.poll(async () => Math.abs((await source.boundingBox()).y - sourceTop)).toBeGreaterThan(50);
    await expect.poll(async () => Math.abs((await note.boundingBox()).y - (await source.boundingBox()).y - offsetBefore)).toBeLessThan(2);
    await page.getByRole('button', { name: '定位批注 1 原文', exact: true }).click();
    await expect(source).toBeFocused();
    await page.screenshot({ path: testInfo.outputPath(`margin-notes-${theme}.png`) });
    await page.getByRole('button', { name: '删除批注 2', exact: true }).click();
    expect(state.items).toHaveLength(2);
    state.failDelete = true;
    await page.getByRole('button', { name: '删除批注', exact: true }).click();
    await expect(page.getByRole('alert')).toContainText('删除失败');
    expect(state.items).toHaveLength(2);
    await page.getByRole('button', { name: '删除批注', exact: true }).click();
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await expect(page.locator('.lesson-margin-note')).toHaveCount(1);
    expect(state.items[0].content).toContain('长批注');
  });
}
