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

async function installOriginal(page, { marker = null, jsonPage = null, missing = false } = {}) {
  const job = { ...processingJob(), status: 'succeeded' };
  await installProcessingMocks(page, { getJob: () => job, ready: true, withCurrentJob: false, title: '原书阅读与知识点定位测试教材 · A Book With a Longer Title' });
  let downloads = 0;
  await mockAPI(page, {
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
  });
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

for (const theme of ['light', 'dark']) {
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
      await page.locator('.pdf-nav button').last().click();
      await expectPdf(page, 13);
      await expect(page).toHaveURL(/pdfPage=13/);
      await page.reload();
      await expectPdf(page, 13);
      await page.getByRole('tab', { name: '原文', exact: true }).click();
      await expect(page.getByText('Paragraph 1:', { exact: false })).toBeVisible();
      await page.getByRole('tab', { name: '原文件', exact: true }).click();
      await expectPdf(page, 13);
      expect(requests.downloads()).toBe(2); // one load per page lifetime, not per selection/tab
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
      await page.screenshot({ path: testInfo.outputPath(`original-${theme}-${width}.png`) });
    });
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
  await page.getByRole('tab', { name: '原书目录', exact: true }).click();
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
  await page.getByRole('tab', { name: '原文', exact: true }).click();
  await expect(page.getByText('Paragraph 1:', { exact: false })).toBeVisible();
});
