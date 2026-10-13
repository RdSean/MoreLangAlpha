import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { expect, mockAPI, resetMockServer, test } from './fixtures.js';
import { installProcessingMocks, json, processingJob } from './helpers/textbookProcessingFixtures.js';

// Reuse the repository's readable PDF page; do not touch uploaded library files.
const originalPdf = execFileSync('uv', ['run', 'python', '-c', `
import sys
from io import BytesIO
from pypdf import PdfReader, PdfWriter
reader = PdfReader('tests/fixtures/documents/text.pdf')
writer = PdfWriter()
for _ in range(20):
    writer.add_page(reader.pages[0])
output = BytesIO()
writer.write(output)
sys.stdout.buffer.write(output.getvalue())
`], { cwd: fileURLToPath(new URL('../../', import.meta.url)) });

test.use({ locale: 'zh-CN', screenshot: 'only-on-failure' });
test.beforeEach(async () => resetMockServer());
test.afterEach(async ({ page }) => { await page.close(); await resetMockServer(); });

async function installOriginal(page, { marker = null, jsonPage = null, missing = false, student = false, longLesson = false } = {}) {
  const job = { ...processingJob(), status: 'succeeded' };
  await installProcessingMocks(page, { getJob: () => job, ready: true, withCurrentJob: false, title: '原书阅读与知识点定位测试教材 · A Book With a Longer Title' });
  let downloads = 0;
  const lessonMarkdown = '# 已提交的讲义\n\n这份讲义已经可以阅读。' + (longLesson
    ? Array.from({ length: 40 }, (_, index) => `\n\n### 足球与世界 ${index + 1}\n\nFootball is played around the world. 足球的规则帮助来自不同国家的球员共同比赛，团队合作是理解这项运动的重要部分。`).join('')
    : '');
  await mockAPI(page, {
    'GET /education/textbooks/book-1/knowledge-points/kp-1/material': {
      textbook_id: 'book-1', knowledge_point_id: 'kp-1', skill_kp_id: 'reading', material_available: true,
      markdown: lessonMarkdown, generated_at: '2026-10-01T00:00:00Z', depth: 'lesson', requirements: null, content_sha256: 'b'.repeat(64),
    },
    'GET /education/textbooks/book-1/structure': {
      textbook_id: 'book-1', structure_id: 'structure-1', schema_version: '2.1.0', warnings: [],
      structure: { schema_version: '2.1.0', book: { title: '原书' }, source: { path: 'source.md', total_lines: 500 }, coverage: {},
        nodes: [{ id: 'unit-1', title: '章节一', anchor: { start_line: 300, end_line: 350 }, page_range: jsonPage === null ? null : { start: jsonPage, end: 15, source: 'derived', label: 'PDF pages' }, children: [] }] },
      knowledge_points: [{ knowledge_point_id: 'kp-1', skill_kp_id: 'reading', position: 1, title: '原文阅读', unit_skill_node_id: 'unit-1', node_skill_ids: ['unit-1'], start_line: 300, end_line: 350, content_file: 'materials/kp-1.md', material_available: true }],
    },
    'GET /education/textbooks/book-1/original': (route) => {
      downloads += 1;
      return missing ? route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"Original file not found"}' }) : route.fulfill({ contentType: 'application/pdf', body: originalPdf });
    },
    'GET /education/textbooks/book-1/original-location': (route) => {
      expect(new URL(route.request().url()).searchParams.get('start_line')).toBe('300');
      return json(route, { page: marker });
    },
    'GET /education/textbooks/book-1/reading-state': [],
    'POST /education/textbooks/book-1/knowledge-points/kp-1/chat-space': { workspace_id: 'workspace-1', conversation_thread_id: 'thread-1' },
    'POST /education/textbooks/book-1/knowledge-points/kp-1/reading-state': {},
    'GET /education/textbooks/book-1/knowledge-points/kp-1/conversation/replay': [],
    'GET /education/textbooks/book-1/knowledge-points/kp-1/conversation/status': { status: 'completed', can_reconnect: false, lesson_active: true },
  });
  if (student) {
    const member = { user_id: 'student-1', email: null, name: 'Student', role: 'student', household_id: 'household-1' };
    await mockAPI(page, {
      'GET /auth/me': member,
      'GET /users/me': { ...member, onboarding_completed: true, has_api_key: true },
      'GET /education/learning/assignment-1/structure': {
        assignment_id: 'assignment-1', textbook_id: 'book-1', textbook_title: '原书阅读测试教材',
        structure_id: 'structure-1', schema_version: '2.1.0', warnings: [],
        structure: { schema_version: '2.1.0', book: { title: '原书' }, source: { path: 'source.md', total_lines: 500 }, coverage: {},
          nodes: [{ id: 'unit-1', title: '章节一', anchor: { start_line: 300, end_line: 350 }, page_range: { start: 15, end: 20, source: 'derived', label: 'PDF pages' }, children: [] }] },
        knowledge_points: [{ knowledge_point_id: 'kp-1', skill_kp_id: 'reading', position: 1, title: '原文阅读', unit_skill_node_id: 'unit-1', node_skill_ids: ['unit-1'], start_line: 300, end_line: 350, content_file: 'materials/kp-1.md', material_available: true }],
      },
      'GET /education/learning/assignment-1/knowledge-points/kp-1': {
        assignment_id: 'assignment-1', textbook_id: 'book-1', knowledge_point_id: 'kp-1', skill_kp_id: 'reading', material_available: true,
        markdown: lessonMarkdown, generated_at: '2026-10-01T00:00:00Z', depth: 'lesson', requirements: null, content_sha256: 'b'.repeat(64),
      },
      'GET /education/learning/assignment-1/chat-space': { assignment_id: 'assignment-1', workspace_id: 'workspace-1', conversation_thread_id: 'thread-1' },
      'GET /education/learning/assignment-1/items': [],
      'GET /education/textbooks/book-1/reading-state': [],
      'POST /education/learning/assignment-1/knowledge-points/kp-1/reading-state': {},
      'GET /education/textbooks/book-1/knowledge-points/kp-1/conversation/replay': [],
      'GET /education/textbooks/book-1/knowledge-points/kp-1/conversation/status': { status: 'completed', can_reconnect: false, lesson_active: true },
    });
  }
  return { downloads: () => downloads };
}

async function expectPdf(page, number) {
  const pdfPage = page.locator(`.react-pdf__Page[data-page-number="${number}"] canvas`);
  await expect(pdfPage).toBeVisible();
  await expect(page.locator('.pdf-page-info')).toHaveText(`${number} / 20`);
  await expect.poll(() => pdfPage.evaluate((canvas) => {
    const pixels = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
    let ink = 0;
    for (let i = 0; i < pixels.length; i += 4) if (pixels[i + 3] && pixels[i] < 200 && pixels[i + 1] < 200 && pixels[i + 2] < 200) ink++;
    return ink;
  })).toBeGreaterThan(40);
}

async function selectDirectoryTab(page, name) {
  const openDirectory = page.locator('.textbook-mobile-header').getByRole('button', { name: '打开教材目录', exact: true });
  if (await openDirectory.isVisible()) await openDirectory.click();
  await page.getByRole('tab', { name, exact: true }).click();
  const closeDirectory = page.getByRole('button', { name: '关闭教材目录', exact: true });
  if (await closeDirectory.isVisible()) await closeDirectory.click();
}

for (const theme of ['quiet', 'nasa']) {
  for (const width of [375, 1440]) {
    test(`${theme} ${width}px original starts at marker page and restores navigation`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: 900 });
      await page.addInitScript((value) => localStorage.setItem('theme', value), theme);
      const requests = await installOriginal(page, { marker: 12, jsonPage: 15 });
      await page.goto('/textbooks/book-1?kp=reading&view=original&nav=source');
      await expectPdf(page, 12);
      const canvas = await page.locator('.react-pdf__Page canvas').boundingBox();
      const viewport = await page.locator('.pdf-document-wrapper').boundingBox();
      expect(canvas.x).toBeGreaterThanOrEqual(viewport.x);
      expect(canvas.width).toBeLessThanOrEqual(viewport.width);
      expect(canvas.height).toBeLessThanOrEqual(viewport.height - 22);
      expect(canvas.y + canvas.height).toBeLessThanOrEqual(viewport.y + viewport.height);
      await page.locator('.pdf-nav button').last().click();
      await expectPdf(page, 13);
      await expect(page).toHaveURL(/pdfPage=13/);
      await page.reload();
      await expectPdf(page, 13);
      await selectDirectoryTab(page, '文字目录');
      await expect(page.getByText('Paragraph 1:', { exact: false })).toBeVisible();
      await selectDirectoryTab(page, '原始教材');
      await expectPdf(page, 13);
      expect(requests.downloads()).toBe(2); // one load per page lifetime, not per selection/tab
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
      await page.screenshot({ path: testInfo.outputPath(`original-${theme}-${width}.png`) });
    });
  }
}

for (const student of [false, true]) {
  test(`${student ? 'student' : 'parent'} original fits height and supports scoped keyboard and wheel navigation`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await installOriginal(page, { marker: 12, student });
    const path = student ? '/education/learn/assignment-1' : '/textbooks/book-1';
    await page.goto(`${path}?kp=reading&view=original&nav=source`);
    await expectPdf(page, 12);
    await page.keyboard.press('PageDown');
    await expectPdf(page, 13);
    await page.keyboard.press('PageUp');
    await expectPdf(page, 12);
    const viewport = page.locator('.pdf-document-wrapper');
    await viewport.evaluate(element => {
      element.dispatchEvent(new WheelEvent('wheel', { deltaY: 100, bubbles: true, cancelable: true }));
      element.dispatchEvent(new WheelEvent('wheel', { deltaY: 100, bubbles: true, cancelable: true }));
    });
    await expectPdf(page, 13);
    await page.waitForTimeout(250);
    const bounds = await viewport.boundingBox();
    await page.mouse.move(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2);
    await page.keyboard.down('Control');
    await page.mouse.wheel(0, -100);
    await page.keyboard.up('Control');
    await expect(page.locator('.pdf-zoom-info')).toHaveText('125%');
    await expect(page.locator('.pdf-page-info')).toHaveText('13 / 20');
    await expect.poll(() => viewport.evaluate(element => element.scrollHeight > element.clientHeight)).toBe(true);
    await page.waitForTimeout(250);
    await page.mouse.wheel(0, 100);
    await expect.poll(() => viewport.evaluate(element => element.scrollTop)).toBeGreaterThan(0);
    await expect(page.locator('.pdf-page-info')).toHaveText('13 / 20');
    await page.locator('.pdf-zoom button').first().click();
    await expect(page.locator('.pdf-zoom-info')).toHaveText('100%');
    await page.setViewportSize({ width: 1440, height: 600 });
    await expect.poll(() => viewport.locator('canvas').evaluate(canvas => canvas.getBoundingClientRect().height)).toBeLessThan(450);
    const canvas = await viewport.locator('canvas').boundingBox();
    const resized = await viewport.boundingBox();
    expect(canvas.height).toBeLessThanOrEqual(resized.height - 22);
    await page.goto(`${path}?kp=reading&view=original&nav=source&pdfPage=20`);
    await expectPdf(page, 20);
    await page.keyboard.press('PageDown');
    await expect(page.locator('.pdf-page-info')).toHaveText('20 / 20');
  });
}

for (const student of [false, true]) {
  for (const theme of ['quiet', 'nasa']) {
    for (const width of [375, 768, 1440]) {
      test(`${student ? 'student' : 'parent'} ${theme} ${width}px compares lecture and original without losing Chat`, async ({ page }, testInfo) => {
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.setViewportSize({ width, height: 900 });
        await page.addInitScript(value => localStorage.setItem('theme', value), theme);
        const requests = await installOriginal(page, { marker: 12, student, longLesson: true });
        const path = student ? '/education/learn/assignment-1' : '/textbooks/book-1';
        await page.goto(`${path}?kp=reading&view=material&nav=knowledge`);
        const question = page.getByRole('textbox', { name: '讲义问题' });
        await expect(question).toBeEnabled();
        await question.fill('对照原书之后继续提问');
        await question.evaluate(element => { element.dataset.draftIdentity = 'keep'; });
        await page.getByRole('button', { name: '对照原书', exact: true }).click();
        await expectPdf(page, 12);
        await expect(question).toHaveValue('对照原书之后继续提问');
        await expect(question).toHaveAttribute('data-draft-identity', 'keep');
        await question.press('PageDown');
        await expect(page.locator('.pdf-page-info')).toHaveText('12 / 20');
        const pdf = page.getByRole('region', { name: 'PDF', exact: true });
        await pdf.focus();
        await pdf.press('PageDown');
        await expectPdf(page, 13);
        await expect(page).toHaveURL(/comparePage=13/);
        const left = await page.locator('.book-lesson-primary').boundingBox();
        const right = await page.getByRole('complementary', { name: '原书对照' }).boundingBox();
        if (width >= 1440) {
          expect(right.x).toBeGreaterThanOrEqual(left.x + left.width - 1);
          expect(Math.abs(right.y - left.y)).toBeLessThan(2);
        } else {
          expect(right.y).toBeGreaterThanOrEqual(left.y + left.height - 1);
        }
        const canvas = await pdf.locator('canvas').boundingBox();
        const viewport = await pdf.boundingBox();
        expect(canvas.height).toBeLessThanOrEqual(viewport.height - 22);
        expect(canvas.width).toBeLessThanOrEqual(viewport.width);
        const lecture = page.getByRole('region', { name: '讲义与问答' });
        await expect.poll(() => lecture.evaluate(element => element.scrollHeight > element.clientHeight)).toBe(true);
        await lecture.evaluate(element => { element.scrollTop = 250; });
        expect(await lecture.evaluate(element => element.scrollTop)).toBe(250);
        expect(await pdf.evaluate(element => element.scrollTop)).toBe(0);
        await pdf.evaluate(element => element.dispatchEvent(new WheelEvent('wheel', { deltaY: 100, bubbles: true, cancelable: true })));
        await expectPdf(page, 14);
        expect(await lecture.evaluate(element => element.scrollTop)).toBe(250);
        await lecture.evaluate(element => { element.scrollTop = 0; });
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
        await page.screenshot({ path: testInfo.outputPath(`comparison-${student ? 'student' : 'parent'}-${theme}-${width}.png`) });
        await page.getByRole('complementary', { name: '原书对照' }).getByRole('button', { name: '关闭', exact: true }).click();
        await expect(page.locator('.react-pdf__Page canvas')).toHaveCount(0);
        await expect(question).toHaveValue('对照原书之后继续提问');
        await expect(question).toHaveAttribute('data-draft-identity', 'keep');
        await page.getByRole('button', { name: '对照原书', exact: true }).click();
        await expectPdf(page, 14);
        expect(requests.downloads()).toBe(1);
        await page.reload();
        await expectPdf(page, 14);
        await expect(question).toBeEnabled();
        expect(errors).toEqual([]);
      });
    }
  }
}

test('no location opens original at page one; JSON alone opens its start page', async ({ page }) => {
  await installOriginal(page);
  await page.goto('/textbooks/book-1?node=unit-1&view=original&nav=source', { waitUntil: 'domcontentloaded' });
  await expectPdf(page, 1);
  await installOriginal(page, { jsonPage: 12 });
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expectPdf(page, 12);
});

test('directory tabs select PDF and Markdown separately and an out-of-range page stays readable', async ({ page }) => {
  await installOriginal(page, { jsonPage: 300 });
  await page.goto('/textbooks/book-1?kp=reading&view=material');
  await page.getByRole('tab', { name: '原始教材', exact: true }).click();
  await page.getByRole('button', { name: '打开 章节一' }).click();
  await expectPdf(page, 1);
  await expect(page).toHaveURL(/view=original/);
  await page.getByRole('tab', { name: '文字目录', exact: true }).click();
  await expect(page.getByText('Paragraph 1:', { exact: false })).toBeVisible();
  await expect(page).toHaveURL(/view=source/);
});

test('original unavailable has a retry and text reading remains available', async ({ page }) => {
  await installOriginal(page, { missing: true });
  await page.goto('/textbooks/book-1?kp=reading&view=original');
  await expect(page.getByRole('alert')).toHaveText('原文件暂不可读，请重试或切换文字目录。');
  await expect(page.getByRole('button', { name: '重试', exact: true })).toBeVisible();
  await selectDirectoryTab(page, '文字目录');
  await expect(page.getByText('Paragraph 1:', { exact: false })).toBeVisible();
});

for (const theme of ['quiet', 'nasa']) {
  for (const width of [375, 768, 1440]) {
    test(`student ${theme} ${width}px reads original PDF and returns to the lecture`, async ({ page }, testInfo) => {
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.setViewportSize({ width, height: 900 });
      await page.addInitScript((value) => localStorage.setItem('theme', value), theme);
      await installOriginal(page, { marker: 12, student: true });
      await page.goto('/education/learn/assignment-1?kp=reading&view=original&nav=source');
      await expectPdf(page, 12);
      await page.locator('.pdf-nav button').last().click();
      await expectPdf(page, 13);
      await page.reload();
      await expectPdf(page, 13);
      const selectTab = async (name) => {
        if (width < 1024) await page.getByRole('button', { name: '打开教材目录', exact: true }).click();
        await page.getByRole('tab', { name, exact: true }).click();
        const dialog = page.getByRole('dialog');
        if (width < 1024 && await dialog.isVisible()) await page.keyboard.press('Escape');
      };
      await selectTab('文字目录');
      await expect(page.getByText('Paragraph 1:', { exact: false })).toBeVisible();
      await selectTab('原始教材');
      await expectPdf(page, 13);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
      await page.screenshot({ path: testInfo.outputPath(`student-original-${theme}-${width}.png`) });
      await selectTab('知识点');
      await expect(page.getByRole('textbox', { name: '讲义问题' })).toBeEnabled();
      await expect(page).not.toHaveURL(/pdfPage=/);
      expect(errors).toEqual([]);
    });
  }
}
