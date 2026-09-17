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

const formalAssets = {
  textbookId: 'textbook-A1b2C3d4E5f6',
  versionId: 'version-A1b2C3d4E5f6',
  processingJobId: 'processing-job-A1b2C3d4E5f6',
  teachingJobId: 'teaching-job-A1b2C3d4E5f6',
  teachingPackageId: 'teaching-package-A1b2C3d4E5f6',
  publicationId: 'publication-A1b2C3d4E5f6',
  assignmentId: 'assignment-A1b2C3d4E5f6',
  chapterId: 'chapter-A1b2C3d4E5f6',
  title: 'Algebra Reader',
  completedAt: '2026-09-05T00:03:00Z',
};

const completedParseJobCandidate = {
  producer_job_id: 'job-A1b2C3d4E5f6',
  document_id: document.document_id,
  primary_artifact_id: 'art-A1b2C3d4E5f6',
  filename: document.original_filename,
  media_type: document.media_type,
  format: document.document_format,
  parser_id: 'anydoc-local',
  parser_name: 'AnyDoc Local',
  parser_version: '0.2.4',
  parse_completed_at: formalAssets.completedAt,
  size_bytes: document.source_size_bytes,
  artifact_count: artifacts.length,
};

const formalTextbookSource = {
  legacy: false,
  position: 1,
  document_id: document.document_id,
  producer_job_id: completedParseJobCandidate.producer_job_id,
  primary_artifact_id: completedParseJobCandidate.primary_artifact_id,
  filename: completedParseJobCandidate.filename,
  media_type: completedParseJobCandidate.media_type,
  format: completedParseJobCandidate.format,
  parser_id: completedParseJobCandidate.parser_id,
  parser_name: completedParseJobCandidate.parser_name,
  parser_version: completedParseJobCandidate.parser_version,
  parse_completed_at: completedParseJobCandidate.parse_completed_at,
  primary_sha256: 'a'.repeat(64),
  document_deleted: false,
  document_accessible: true,
};

function documentTeachingUsage(isPublished = false) {
  return {
    document_id: document.document_id,
    producer_job_id: completedParseJobCandidate.producer_job_id,
    primary_artifact_id: completedParseJobCandidate.primary_artifact_id,
    textbook_id: formalAssets.textbookId,
    textbook_title: formalAssets.title,
    content_version_id: formalAssets.versionId,
    content_version_sequence: 1,
    artifact_position: 1,
    teaching_package_id: formalAssets.teachingPackageId,
    teaching_package_sequence: 1,
    status: 'review',
    publication_id: isPublished ? formalAssets.publicationId : null,
    is_published: isPublished,
    has_asset_manifest: true,
    created_at: formalAssets.completedAt,
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

async function dismissTeachingRunDialog(page, dialog) {
  if (test.info().project.name === 'documents-mobile') {
    await dialog.evaluate((element) => {
      const handle = element.querySelector('.cursor-grab');
      if (!(handle instanceof HTMLElement)) {
        throw new Error('Teaching run dialog drag handle is missing');
      }
      const touchAt = (clientY) => new Touch({
        identifier: 1,
        target: handle,
        clientX: 24,
        clientY,
      });
      const start = touchAt(100);
      const end = touchAt(260);
      const event = (type, touches) => new TouchEvent(type, {
        bubbles: true,
        cancelable: true,
        composed: true,
        touches,
        targetTouches: touches,
        changedTouches: touches,
      });
      handle.dispatchEvent(event('touchstart', [start]));
      handle.dispatchEvent(event('touchmove', [end]));
      handle.dispatchEvent(event('touchend', []));
    });
  } else {
    await page.keyboard.press('Escape');
  }
  await expect(dialog).toBeHidden();
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

async function mockLibraryTextbookFormalAssets(page) {
  let textbookCreated = false;
  let processingState = 'none';
  let teachingState = 'none';
  let assigned = false;
  let startPayload;
  let publishRequest;
  let assignmentRequest;
  const teachingUsageRequests = [];
  const teachingUsagePackageIds = [];
  const assetRequests = [];
  const chapter = {
    chapter_id: formalAssets.chapterId,
    position: 1,
    slug: '01-foundations',
    title: '代数基础',
    page_start: 1,
    page_end: 12,
    markdown: '# 代数基础\n\n冻结后的图书馆 Markdown。',
    teaching_material: '# 学习目标\n\n理解变量与方程。',
    questions: [{
      question_id: 'question-A1b2C3d4E5f6',
      position: 1,
      prompt: '方程中字母通常表示什么？',
      options: { A: '变量', B: '标点' },
      correct_option: 'A',
      explanation: '字母通常表示变量。',
      knowledge_point: '变量',
    }],
  };
  const textbookDetail = () => ({
    textbook_id: formalAssets.textbookId,
    household_id: parent.household_id,
    title: formalAssets.title,
    slug: 'algebra-reader',
    versions: processingState === 'none' ? [] : [{
      version_id: formalAssets.versionId,
      sequence: 1,
      status: processingState === 'queued' ? 'processing' : processingState === 'review' ? 'review' : 'published',
      processing_job_id: formalAssets.processingJobId,
      processing_job_status: processingState === 'queued' ? 'queued' : 'completed',
      chapter_count: processingState === 'queued' ? 0 : 1,
      is_published: processingState === 'published',
      publication_id: processingState === 'published' ? formalAssets.publicationId : null,
      teaching_packages: teachingState === 'none' ? [] : [{
        teaching_package_id: formalAssets.teachingPackageId,
        job_id: formalAssets.teachingJobId,
        sequence: 1,
        status: teachingState === 'running' ? 'generating_teaching' : 'review',
        job_status: teachingState === 'running' ? 'running' : 'completed',
        chapter_count: teachingState === 'running' ? 0 : 1,
        question_count: teachingState === 'running' ? 0 : 1,
      }],
      sources: [formalTextbookSource],
      chapters: processingState === 'queued' ? [] : [chapter],
      assignments: assigned ? [{
        assignment_id: formalAssets.assignmentId,
        student_user_id: student.user_id,
        student_name: student.name,
      }] : [],
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
    'GET /auth/members': [parent, student],
    'GET /education/dictionaries': {
      timezone: 'Asia/Tokyo',
      subjects: [],
      grade_levels: [],
      practice_sources: [],
    },
    'GET /education/tasks': [],
    'GET /education/textbook-parse-jobs/completed': (route) => fulfillJSON(route, [completedParseJobCandidate]),
    [`GET /documents/${document.document_id}/teaching-usage`]: (route) => {
      teachingUsageRequests.push(new URL(route.request().url()).pathname);
      const usage = documentTeachingUsage(processingState === 'published');
      teachingUsagePackageIds.push(usage.teaching_package_id);
      return fulfillJSON(route, {
        items: [usage],
      });
    },
    'GET /education/textbooks': (route) => fulfillJSON(route, textbookCreated ? [{
      textbook_id: formalAssets.textbookId,
      household_id: parent.household_id,
      title: formalAssets.title,
      slug: 'algebra-reader',
      latest_version_sequence: processingState === 'none' ? null : 1,
      latest_version_status: processingState === 'none' ? null : processingState === 'queued' ? 'processing' : processingState === 'review' ? 'review' : 'published',
      chapter_count: processingState === 'queued' || processingState === 'none' ? 0 : 1,
      assignment_count: assigned ? 1 : 0,
    }] : []),
    'POST /education/textbooks': async (route) => {
      textbookCreated = true;
      await fulfillJSON(route, {
        textbook_id: formalAssets.textbookId,
        household_id: parent.household_id,
        title: route.request().postDataJSON().title,
        slug: 'algebra-reader',
        chapter_count: 0,
        assignment_count: 0,
      }, 201);
    },
    [`GET /education/textbooks/${formalAssets.textbookId}`]: (route) => fulfillJSON(route, textbookDetail()),
    [`POST /education/textbooks/${formalAssets.textbookId}/processing`]: async (route) => {
      startPayload = route.request().postDataJSON();
      processingState = 'queued';
      await fulfillJSON(route, {
        job_id: formalAssets.processingJobId,
        version_id: formalAssets.versionId,
        status: 'queued',
      }, 201);
    },
    [`POST /education/textbook-processing/${formalAssets.processingJobId}/run`]: async (route) => {
      processingState = 'review';
      await fulfillJSON(route, {
        job_id: formalAssets.processingJobId,
        version_id: formalAssets.versionId,
        status: 'completed',
      });
    },
    [`POST /education/textbook-versions/${formalAssets.versionId}/teaching-packages`]: async (route) => {
      teachingState = 'running';
      await fulfillJSON(route, {
        job_id: formalAssets.teachingJobId,
        teaching_package_id: formalAssets.teachingPackageId,
        content_version_id: formalAssets.versionId,
        status: 'running',
        phase: 'generating_teaching',
        attempt_count: 1,
        completed_chapter_count: 0,
        total_chapter_count: 1,
        actions: ['cancel'],
        events: [],
        attempts: [],
      }, 202);
    },
    [`GET /education/teaching-jobs/${formalAssets.teachingJobId}`]: (route) => fulfillJSON(route, {
      job_id: formalAssets.teachingJobId,
      teaching_package_id: formalAssets.teachingPackageId,
      content_version_id: formalAssets.versionId,
      status: teachingState === 'running' ? 'running' : 'completed',
      phase: teachingState === 'running' ? 'generating_teaching' : 'review',
      attempt_count: 1,
      completed_chapter_count: teachingState === 'running' ? 0 : 1,
      total_chapter_count: 1,
      actions: teachingState === 'running' ? ['cancel'] : [],
      events: teachingState === 'running' ? [] : [{
        sequence: 1,
        phase: 'validating_bundle',
        summary: '正式教学资产已通过校验',
      }],
      attempts: [{
        attempt_id: 'attempt-A1b2C3d4E5f6',
        root_run_id: 'root-run-A1b2C3d4E5f6',
        status: teachingState === 'running' ? 'running' : 'completed',
      }],
    }),
    [`GET /education/teaching-packages/${formalAssets.teachingPackageId}/assets`]: (route) => {
      assetRequests.push(new URL(route.request().url()).pathname);
      return fulfillJSON(route, {
        teaching_package_id: formalAssets.teachingPackageId,
        format: 'langalpha-family-teaching-assets/v2',
        concept_index: { size_bytes: 120, concept_count: 3 },
        coverage_audit: { size_bytes: 80, status: 'complete' },
        chapters: [{
          chapter_id: formalAssets.chapterId,
          position: chapter.position,
          title: chapter.title,
          coverage_status: 'complete',
          concept_count: 3,
          assets: [
            { kind: 'knowledge', size_bytes: 20 },
            { kind: 'toolkit', size_bytes: 30 },
            { kind: 'practice', size_bytes: 40 },
          ],
        }],
      });
    },
    [`GET /education/teaching-packages/${formalAssets.teachingPackageId}/chapters/${formalAssets.chapterId}/assets/toolkit`]: (route) => {
      assetRequests.push(new URL(route.request().url()).pathname);
      return fulfillJSON(route, {
        teaching_package_id: formalAssets.teachingPackageId,
        chapter_id: formalAssets.chapterId,
        kind: 'toolkit',
        content: '# 代数工具包\n\n正式资产不依赖 sandbox。',
      });
    },
    [`POST /education/textbooks/${formalAssets.textbookId}/versions/${formalAssets.versionId}/publish`]: async (route) => {
      const body = route.request().postDataJSON();
      publishRequest = {
        textbook_id: formalAssets.textbookId,
        version_id: formalAssets.versionId,
        teaching_package_id: body.teaching_package_id,
      };
      processingState = 'published';
      await fulfillJSON(route, {
        publication_id: formalAssets.publicationId,
        version_id: formalAssets.versionId,
        teaching_package_id: formalAssets.teachingPackageId,
      }, 201);
    },
    [`POST /education/textbook-publications/${formalAssets.publicationId}/assignments`]: async (route) => {
      const body = route.request().postDataJSON();
      assignmentRequest = {
        publication_id: formalAssets.publicationId,
        student_user_id: body.student_user_id,
      };
      assigned = true;
      await fulfillJSON(route, {
        assignment_id: formalAssets.assignmentId,
        publication_id: formalAssets.publicationId,
        student_user_id: route.request().postDataJSON().student_user_id,
      }, 201);
    },
  });

  return {
    assetRequests: () => assetRequests,
    assignmentRequest: () => assignmentRequest,
    startPayload: () => startPayload,
    finishTeaching: () => { teachingState = 'review'; },
    publishRequest: () => publishRequest,
    teachingUsagePackageIds: () => teachingUsagePackageIds,
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

test('library textbook formal assets mock flow renders without runtime', async ({ page }) => {
  const state = await mockLibraryTextbookFormalAssets(page);
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
  // If either formal-asset view starts depending on runtime state, it will get
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

  await page.goto('/education');
  await page.getByRole('link', { name: '家庭教材库' }).click();
  await page.getByRole('button', { name: '新建教材' }).click();
  await page.getByLabel('教材名称').fill(formalAssets.title);
  await page.getByRole('button', { name: '创建教材' }).click();
  await page.getByRole('button', { name: '开始加工' }).click();
  await page.getByRole('checkbox', { name: document.original_filename }).check();
  await page.getByRole('button', { name: '创建加工任务' }).click();
  await expect.poll(state.startPayload).toEqual({
    source_parse_job_ids: [completedParseJobCandidate.producer_job_id],
  });

  await expect(page.getByRole('button', { name: '执行本地加工' })).toBeVisible();
  await page.getByRole('tab', { name: '来源' }).click();
  await expect(page.getByText(document.original_filename)).toBeVisible();
  await expect(page.getByText(/AnyDoc Local 0.2.4/)).toBeVisible();
  await expect(page.getByRole('link', { name: `查看 ${document.original_filename}` })).toHaveAttribute(
    'href',
    `/documents/${document.document_id}`,
  );

  await page.getByRole('button', { name: '执行本地加工' }).click();
  await page.getByRole('button', { name: '生成教学包' }).click();
  await expect(page.getByText('教学包正在加工')).toBeVisible();
  const teachingRunDialog = page.getByRole('dialog', { name: '教材教学包运行' });
  await expect(teachingRunDialog).toBeVisible();
  await dismissTeachingRunDialog(page, teachingRunDialog);
  state.finishTeaching();
  await page.reload();

  await page.getByRole('tab', { name: '知识资产' }).click();
  await expect(page.getByText('覆盖审计通过')).toBeVisible();
  await page.getByRole('button', { name: '查看工具包' }).click();
  await expect(page.getByText('正式资产不依赖 sandbox。')).toBeVisible();

  sandboxAvailable = false;
  await page.goto(`/documents/${document.document_id}`);
  await page.getByRole('tab', { name: '教材资产' }).click();
  await expect(page.getByRole('link', { name: formalAssets.title })).toHaveAttribute(
    'href',
    `/education/textbooks/${formalAssets.textbookId}`,
  );
  await expect(page.getByText('教学包 #1')).toBeVisible();
  await expect(page.getByRole('link', { name: '查看正式教材资产' })).toBeVisible();

  await page.getByRole('link', { name: '查看正式教材资产' }).click();
  await expect(page.getByRole('heading', { name: formalAssets.title })).toBeVisible();
  await page.getByRole('tab', { name: '知识资产' }).click();
  await page.getByRole('button', { name: '查看工具包' }).click();
  await expect(page.getByText('正式资产不依赖 sandbox。')).toBeVisible();
  await expect(page.locator('body')).not.toContainText(/storage_key|snapshot_prefix|bundle_prefix|sandbox_path|minio/i);

  await page.getByRole('button', { name: '发布版本' }).click();
  await expect(page.getByText('已发布')).toBeVisible();
  await page.getByRole('button', { name: '分配学生' }).click();
  await page.getByRole('combobox').selectOption(student.user_id);
  await page.getByRole('button', { name: '分配教材' }).click();
  await page.getByRole('tab', { name: '学生' }).click();
  await expect(page.getByRole('button', { name: `查看记录：${student.name}` })).toBeVisible();

  await page.goto(`/documents/${document.document_id}`);
  await page.getByRole('tab', { name: '教材资产' }).click();
  await expect(page.getByText('已发布')).toBeVisible();
  await expect(page.getByRole('link', { name: '查看正式教材资产' })).toBeVisible();

  expect(state.teachingUsageRequests().length).toBeGreaterThan(0);
  for (const path of state.teachingUsageRequests()) {
    expect(path).toBe(`/api/v1/documents/${document.document_id}/teaching-usage`);
  }
  for (const packageId of state.teachingUsagePackageIds()) {
    expect(packageId).toBe(formalAssets.teachingPackageId);
  }
  expect(new Set(state.assetRequests())).toEqual(new Set([
    `/api/v1/education/teaching-packages/${formalAssets.teachingPackageId}/assets`,
    `/api/v1/education/teaching-packages/${formalAssets.teachingPackageId}/chapters/${formalAssets.chapterId}/assets/toolkit`,
  ]));
  expect(state.publishRequest()).toEqual({
    textbook_id: formalAssets.textbookId,
    version_id: formalAssets.versionId,
    teaching_package_id: formalAssets.teachingPackageId,
  });
  expect(state.assignmentRequest()).toEqual({
    publication_id: formalAssets.publicationId,
    student_user_id: student.user_id,
  });
  expect(sandboxRequests).toEqual([]);

  await page.waitForLoadState('networkidle');
  await Promise.all(pendingResponseChecks);
  const requiredInspectedPaths = [
    `/api/v1/documents/${document.document_id}`,
    `/api/v1/documents/${document.document_id}/teaching-usage`,
    `/api/v1/education/teaching-packages/${formalAssets.teachingPackageId}/assets`,
    `/api/v1/education/teaching-packages/${formalAssets.teachingPackageId}/chapters/${formalAssets.chapterId}/assets/toolkit`,
  ];
  for (const path of requiredInspectedPaths) {
    expect(inspectedResponsePaths).toContain(path);
  }
  expect(inspectedBodyCounts.requests).toBeGreaterThanOrEqual(20);
  expect(inspectedBodyCounts.responses).toBeGreaterThanOrEqual(20);
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
