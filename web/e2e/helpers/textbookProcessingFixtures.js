import { configureSSE, mockAPI } from '../fixtures.js';

export const BOOK_ID = 'book-1';
export const JOB_ID = 'job-1';
export const LONG_TITLE = '教材异步准备与知识点讲义的完整处理记录 '.repeat(8);

export function processingJob({ kind = 'structure', title = LONG_TITLE } = {}) {
  const now = Date.now();
  const accepted = new Date(now - 12_000).toISOString();
  const started = new Date(now - 10_000).toISOString();
  const phase = kind === 'structure' ? 'source_freezing' : 'ptc_execution';
  return {
    job_id: JOB_ID, textbook_id: BOOK_ID, kind, status: 'running',
    total_items: 1, succeeded_items: 0, failed_items: 0, cancelled_items: 0, not_run_items: 0,
    high_water_seq: 0, activity_status: 'available', created_at: accepted, started_at: started,
    finished_at: null, safe_error: null, depth: null, requirements: null,
    replace_existing: false, include_supplementary: false,
    request_round: 1, round_accepted_at: accepted, server_now: new Date(now).toISOString(),
    items: [{
      item_id: 'item-1', kind: kind === 'structure' ? 'structure' : 'material', position: 1,
      knowledge_point_id: kind === 'structure' ? null : 'kp-1', skill_kp_id: kind === 'structure' ? null : 'reading',
      knowledge_point_title: title, status: 'running', attempt: 1, started_at: started,
      finished_at: null, safe_error: null, execution_phase: phase,
      preparation_progress: kind === 'structure' ? { verified_resources: 2, total_resources: 3 } : null,
      timing_summary: {
        attempt: 1, request_round: 1, status: 'available', queued_at: accepted,
        claimed_at: started, terminal_at: null, total_ms: null,
        phases: [{ phase, status: 'available', started_at: started, ended_at: null, measured_ms: null, segment_count: 1 }],
      },
    }],
  };
}

export function activityPage(events = [], { status = 'running', highWater = 0, availability = 'available' } = {}) {
  return {
    job_id: JOB_ID, status, high_water_seq: highWater, activity_status: availability,
    cursor_expired: false, has_more: false, events,
  };
}

export function event(seq, overrides = {}) {
  return {
    seq, job_id: JOB_ID, item_id: 'item-1', kind: 'resource', status: 'running',
    message: '已校验教材来源资源', created_at: new Date().toISOString(),
    metadata: { origin: 'service', verified_resources: 2, total_resources: 3 }, ...overrides,
  };
}

export async function installProcessingMocks(page, {
  getJob, ready = false, title = LONG_TITLE, getEvents = () => [], getStatus, materialAvailable = true, withCurrentJob = true,
} = {}) {
  const selected = {
    document_id: 'document-1', parse_job_id: 'parse-1', primary_artifact_id: 'artifact-1',
    filename: 'textbook.pdf', media_type: 'application/pdf', parser_id: 'markdown', parser_name: 'Markdown',
    completed_at: '2026-10-01T00:00:00Z', content_sha256: 'a'.repeat(64), size_bytes: 1000, image_count: 2, page_count: 24,
  };
  const snapshot = () => getJob();
  await mockAPI(page, {
    'GET /auth/me': { user_id: 'parent-1', email: 'parent@example.test', name: 'Parent', role: 'parent', household_id: 'household-1' },
    'GET /education/textbooks/book-1': (route) => {
      const job = snapshot();
      const terminal = !['queued', 'running'].includes(job.status);
      return json(route, {
        textbook_id: BOOK_ID, title, structure_status: ready ? 'ready' : 'running',
        source_status: getStatus?.() ?? (ready ? 'ready' : 'preparing'),
        source: ready ? { ...selected, frozen_at: '2026-10-01T00:00:00Z' } : null,
        selected_source: selected, materials: { total: ready ? 1 : 0, ready: ready ? 1 : 0 },
        current_job: withCurrentJob && !terminal ? job : null, recent_job: withCurrentJob && terminal ? job : null,
        current_structure_id: ready ? 'structure-1' : null, assigned_student_count: 0, updated_at: job.server_now,
      });
    },
    'GET /education/textbooks/book-1/structure': {
      textbook_id: BOOK_ID, structure_id: 'structure-1', schema_version: '2.1.0', warnings: [],
      structure: { schema_version: '2.1.0', book: { title }, source: { path: 'source.md', total_lines: 500 }, coverage: {},
        nodes: [{ id: 'unit-1', title: 'Reading', anchor: { start_line: 1, end_line: 500 }, children: [] }] },
      knowledge_points: [{ knowledge_point_id: 'kp-1', skill_kp_id: 'reading', position: 1, title: '原文阅读',
        unit_skill_node_id: 'unit-1', node_skill_ids: [], start_line: 1, end_line: 500,
        content_file: 'materials/kp-1.md', material_available: materialAvailable }],
    },
    'GET /education/textbooks/book-1/source': { textbook_id: BOOK_ID, start_line: 1, end_line: 500, total_lines: 500,
      markdown: Array.from({ length: 120 }, (_, index) => `Paragraph ${index + 1}: An existing source paragraph for scroll restoration.\n`).join('\n') },
    'GET /education/textbooks/book-1/knowledge-points/kp-1/material': {
      textbook_id: BOOK_ID, knowledge_point_id: 'kp-1', skill_kp_id: 'reading', material_available: true,
      markdown: '# 已提交的讲义\n\n这份讲义已经可以阅读。', generated_at: '2026-10-01T00:00:00Z',
      depth: 'lesson', requirements: null, content_sha256: 'b'.repeat(64),
    },
    'GET /education/book-jobs/job-1': (route) => json(route, snapshot()),
    'GET /education/book-jobs/job-1/events': (route) => {
      if (route.request().headers().accept?.includes('text/event-stream')) return route.continue();
      const job = snapshot();
      return json(route, activityPage(getEvents(), { status: job.status, highWater: job.high_water_seq, availability: job.activity_status }));
    },
    'GET /education/book-jobs/job-1/statistics': {
      job_id: JOB_ID, request_round: 1, server_now: new Date().toISOString(), status: 'partial', round_total_ms: 12_000,
      material_sample_count: 0, material_median_ms: null, material_longest_ms: null,
      supplementary: [], attempts: [], next_cursor: null,
    },
  });
  await configureSSE({ path: '/api/v1/education/book-jobs/job-1/events', keepOpen: true,
    events: [{ id: 0, event: 'snapshot', data: activityPage() }] });
}

export function json(route, body) {
  return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
}
