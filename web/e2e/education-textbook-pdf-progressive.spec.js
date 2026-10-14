import { expect, mockAPI, resetMockServer, test } from './fixtures.js';
import { installProcessingMocks, processingJob } from './helpers/textbookProcessingFixtures.js';
import { createLargePdf, startPdfRangeServer } from './helpers/pdfRangeServer.js';
import { readFileSync } from 'node:fs';
import { Buffer } from 'node:buffer';

const pdf = process.env.PDF_PERF_FIXTURE ? readFileSync(process.env.PDF_PERF_FIXTURE) : createLargePdf();
test.use({ locale: 'zh-CN' });
test.beforeEach(async () => { await resetMockServer(); });
test.afterEach(async ({ page }) => { await page.close(); await resetMockServer(); });

async function installPdf(page, server) {
  await installProcessingMocks(page, { getJob: () => ({ ...processingJob(), status: 'succeeded' }), ready: true, withCurrentJob: false });
  await mockAPI(page, {
    'GET /education/textbooks/book-1/original': route => route.fulfill({ status: 302, headers: { location: server.url } }),
    'GET /education/textbooks/book-1/original-location': { page: 12 },
    'GET /education/textbooks/book-1/reading-state': [],
  });
}

test('target PDF page is readable before the full response finishes', async ({ page, context }, testInfo) => {
  const server = await startPdfRangeServer(pdf);
  try {
    await context.addCookies([{ name: 'pdf-test-session', value: 'authenticated', url: server.url }]);
    await installPdf(page, server);
    const startedAt = Date.now();
    await page.goto(`${process.env.PDF_TEST_ORIGIN ?? ''}/textbooks/book-1?kp=reading&view=original&nav=source`, { waitUntil: 'domcontentloaded' });
    const canvas = page.locator('.react-pdf__Page[data-page-number="12"] canvas');
    await expect(canvas).toBeVisible();
    await expect.poll(() => canvas.evaluate(node => {
      const data = node.getContext('2d').getImageData(0, 0, node.width, node.height).data;
      return data.some((value, index) => index % 4 === 0 && value < 180 && data[index + 3] > 0);
    })).toBe(true);
    const firstReadableMs = Date.now() - startedAt;
    console.log(JSON.stringify({ firstReadableMs, size: pdf.length, bytesBeforeReadable: server.requests.reduce((sum, request) => sum + request.bytesSent, 0), rangeRequests: server.requests.filter(request => request.range).length }));
    await testInfo.attach('progressive-metrics', { body: JSON.stringify({ firstReadableMs, size: pdf.length, requests: server.requests }), contentType: 'application/json' });
    const full = server.requests.find(request => !request.range);
    expect(full).toBeTruthy();
    expect(full.finished).toBe(false);
    expect(server.requests.reduce((sum, request) => sum + request.bytesSent, 0)).toBeLessThan(pdf.length);
    expect(server.requests.some(request => request.range)).toBe(true);
    expect(server.requests.every(request => request.cookie.includes('pdf-test-session=authenticated'))).toBe(true);
    await page.screenshot({ path: testInfo.outputPath('progressive-page.png') });
  } finally { await page.close(); await server.close(); }
});

test('URL loading falls back to a full response when Range is unavailable', async ({ page, context }) => {
  const server = await startPdfRangeServer(pdf, { ranges: false, delay: 1 });
  try {
    await context.addCookies([{ name: 'pdf-test-session', value: 'authenticated', url: server.url }]);
    await installPdf(page, server);
    await page.goto(`${process.env.PDF_TEST_ORIGIN ?? ''}/textbooks/book-1?kp=reading&view=original&nav=source`, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('.react-pdf__Page[data-page-number="12"] canvas')).toBeVisible();
    expect(server.requests).toHaveLength(1);
    expect(server.requests[0].finished).toBe(true);
  } finally { await page.close(); await server.close(); }
});

test('leaving the original cancels pending PDF downloads without showing an error', async ({ page, context }) => {
  const server = await startPdfRangeServer(pdf, { delay: 200 });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  try {
    await context.addCookies([{ name: 'pdf-test-session', value: 'authenticated', url: server.url }]);
    await installPdf(page, server);
    await page.goto(`${process.env.PDF_TEST_ORIGIN ?? ''}/textbooks/book-1?kp=reading&view=original&nav=source`, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('.react-pdf__Page[data-page-number="12"] canvas')).toBeVisible();
    await page.getByRole('tab', { name: '文字目录', exact: true }).click();
    await expect(page.getByText('Paragraph 1:', { exact: false })).toBeVisible();
    await expect.poll(() => server.requests.filter(request => !request.range).every(request => request.cancelled)).toBe(true);
    expect(errors).toEqual([]);
    await expect(page.getByRole('alert')).toHaveCount(0);
  } finally { await page.close(); await server.close(); }
});

test('permission errors show retry without starting another download path', async ({ page }) => {
  await installProcessingMocks(page, { getJob: () => ({ ...processingJob(), status: 'succeeded' }), ready: true, withCurrentJob: false });
  let requests = 0;
  await mockAPI(page, {
    'GET /education/textbooks/book-1/original': route => { requests++; return route.fulfill({ status: 403, contentType: 'application/json', body: '{"detail":"Forbidden"}' }); },
    'GET /education/textbooks/book-1/original-location': { page: 12 },
    'GET /education/textbooks/book-1/reading-state': [],
  });
  await page.goto(`${process.env.PDF_TEST_ORIGIN ?? ''}/textbooks/book-1?kp=reading&view=original&nav=source`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('alert')).toContainText('原文件暂不可读');
  expect(requests).toBe(1);
  await page.getByRole('button', { name: '重试', exact: true }).click();
  await expect.poll(() => requests).toBe(2);
  await expect(page.getByRole('alert')).toContainText('原文件暂不可读');
});

for (const buffered of [true, false]) {
  test(`performance probe ${buffered ? 'buffered baseline' : 'progressive URL'}`, async ({ page, context }) => {
    test.skip(process.env.PDF_PERF_BENCHMARK !== '1', 'opt-in read-only performance measurements');
    test.setTimeout(120_000);
    const measurements = [];
    const delay = Number(process.env.PDF_PERF_DELAY ?? 1);
    for (let sample = 0; sample < 3; sample++) {
      const server = await startPdfRangeServer(pdf, { delay });
      try {
        await context.addCookies([{ name: 'pdf-test-session', value: 'authenticated', url: server.url }]);
        await installPdf(page, server);
        if (buffered) {
          // Reproduce the old reader's contract: no PDF parsing before all bytes arrive.
          await page.route('**/api/v1/education/textbooks/book-1/original', async route => {
            const response = await fetch(server.url, { headers: { cookie: 'pdf-test-session=authenticated' } });
            const bytes = await response.arrayBuffer();
            await route.fulfill({ contentType: 'application/pdf', body: Buffer.from(bytes) });
          });
        }
        const started = Date.now();
        await page.goto(`${process.env.PDF_TEST_ORIGIN ?? ''}/textbooks/book-1?kp=reading&view=original&nav=source`, { waitUntil: 'domcontentloaded' });
        const canvas = page.locator('.react-pdf__Page[data-page-number="12"] canvas');
        await expect(canvas).toBeVisible({ timeout: 60_000 });
        await expect.poll(() => canvas.evaluate(node => {
          const pixels = node.getContext('2d').getImageData(0, 0, node.width, node.height).data;
          return pixels.some((value, index) => index % 4 === 0 && value < 180 && pixels[index + 3] > 0);
        }), { timeout: 60_000 }).toBe(true);
        measurements.push({ firstReadableMs: Date.now() - started, bytesBeforeReadable: server.requests.reduce((sum, request) => sum + request.bytesSent, 0), rangeRequests: server.requests.filter(request => request.range).length, fullFinished: server.requests.find(request => !request.range)?.finished });
        await page.goto('about:blank');
        await page.unroute('**/api/v1/education/textbooks/book-1/original');
      } finally { await server.close(); }
    }
    console.log(JSON.stringify({ mode: buffered ? 'buffered' : 'progressive', size: pdf.length, delay, measurements }));
  });
}
