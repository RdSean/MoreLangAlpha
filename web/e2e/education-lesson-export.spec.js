import { expect, mockAPI, resetMockServer, test } from './fixtures.js';

test.use({ locale: 'zh-CN', screenshot: 'only-on-failure' });

const point = {
  knowledge_point_id: 'kp-1', skill_kp_id: 'place-value', position: 1,
  title: '位值与运算', unit_skill_node_id: 'chapter-1', node_skill_ids: [],
  start_line: 1, end_line: 20, content_file: 'materials/kp-1.md', material_available: true,
};
const structure = {
  textbook_id: 'book-1', assignment_id: 'assignment-1', textbook_title: '数学教材',
  structure_id: 'structure-1', schema_version: '2.1.0', warnings: [],
  structure: {
    schema_version: '2.1.0', book: { title: '数学教材' },
    source: { path: 'source.md', total_lines: 20 }, coverage: {},
    nodes: [{ id: 'chapter-1', title: '第一章', anchor: { start_line: 1, end_line: 20 }, children: [] }],
  },
  knowledge_points: [point],
};
const material = {
  textbook_id: 'book-1', assignment_id: 'assignment-1', knowledge_point_id: 'kp-1',
  skill_kp_id: 'place-value', material_available: true,
  markdown: '## 位值\n\n先看一看这个算式：$12 \\times 3 = 36$。\n\n|数量|结果|\n|---|---|\n|12|36|',
  generated_at: '2026-10-09T00:00:00Z', depth: 'lesson', requirements: null, content_sha256: 'a'.repeat(64),
};

async function prepare(page, role, exports, failFirst = false) {
  await mockAPI(page, {
    'GET /auth/me': { user_id: `${role}-1`, email: `${role}@example.test`, name: role, role, household_id: 'household-1' },
    'GET /education/textbooks/book-1': {
      textbook_id: 'book-1', title: '数学教材', structure_status: 'ready',
      materials: { total: 1, ready: 1 }, current_job: null, recent_job: null,
      current_structure_id: 'structure-1', assigned_student_count: 1,
      updated_at: '2026-10-09T00:00:00Z',
      source: { document_id: 'doc-1', filename: 'math.pdf', media_type: 'application/pdf', size_bytes: 1000, image_count: 0 },
    },
    'GET /education/textbooks/book-1/structure': structure,
    'GET /education/learning/assignment-1/structure': structure,
    'GET /education/textbooks/book-1/knowledge-points/kp-1/material': material,
    'GET /education/learning/assignment-1/knowledge-points/kp-1': material,
    'GET /education/learning/assignment-1/items': [],
    'GET /education/textbooks/book-1/reading-state': {},
    'POST /education/textbooks/book-1/knowledge-points/kp-1/reading-state': {},
    'GET /education/textbooks/book-1/knowledge-points/kp-1/questions': [
      { role: 'user', content: '为什么这样计算？' },
      { role: 'assistant', content: '我们可以把数量分成三组。', reasoning: 'PRIVATE_REASONING' },
      { role: 'tool', content: 'PRIVATE_TOOL' },
      { role: 'assistant', content: 'PRIVATE_THOUGHT', content_type: 'reasoning' },
    ],
    'POST /education/textbooks/book-1/knowledge-points/kp-1/export-pdf': async (route) => {
      exports.push(route.request().postDataJSON());
      if (failFirst && exports.length === 1) {
        return route.fulfill({ status: 502, contentType: 'application/json', body: JSON.stringify({ detail: 'PDF 内容未能完整生成，请稍后重试。' }) });
      }
      // This checks the browser download contract, not actual PDF rendering.
      return route.fulfill({ status: 200, contentType: 'application/pdf', headers: { 'Content-Disposition': "attachment; filename*=UTF-8''%E4%BD%8D%E5%80%BC.pdf" }, body: '%PDF-test-download' });
    },
  });
  await page.goto(role === 'parent'
    ? '/textbooks/book-1?kp=place-value&view=material'
    : '/education/learn/assignment-1?kp=place-value&view=material');
  await expect(page.getByRole('button', { name: '导出讲义 PDF', exact: true })).toBeVisible();
}

test.beforeEach(async () => { await resetMockServer(); });

for (const role of ['parent', 'student']) {
  for (const mobile of [false, true]) {
    test(`${role} exports public lesson and own Q&A (${mobile ? 'mobile dark' : 'desktop light'})`, async ({ page }) => {
      await page.setViewportSize(mobile ? { width: 375, height: 812 } : { width: 1440, height: 900 });
      await page.emulateMedia({ colorScheme: mobile ? 'dark' : 'light' });
      const exports = [];
      await prepare(page, role, exports);
      let download = page.waitForEvent('download');
      await page.getByRole('button', { name: '导出讲义 PDF', exact: true }).click();
      expect((await download).suggestedFilename()).toBe('位值.pdf');
      expect(exports[0].include_questions).toBe(false);
      expect(exports[0].sections.map((section) => section.role)).toEqual(['material']);
      expect(exports[0].sections[0].html).toContain('class="katex');
      expect(exports[0].sections[0].html).toContain('<table');
      expect(exports[0].font_css).toContain('data:font/woff2;base64,');
      await page.getByRole('button', { name: 'PDF 导出选项' }).click();
      const questionOption = page.getByRole('menuitem', { name: '讲义及我的问答' });
      await expect(questionOption).toBeEnabled();
      download = page.waitForEvent('download');
      await questionOption.click();
      await download;
      expect(exports[1].sections.map((section) => section.role)).toEqual(['material', 'user', 'assistant']);
      expect(exports[1].assignment_id).toBe(role === 'student' ? 'assignment-1' : undefined);
      expect(JSON.stringify(exports[1])).not.toContain('PRIVATE');
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      const header = page.locator('.book-reader-header');
      const headerBox = await header.boundingBox();
      const buttonBox = await page.getByRole('button', { name: '导出讲义 PDF', exact: true }).boundingBox();
      expect(buttonBox.y + buttonBox.height).toBeLessThanOrEqual(headerBox.y + headerBox.height);
    });
  }
}

test('failed export remains on the lesson and can be retried', async ({ page }) => {
  const exports = [];
  await prepare(page, 'parent', exports, true);
  await page.getByRole('button', { name: '导出讲义 PDF', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('PDF 内容未能完整生成');
  await expect(page).toHaveURL(/\/textbooks\/book-1/);
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: '导出讲义 PDF', exact: true }).click();
  await download;
  expect(exports).toHaveLength(2);
});
