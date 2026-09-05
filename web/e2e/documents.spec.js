import { Buffer } from 'node:buffer';
import {
  configureSSE,
  expect,
  getCapturedRequests,
  mockAPI,
  resetMockServer,
  test,
} from './fixtures.js';

const browserErrors = new WeakMap();

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

const dataset = {
  dataset_id: 'dts-A1b2C3d4E5f6',
  name: 'Mathematics',
  description: 'Reusable mathematics source material',
  document_count: 21,
  created_at: '2026-09-01T00:00:00Z',
  updated_at: '2026-09-05T00:00:00Z',
};

const tag = {
  tag_id: 'tag-A1b2C3d4E5f6',
  name: 'Textbook',
  document_count: 1,
  created_at: '2026-09-01T00:00:00Z',
  updated_at: '2026-09-05T00:00:00Z',
};

const document = {
  document_id: 'doc-A1b2C3d4E5f6',
  original_filename: 'algebra-textbook.pdf',
  media_type: 'application/pdf',
  document_format: 'pdf',
  source_size_bytes: 2_621_440,
  source_sha256: 'a'.repeat(64),
  datasets: [{ dataset_id: dataset.dataset_id, name: dataset.name }],
  tags: [{ tag_id: tag.tag_id, name: tag.name }],
  classification: 'text_based',
  parse_status: 'completed',
  created_at: '2026-09-05T00:00:00Z',
  updated_at: '2026-09-05T00:00:00Z',
};

const inspectionOutcome = {
  inspection: {
    inspection_id: 'ins-A1b2C3d4E5f6',
    document_id: document.document_id,
    inspector_id: 'pdf-inspector',
    inspector_name: 'PDF Inspector',
    inspector_version: '1.17.0',
    status: 'completed',
    detected_format: 'pdf',
    classification: 'text_based',
    summary: {
      page_count: 128,
      page_dimensions: [{ width_points: 612, height_points: 792 }],
    },
    details: {},
  },
  parser_options: [
    {
      parser_id: 'anydoc-local',
      display_name: 'AnyDoc Local',
      version: '0.2.4',
      supported_formats: ['pdf'],
      supported_classifications: ['text_based', 'mixed'],
      available: true,
      reason: 'Best fit for a digital PDF.',
      warning: null,
      recommended: true,
    },
    {
      parser_id: 'legacy-pdf-text',
      display_name: 'Legacy PDF text',
      version: null,
      supported_formats: ['pdf'],
      supported_classifications: ['text_based', 'mixed', 'scanned', 'image_based'],
      available: true,
      reason: 'Use when the suggested method is incomplete.',
      warning: 'Scanned pages may produce little text.',
      recommended: false,
    },
    {
      parser_id: 'ocr-document',
      display_name: 'OCR document',
      version: null,
      supported_formats: ['pdf'],
      supported_classifications: ['scanned', 'image_based'],
      available: false,
      reason: 'Reserved for a future OCR service.',
      warning: null,
      recommended: false,
    },
  ],
};

function parseJob(status, version, overrides = {}) {
  return {
    job_id: 'job-A1b2C3d4E5f6',
    document_id: document.document_id,
    inspection_id: inspectionOutcome.inspection.inspection_id,
    parser_id: 'anydoc-local',
    parser_name: 'AnyDoc Local',
    parser_version: '0.2.4',
    parser_options: {},
    request_mode: 'async',
    status,
    stage: status === 'completed' ? 'completed' : status === 'queued' ? 'queued' : 'parsing',
    percentage: status === 'completed' ? 100 : status === 'queued' ? 0 : 55,
    status_version: version,
    attempt_count: 1,
    ...overrides,
  };
}

const artifacts = [
  {
    artifact_id: 'art-A1b2C3d4E5f6',
    document_id: document.document_id,
    producer_job_id: 'job-A1b2C3d4E5f6',
    artifact_kind: 'primary_document',
    format: 'markdown',
    media_type: 'text/markdown',
    relative_path: 'document.md',
  },
  {
    artifact_id: 'art-B1b2C3d4E5f6',
    document_id: document.document_id,
    producer_job_id: 'job-A1b2C3d4E5f6',
    artifact_kind: 'structured_data',
    format: 'json',
    media_type: 'application/json',
    relative_path: 'document.json',
  },
  {
    artifact_id: 'art-C1b2C3d4E5f6',
    document_id: document.document_id,
    producer_job_id: 'job-A1b2C3d4E5f6',
    artifact_kind: 'embedded_image',
    format: 'png',
    media_type: 'image/png',
    relative_path: 'images/page-1.png',
  },
  {
    artifact_id: 'art-D1b2C3d4E5f6',
    document_id: document.document_id,
    producer_job_id: 'job-A1b2C3d4E5f6',
    artifact_kind: 'manifest',
    format: 'json',
    media_type: 'application/json',
    relative_path: 'manifest.json',
  },
];

function fulfillJSON(route, body, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

async function mockDocumentLibrary(page) {
  let parseJobCreates = 0;
  const documentQueries = [];
  const completed = parseJob('completed', 3, { completed_at: '2026-09-05T00:03:00Z' });
  const previous = parseJob('completed', 8, {
    job_id: 'job-Z9y8X7w6V5u4',
    parser_id: 'legacy-pdf-text',
    parser_name: 'Legacy PDF text',
  });

  await configureSSE({
    method: 'GET',
    path: '/api/v1/document-jobs/job-A1b2C3d4E5f6/events',
    delay: 80,
    responses: [
      { events: [{ event: 'snapshot', data: parseJob('running', 2) }] },
      { events: [{ event: 'snapshot', data: completed }] },
    ],
  });

  await mockAPI(page, {
    'GET /auth/me': parent,
    'GET /document-datasets': { items: [dataset], total: 1, limit: 100, offset: 0 },
    'GET /document-datasets/*': dataset,
    'GET /document-tags': [tag],
    'GET /documents': async (route) => {
      const url = new URL(route.request().url());
      documentQueries.push(url.search);
      return fulfillJSON(route, {
        items: [document],
        total: url.searchParams.get('dataset_id') ? 1 : 21,
        limit: 20,
        offset: Number(url.searchParams.get('offset') ?? 0),
      });
    },
    'GET /documents/*': document,
    'POST /documents': (route) => fulfillJSON(route, document, 201),
    'POST /documents/*/inspections': (route) => fulfillJSON(route, inspectionOutcome, 201),
    'GET /documents/*/parse-jobs': { items: [completed, previous], total: 2, limit: 50, offset: 0 },
    'POST /documents/*/parse-jobs': (route) => {
      parseJobCreates += 1;
      return fulfillJSON(route, parseJob('queued', 1), 202);
    },
    'GET /documents/*/artifacts': { items: artifacts, total: artifacts.length, limit: 100, offset: 0 },
    'GET /document-artifacts/*/download': (route) => route.fulfill({
      status: 200,
      contentType: 'text/markdown',
      body: '# Algebra foundations\n\nA reusable lesson extracted from the uploaded PDF.',
    }),
  });

  return {
    documentQueries,
    parseJobCreates: () => parseJobCreates,
  };
}

test.beforeEach(async ({ page }) => {
  await resetMockServer();
  await page.route('https://fonts.googleapis.com/**', (route) => route.fulfill({
    status: 200,
    contentType: 'text/css',
    body: '',
  }));
  await configureSSE({
    method: 'GET',
    path: '/api/v1/users/me/thread-events',
    delay: 10_000,
    events: [
      { event: 'keepalive', data: { status: 'alive' } },
      { event: 'keepalive', data: { status: 'alive' } },
    ],
  });
  const errors = [];
  browserErrors.set(page, errors);
  page.on('console', (message) => {
    if (message.type() === 'error') {
      const source = message.location().url;
      errors.push(source ? `${message.text()} (${source})` : message.text());
    }
  });
  page.on('pageerror', (error) => errors.push(error.message));
});

test.afterEach(async ({ page }) => {
  expect(browserErrors.get(page) ?? []).toEqual([]);
});

test('browses datasets and all documents with responsive filtering and pagination', async ({ page }) => {
  const state = await mockDocumentLibrary(page);
  await page.goto('/documents');

  await expect(page.getByRole('heading', { name: 'Knowledge Library' })).toBeVisible();
  await expect(page.getByRole('tab', { name: 'Datasets' })).toHaveAttribute('aria-selected', 'true');
  await page.getByRole('button', { name: 'Open Mathematics' }).click();
  await expect(page.getByRole('heading', { name: 'Mathematics' })).toBeVisible();
  await page.getByRole('button', { name: 'Back to datasets' }).click();

  await page.getByRole('tab', { name: 'All documents' }).click();
  await expect(page.getByRole('table', { name: 'Documents' })).toBeVisible();
  await page.getByLabel('Classification').selectOption('text_based');
  await expect.poll(() => state.documentQueries.some((query) => query.includes('classification=text_based'))).toBe(true);
  await page.getByRole('button', { name: 'Next page' }).click();
  await expect(page).toHaveURL(/documents_page=2/);
  await expect.poll(() => state.documentQueries.some((query) => query.includes('offset=20'))).toBe(true);

  const viewport = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  expect(viewport.scrollWidth).toBeLessThanOrEqual(viewport.clientWidth);
  if (test.info().project.name === 'documents-mobile') {
    const table = page.locator('.documents-table-wrap');
    await expect.poll(() => table.evaluate((element) => element.scrollWidth > element.clientWidth)).toBe(true);
  }
});

test('waits for an explicit method choice, then shows progress and extensible artifacts', async ({ page }) => {
  const state = await mockDocumentLibrary(page);
  await page.goto('/documents');
  await page.getByRole('button', { name: 'Upload file' }).click();
  await page.getByLabel('PDF file').setInputFiles({
    name: document.original_filename,
    mimeType: 'application/pdf',
    buffer: Buffer.from('%PDF-1.7\nfixture\n%%EOF\n'),
  });
  await page.getByRole('checkbox', { name: dataset.name }).check();
  await page.getByRole('checkbox', { name: tag.name }).check();
  await page.getByRole('button', { name: 'Upload and inspect' }).click();

  await expect(page.getByRole('heading', { name: 'File summary' })).toBeVisible();
  await expect(page.getByText('128 pages')).toBeVisible();
  await expect(page.getByText('612 × 792 pt')).toBeVisible();
  await expect(page.getByText('Digital text', { exact: true })).toBeVisible();
  expect(state.parseJobCreates()).toBe(0);

  await page.getByRole('button', { name: 'Choose method' }).click();
  const start = page.getByRole('button', { name: 'Start parsing' });
  await expect(start).toBeDisabled();
  await expect(page.getByRole('radio', { name: /OCR document/ })).toBeDisabled();
  await page.getByRole('radio', { name: /AnyDoc Local/ }).check();
  expect(state.parseJobCreates()).toBe(0);
  await start.click();

  await expect.poll(state.parseJobCreates).toBe(1);
  await expect(page.getByRole('heading', { name: 'Parsing result' })).toBeVisible();
  const streamRequests = (await getCapturedRequests()).filter((request) => (
    request.url.startsWith('/api/v1/document-jobs/job-A1b2C3d4E5f6/events')
  ));
  expect(streamRequests).toHaveLength(2);
  expect(streamRequests[1].url).toContain('after_status_version=2');
  await expect(page.getByText('Algebra foundations')).toBeVisible();
  for (const artifact of artifacts) {
    await expect(page.getByRole('link', { name: `Download ${artifact.relative_path}` })).toBeVisible();
  }
  await expect(page.getByRole('heading', { name: 'Previous runs' })).toBeVisible();
  await expect(page.getByText('Legacy PDF text', { exact: true })).toBeVisible();
});

test('hides the knowledge library navigation from students', async ({ page }) => {
  await mockAPI(page, {
    'GET /auth/me': student,
    'GET /education/dictionaries': {
      timezone: 'Asia/Tokyo',
      subjects: [],
      grade_levels: [],
      practice_sources: [],
    },
    'GET /education/tasks': [],
    'GET /education/learning': [],
  });
  await page.goto('/education');
  await expect(page.locator('a[href="/documents"], button[aria-label="Knowledge Library"]')).toHaveCount(0);
  await expect(page.getByText('Knowledge Library', { exact: true })).toHaveCount(0);
});
