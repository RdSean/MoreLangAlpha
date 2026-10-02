import { Buffer } from 'node:buffer';
import { readFileSync } from 'node:fs';
import {
  configureSSE,
  expect,
  getCapturedRequests,
  mockAPI,
  resetMockServer,
  test,
} from './fixtures.js';

const browserErrors = new WeakMap();
const sourcePdf = readFileSync(new URL('../../tests/fixtures/documents/text.pdf', import.meta.url));

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

const textbookAssets = {
  textbookId: 'textbook-A1b2C3d4E5f6',
  structureId: 'structure-A1b2C3d4E5f6',
  jobId: 'book-job-A1b2C3d4E5f6',
  knowledgePointId: 'knowledge-point-A1b2C3d4E5f6',
  title: 'Algebra Reader',
  completedAt: '2026-09-05T00:03:00Z',
};

const completedParseJobCandidate = {
  document_id: document.document_id,
  parse_job_id: 'job-A1b2C3d4E5f6',
  primary_artifact_id: 'art-A1b2C3d4E5f6',
  filename: document.original_filename,
  media_type: document.media_type,
  parser_id: 'anydoc-local',
  parser_name: 'AnyDoc Local',
  completed_at: textbookAssets.completedAt,
  content_sha256: 'a'.repeat(64),
  size_bytes: document.source_size_bytes,
  image_count: 1,
};

const frozenTextbookSource = {
  ...completedParseJobCandidate,
  frozen_at: '2026-09-05T00:04:00Z',
};

function documentTeachingUsage() {
  return {
    document_id: document.document_id,
    parse_job_id: completedParseJobCandidate.parse_job_id,
    primary_artifact_id: completedParseJobCandidate.primary_artifact_id,
    textbook_id: textbookAssets.textbookId,
    textbook_title: textbookAssets.title,
    source_filename: completedParseJobCandidate.filename,
    source_completed_at: completedParseJobCandidate.completed_at,
    structure_status: 'ready',
    materials: { ready: 0, total: 1 },
    updated_at: '2026-09-05T00:05:00Z',
  };
}

function fulfillJSON(route, body, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

const sensitiveNetworkPatterns = [
  /storage_key|snapshot_prefix|bundle_prefix|sandbox_path|managed_path|object_url|download_url|presigned|minio|\/managed\//i,
  /(?:^|["'\s])(?:education|documents)\/[A-Za-z0-9][A-Za-z0-9_-]{5,}(?:\/|["'\s]|$)/i,
  /https?:\/\/[^/"'\s]+\/(?:[^/"'\s]+\/)?(?:education|documents)\/[A-Za-z0-9][A-Za-z0-9_-]{5,}(?:\/|["'\s]|$)/i,
  /(?:[?&](?:x-amz-|awsaccesskeyid|signature)|x-amz-|awsaccesskeyid|signature=)/i,
];

function findSensitiveNetworkValue(value) {
  return sensitiveNetworkPatterns.find((pattern) => pattern.test(value));
}

function isRelevantApiPath(pathname) {
  return pathname.startsWith('/api/v1/documents')
    || pathname.startsWith('/api/v1/document-')
    || pathname.startsWith('/api/v1/education');
}

async function mockDocumentLibrary(page, artifactItems = artifacts) {
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
    'GET /documents/*/artifacts': { items: artifactItems, total: artifactItems.length, limit: 100, offset: 0 },
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

async function mockLibraryTextbookWorkbench(page) {
  let textbookCreated = false;
  let createRequest;
  const teachingUsageRequests = [];
  const structure = {
    textbook_id: textbookAssets.textbookId,
    structure_id: textbookAssets.structureId,
    schema_version: '2.1.0',
    warnings: [],
    structure: {
      schema_version: '2.1.0',
      book: { title: textbookAssets.title },
      source: { path: 'source.md', total_lines: 24 },
      coverage: {},
      nodes: [{
        id: 'unit-algebra',
        title: '代数基础',
        anchor: { start_line: 1, end_line: 24 },
        children: [],
      }],
    },
    knowledge_points: [{
      knowledge_point_id: textbookAssets.knowledgePointId,
      skill_kp_id: 'variables-and-equations',
      position: 1,
      title: '变量与方程',
      unit_skill_node_id: 'unit-algebra',
      node_skill_ids: [],
      start_line: 4,
      end_line: 12,
      content_file: null,
      material_available: false,
    }],
  };
  const bookJob = {
    job_id: textbookAssets.jobId,
    textbook_id: textbookAssets.textbookId,
    kind: 'structure',
    status: 'succeeded',
    total_items: 1,
    succeeded_items: 1,
    failed_items: 0,
    cancelled_items: 0,
    not_run_items: 0,
    high_water_seq: 1,
    activity_status: 'available',
    created_at: '2026-09-05T00:04:00Z',
    started_at: '2026-09-05T00:04:01Z',
    finished_at: '2026-09-05T00:05:00Z',
    safe_error: null,
    depth: null,
    requirements: null,
    replace_existing: false,
    include_supplementary: false,
    items: [{
      item_id: 'book-job-item-A1b2C3d4E5f6',
      kind: 'structure',
      position: 1,
      knowledge_point_id: null,
      skill_kp_id: null,
      status: 'succeeded',
      attempt: 1,
      safe_error: null,
      started_at: '2026-09-05T00:04:01Z',
      finished_at: '2026-09-05T00:05:00Z',
    }],
  };
  const workbench = {
    textbook_id: textbookAssets.textbookId,
    title: textbookAssets.title,
    structure_status: 'ready',
    materials: { ready: 0, total: 1 },
    current_job: null,
    recent_job: bookJob,
    current_structure_id: textbookAssets.structureId,
    assigned_student_count: 0,
    updated_at: '2026-09-05T00:05:00Z',
    source: frozenTextbookSource,
  };

  await configureSSE({
    method: 'GET',
    path: `/api/v1/education/book-jobs/${textbookAssets.jobId}/events`,
    events: [{
      event: 'snapshot',
      data: {
        job_id: textbookAssets.jobId,
        status: 'succeeded',
        events: [],
        high_water_seq: 1,
        activity_status: 'available',
        cursor_expired: false,
        has_more: false,
      },
    }],
  });
  await mockDocumentLibrary(page);
  await mockAPI(page, {
    'GET /users/me': {
      user_id: parent.user_id,
      email: parent.email,
      name: parent.name,
      onboarding_completed: true,
      has_api_key: true,
      has_oauth_token: false,
      locale: 'zh-CN',
    },
    [`GET /documents/${document.document_id}/source`]: (route) => route.fulfill({
      status: 200,
      contentType: 'application/pdf',
      body: sourcePdf,
    }),
    'GET /education/textbook-sources': (route) => fulfillJSON(route, {
      items: [completedParseJobCandidate],
    }),
    [`GET /documents/${document.document_id}/teaching-usage`]: (route) => {
      teachingUsageRequests.push(new URL(route.request().url()).pathname);
      return fulfillJSON(route, {
        items: textbookCreated ? [documentTeachingUsage()] : [],
      });
    },
    'POST /education/textbooks': async (route) => {
      createRequest = route.request().postDataJSON();
      textbookCreated = true;
      await fulfillJSON(route, {
        textbook_id: textbookAssets.textbookId,
        job_id: textbookAssets.jobId,
      }, 201);
    },
    [`GET /education/textbooks/${textbookAssets.textbookId}`]: (route) => fulfillJSON(route, workbench),
    [`GET /education/textbooks/${textbookAssets.textbookId}/structure`]: (route) => fulfillJSON(route, structure),
    [`GET /education/textbooks/${textbookAssets.textbookId}/source`]: (route) => fulfillJSON(route, {
      textbook_id: textbookAssets.textbookId,
      start_line: 1,
      end_line: 24,
      total_lines: 24,
      markdown: '# 代数基础\n\n变量可以表示未知数。\n\n方程描述两个表达式相等。',
    }),
    [`GET /education/textbooks/${textbookAssets.textbookId}/knowledge-points/${textbookAssets.knowledgePointId}/material`]: (route) => fulfillJSON(route, {
      textbook_id: textbookAssets.textbookId,
      knowledge_point_id: textbookAssets.knowledgePointId,
      skill_kp_id: 'variables-and-equations',
      material_available: false,
      markdown: null,
      generated_at: null,
      depth: null,
      requirements: null,
      content_sha256: null,
    }),
    [`GET /education/book-jobs/${textbookAssets.jobId}`]: (route) => fulfillJSON(route, bookJob),
  });

  return {
    createRequest: () => createRequest,
    teachingUsageRequests: () => teachingUsageRequests,
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

  await expect(page.getByRole('heading', { name: 'Library' })).toBeVisible();
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

test('keeps the completion action visible when a parse produces many artifacts', async ({ page }) => {
  const manyArtifacts = [
    artifacts[0],
    ...Array.from({ length: 80 }, (_, index) => ({
      ...artifacts[2],
      artifact_id: `art-${String(index).padStart(12, '0')}`,
      relative_path: `images/page-${String(index + 1).padStart(3, '0')}.jpg`,
    })),
  ];
  await mockDocumentLibrary(page, manyArtifacts);
  await page.goto('/documents');
  await page.getByRole('button', { name: 'Upload file' }).click();
  await page.getByLabel('PDF file').setInputFiles({
    name: document.original_filename,
    mimeType: 'application/pdf',
    buffer: Buffer.from('%PDF-1.7\nfixture\n%%EOF\n'),
  });
  await page.getByRole('button', { name: 'Upload and inspect' }).click();
  await page.getByRole('button', { name: 'Choose method' }).click();
  await page.getByRole('radio', { name: /AnyDoc Local/ }).check();
  await page.getByRole('button', { name: 'Start parsing' }).click();

  const complete = page.getByRole('button', { name: 'Complete' });
  await expect(complete).toBeVisible();
  const list = page.locator('.documents-artifact-list');
  await expect.poll(() => list.evaluate((element) => element.scrollHeight > element.clientHeight)).toBe(true);
  const [buttonBox, viewport] = await Promise.all([
    complete.boundingBox(),
    page.evaluate(() => ({ width: window.innerWidth, height: window.innerHeight })),
  ]);
  expect(buttonBox).not.toBeNull();
  expect(buttonBox.y + buttonBox.height).toBeLessThanOrEqual(viewport.height);
});

test('library textbook workbench mock flow renders without runtime', async ({ page }) => {
  const state = await mockLibraryTextbookWorkbench(page);
  let sandboxAvailable = true;
  const sandboxRequests = [];
  const networkFindings = [];
  const inspectedResponsePaths = [];
  const pendingResponseChecks = [];
  const inspectedBodyCounts = { requests: 0, responses: 0 };
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (!isRelevantApiPath(url.pathname)) return;
    inspectedBodyCounts.requests += 1;
    const body = request.postData();
    const requestText = `${request.method()} ${url.href}\n${body ?? ''}`;
    const finding = findSensitiveNetworkValue(requestText);
    if (finding) {
      networkFindings.push(`request ${url.pathname}: ${finding} in ${requestText}`);
    }
  });
  page.on('response', (response) => {
    const url = new URL(response.url());
    if (!isRelevantApiPath(url.pathname)) return;
    inspectedBodyCounts.responses += 1;
    inspectedResponsePaths.push(url.pathname);
    const headers = Object.entries(response.headers())
      .map(([name, value]) => `${name}: ${value}`)
      .join('\n');
    pendingResponseChecks.push(response.text().then((body) => {
      const responseText = `${response.status()} ${url.href}\n${headers}\n${body}`;
      const finding = findSensitiveNetworkValue(responseText);
      if (finding) {
        networkFindings.push(`response ${url.pathname}: ${finding} in ${responseText}`);
      }
    }).catch((error) => {
      networkFindings.push(`response ${url.pathname}: ${String(error)}`);
    }));
  });
  // If either the document usage view or textbook workbench starts depending on runtime state, it will get
  // a 503 here and the zero-request assertion will also fail.
  await page.route('**/api/v1/workspaces/*/sandbox/stats', (route) => {
    const url = new URL(route.request().url());
    sandboxRequests.push(url.href);
    return route.fulfill({
      status: sandboxAvailable ? 200 : 503,
      contentType: 'application/json',
      body: JSON.stringify(sandboxAvailable ? {} : { detail: 'sandbox unavailable' }),
    });
  });

  await page.goto('/documents');
  await page.getByRole('button', { name: '上传文件' }).click();
  await page.getByLabel('PDF 文件').setInputFiles({
    name: document.original_filename,
    mimeType: document.media_type,
    buffer: Buffer.from('%PDF-1.7\nformal-assets\n%%EOF\n'),
  });
  await page.getByRole('button', { name: '上传并检测' }).click();
  await page.getByRole('button', { name: '选择方法' }).click();
  await page.getByRole('radio', { name: /AnyDoc Local/ }).check();
  await page.getByRole('button', { name: '开始解析' }).click();
  await expect(page.getByRole('heading', { name: '解析结果' })).toBeVisible();

  await page.goto(`/documents/${document.document_id}`);
  await expect(page.getByRole('tab', { name: '原文' })).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByRole('tab', { name: '解析结果' })).toBeVisible();
  await expect(page.getByRole('tab', { name: '教材资产' })).toBeVisible();
  await page.getByRole('tab', { name: '解析结果' }).click();
  await expect(page.getByText('Algebra foundations')).toBeVisible();

  await page.getByRole('button', { name: '用作教材' }).click();
  const sourceDialog = page.getByRole('dialog', { name: '选择教材来源' });
  await expect(sourceDialog.getByRole('radio', { name: /algebra-textbook\.pdf/ })).toBeChecked();
  await sourceDialog.getByLabel('教材名称').fill(textbookAssets.title);
  await sourceDialog.getByRole('button', { name: '添加并分析' }).click();

  await expect(page).toHaveURL((url) => (
    url.pathname === `/textbooks/${textbookAssets.textbookId}`
    && url.searchParams.get('activity') === textbookAssets.jobId
    && url.searchParams.get('kp') === 'variables-and-equations'
    && url.searchParams.get('view') === 'source'
  ));
  await expect(page.getByText(textbookAssets.title, { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: '变量与方程' })).toBeVisible();
  await expect(page.getByText('变量可以表示未知数。')).toBeVisible();
  await expect(page.getByRole('complementary', { name: '教材处理活动' })).toBeVisible();
  await expect.poll(state.createRequest).toEqual({
    parse_job_id: completedParseJobCandidate.parse_job_id,
    primary_artifact_id: completedParseJobCandidate.primary_artifact_id,
    title: textbookAssets.title,
    idempotency_key: expect.any(String),
  });

  sandboxAvailable = false;
  await page.goto(`/documents/${document.document_id}`);
  await page.getByRole('tab', { name: '教材资产' }).click();
  await expect(page.getByRole('link', { name: textbookAssets.title })).toHaveAttribute(
    'href',
    `/textbooks/${textbookAssets.textbookId}`,
  );
  await expect(page.getByText('结构已就绪')).toBeVisible();
  await expect(page.getByText('讲义 0 / 1')).toBeVisible();
  await expect(page.getByRole('link', { name: '打开教材' })).toBeVisible();

  await page.getByRole('link', { name: '打开教材' }).click();
  await expect(page).toHaveURL((url) => (
    url.pathname === `/textbooks/${textbookAssets.textbookId}`
    && !url.searchParams.has('activity')
    && url.searchParams.get('kp') === 'variables-and-equations'
    && url.searchParams.get('view') === 'source'
  ));
  await expect(page.getByText(textbookAssets.title, { exact: true })).toBeVisible();
  await expect(page.locator('body')).not.toContainText(/storage_key|snapshot_prefix|bundle_prefix|sandbox_path|minio/i);

  expect(state.teachingUsageRequests().length).toBeGreaterThan(0);
  for (const path of state.teachingUsageRequests()) {
    expect(path).toBe(`/api/v1/documents/${document.document_id}/teaching-usage`);
  }
  expect(sandboxRequests).toEqual([]);

  await page.waitForLoadState('networkidle');
  await Promise.all(pendingResponseChecks);
  const requiredInspectedPaths = [
    `/api/v1/documents/${document.document_id}`,
    `/api/v1/documents/${document.document_id}/teaching-usage`,
    '/api/v1/education/textbook-sources',
    '/api/v1/education/textbooks',
    `/api/v1/education/textbooks/${textbookAssets.textbookId}`,
    `/api/v1/education/textbooks/${textbookAssets.textbookId}/structure`,
  ];
  for (const path of requiredInspectedPaths) {
    expect(inspectedResponsePaths).toContain(path);
  }
  expect(inspectedBodyCounts.requests).toBeGreaterThanOrEqual(10);
  expect(inspectedBodyCounts.responses).toBeGreaterThanOrEqual(10);
  expect(networkFindings).toEqual([]);
});

test('hides the library navigation from students', async ({ page }) => {
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
  await expect(page.locator('a[href="/documents"], button[aria-label="Library"]')).toHaveCount(0);
  await expect(page.getByText('Library', { exact: true })).toHaveCount(0);
});
