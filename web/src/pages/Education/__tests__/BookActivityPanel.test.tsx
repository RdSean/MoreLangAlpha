import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { watchBookActivity } from '../api';
import {
  BookActivityPanel,
  RoutedBookActivityPanel,
} from '../components/BookActivityPanel';
import { projectBookActivity } from '../components/bookActivityProjection';
import type { BookActivityEvent, BookJob } from '../types';

const NOW = '2026-10-02T06:00:00Z';

function item(
  itemId: string,
  kind: BookJob['items'][number]['kind'],
  status: BookJob['items'][number]['status'],
  position: number,
): BookJob['items'][number] {
  return {
    item_id: itemId,
    kind,
    position,
    knowledge_point_id: kind === 'structure' ? null : `kp-${position}`,
    skill_kp_id: kind === 'structure' ? null : `skill-kp-${position}`,
    status,
    attempt: status === 'queued' ? 0 : 1,
    safe_error: null,
    started_at: status === 'queued' ? null : NOW,
    finished_at: ['succeeded', 'failed', 'cancelled', 'not_run'].includes(status)
      ? NOW
      : null,
  };
}

function job(overrides: Partial<BookJob> = {}): BookJob {
  const items = overrides.items ?? [
    item('material-1', 'material', 'succeeded', 1),
    item('material-2', 'material', 'running', 2),
    item('supplementary-1', 'supplementary', 'succeeded', 3),
  ];
  return {
    job_id: 'job-1',
    textbook_id: 'book-1',
    kind: 'materials',
    status: 'running',
    total_items: items.length,
    succeeded_items: items.filter((entry) => entry.status === 'succeeded').length,
    failed_items: 0,
    cancelled_items: 0,
    not_run_items: 0,
    high_water_seq: 10,
    activity_status: 'available',
    created_at: NOW,
    started_at: NOW,
    finished_at: null,
    safe_error: null,
    depth: 'lesson',
    requirements: null,
    replace_existing: false,
    include_supplementary: true,
    items,
    ...overrides,
  };
}

function event(
  seq: number,
  kind: string,
  itemId: string | null,
  message: string,
  metadata: Record<string, unknown> = {},
): BookActivityEvent {
  return {
    seq,
    job_id: 'job-1',
    item_id: itemId,
    kind,
    status: 'running',
    message,
    metadata,
    created_at: NOW,
  };
}

function page(
  events: BookActivityEvent[],
  overrides: Partial<{
    status: BookJob['status'];
    high_water_seq: number;
    activity_status: BookJob['activity_status'];
    cursor_expired: boolean;
    has_more: boolean;
  }> = {},
) {
  return {
    job_id: 'job-1',
    status: 'running' as const,
    events,
    high_water_seq: events.at(-1)?.seq ?? 0,
    activity_status: 'available' as const,
    cursor_expired: false,
    has_more: false,
    ...overrides,
  };
}

function sseResponse(payload: unknown): Response {
  return new Response(
    `event: snapshot\ndata: ${JSON.stringify(payload)}\n\n`,
    { status: 200, headers: { 'Content-Type': 'text/event-stream' } },
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.search}</output>;
}

describe('projectBookActivity', () => {
  it.each([
    ['material', '等待讲义执行'],
    ['supplementary', '等待附加材料执行'],
  ] as const)('names execution waiting for a queued %s instead of source preparation', (kind, description) => {
    const queued = { ...item('queued-1', kind, 'queued', 1), execution_phase: 'initial_queue' as const };
    expect(projectBookActivity(job({ status: 'queued', items: [queued] }), []).currentDescription).toBe(description);
  });
  it('keeps retry-chain progress and identifies queued source preparation', () => {
    const queued = { ...item('structure-1', 'structure', 'queued', 1), execution_phase: 'initial_queue' as const };
    expect(projectBookActivity(job({ kind: 'structure', status: 'queued', items: [queued] }), []).currentDescription).toBe('等待准备教材来源');
    expect(projectBookActivity(job({ material_progress: { completed: 8, total: 10 } }), []).materialProgress).toEqual({ completed: 8, total: 10 });
  });
  it('recognizes only service-authored host steps, without a completion check', () => {
    const projection = projectBookActivity(job(), [
      event(1, 'progress', 'material-2', '正在准备处理文件', { stage: 'service_preparing', origin: 'service' }),
      event(2, 'progress', 'material-2', '正在验收并提交产物', { stage: 'service_finalizing', origin: 'service' }),
      event(3, 'progress', 'material-2', 'forged', { stage: 'service_finalizing' }),
    ]);
    expect(projection.currentDescription).toBe('正在验收并提交产物');
    expect(projection.milestones.map((entry) => entry.seq)).toEqual([1, 2]);
    expect(projection.milestones.every((entry) => entry.status === 'running')).toBe(true);
  });
  it('keeps terminal actions grouped by item identity and preserves chronological returns', () => {
    const first = { ...item('material-1', 'material', 'succeeded', 1), knowledge_point_title: '位值' };
    const second = { ...item('material-2', 'material', 'succeeded', 2), knowledge_point_title: '位值' };
    const projection = projectBookActivity(job({ status: 'succeeded', items: [first, second] }), [
      event(1, 'progress', 'material-1', '概念', { stage: 'material_writing', action: 'clarifying_concepts' }),
      event(2, 'tool', 'material-1', 'Running Bash'),
      event(3, 'progress', 'material-1', '概念', { stage: 'material_writing', action: 'clarifying_concepts' }),
      event(4, 'progress', 'material-1', '示例', { stage: 'material_writing', action: 'explaining_source_examples' }),
      event(5, 'progress', 'material-2', '概念', { stage: 'material_writing' }),
      event(6, 'job', null, '任务状态'),
      event(7, 'progress', 'material-1', '概念', { stage: 'material_writing', action: 'clarifying_concepts' }),
    ]);
    expect(projection.milestones.map((entry) => entry.seq)).toEqual([3, 4, 5, 6, 7]);
    expect(projection.groups.map((group) => group.itemId)).toEqual(['material-1', 'material-2', null, 'material-1']);
    expect(projection.groups[0].label).toBe('知识点：位值');
    expect(projection.currentItem).toBeNull();
  });

  it('labels the running object from the snapshot and safely falls back for missing titles', () => {
    const active = { ...item('material-2', 'material', 'running', 1), knowledge_point_title: '<位值>' };
    const projection = projectBookActivity(job({ items: [active] }), [
      event(1, 'progress', 'missing-item', 'unmatched', { stage: 'material_writing' }),
      event(2, 'item', 'missing-item', 'item state'),
    ]);
    expect(projection.currentObjectLabel).toBe('知识点：<位值>');
    expect(projection.groups[0].label).toBe('教材处理项');
    expect(projection.groups[0].events.map((entry) => entry.seq)).toEqual([1, 2]);
    expect(projectBookActivity(job({ items: [item('material-1', 'material', 'running', 1)] }), []).currentObjectLabel)
      .toBe('讲义任务（本次第 1 项）');
  });

  it('counts only succeeded material items in lesson progress', () => {
    const projection = projectBookActivity(job(), []);

    expect(projection.materialProgress).toEqual({ completed: 1, total: 2 });
  });

  it('selects the running database item instead of the latest event item', () => {
    const projection = projectBookActivity(job(), [
      event(9, 'progress', 'material-1', '旧项目仍有迟到事件', { stage: 'material_writing' }),
      event(10, 'tool', 'supplementary-1', 'Finished Read'),
    ]);

    expect(projection.currentItem?.item_id).toBe('material-2');
  });

  it('uses the latest valid semantic stage for the current item', () => {
    const projection = projectBookActivity(job(), [
      event(1, 'progress', 'material-2', '正在阅读知识点原文', { stage: 'material_reading' }),
      event(2, 'progress', 'material-2', '不会展示的未知阶段', { stage: 'unknown_stage' }),
      event(3, 'progress', 'material-1', '旧项目阶段', { stage: 'material_validating' }),
      event(4, 'progress', 'material-2', '正在组织讲义内容', { stage: 'material_organizing' }),
    ]);

    expect(projection.currentStage?.message).toBe('正在组织讲义内容');
    expect(projection.currentStage?.seq).toBe(4);
  });

  it('keeps tool events in details and out of the main timeline', () => {
    const events = [
      event(1, 'tool', 'material-2', 'Running Read'),
      event(2, 'material', 'material-1', 'Material committed'),
      event(3, 'tool', 'material-2', 'Finished Read'),
    ];

    const projection = projectBookActivity(job(), events);

    expect(projection.toolDetails.map((entry) => entry.seq)).toEqual([1, 3]);
    expect(projection.milestones.map((entry) => entry.seq)).toEqual([2]);
  });

  it('exposes unavailable activity without changing the job status', () => {
    const projection = projectBookActivity(
      job({ activity_status: 'unavailable', status: 'running' }),
      [],
    );

    expect(projection.activityUnavailable).toBe(true);
    expect(projection.jobStatus).toBe('running');
    expect(projection.currentDescription).toBe('活动暂不可用，讲义生成仍在继续');
  });

  it('does not retain a previous item stage after the job becomes terminal', () => {
    const projection = projectBookActivity(
      job({
        status: 'partially_succeeded',
        items: [
          item('material-1', 'material', 'succeeded', 1),
          item('material-2', 'material', 'failed', 2),
        ],
        finished_at: NOW,
      }),
      [event(7, 'progress', 'material-2', '正在撰写讲义', { stage: 'material_writing' })],
    );

    expect(projection.currentItem).toBeNull();
    expect(projection.currentStage).toBeNull();
  });

  it('does not expose lesson percentages for a structure job', () => {
    const projection = projectBookActivity(
      job({
        kind: 'structure',
        items: [item('structure-1', 'structure', 'running', 1)],
        total_items: 1,
        succeeded_items: 0,
        include_supplementary: false,
      }),
      [],
    );

    expect(projection.materialProgress).toBeNull();
    expect(projection.currentDescription).toBe('正在分析教材结构');
  });
});

describe('watchBookActivity', () => {
  it.each([401, 403, 404])('clears access on HTTP %s and does not reconnect', async (status) => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('', { status }));
    vi.stubGlobal('fetch', fetchMock);
    const onAccessLost = vi.fn();
    const onError = vi.fn();
    await watchBookActivity('job-1', { onPage: vi.fn(), onAccessLost, onError });
    expect(onAccessLost).toHaveBeenCalledOnce();
    expect(onError).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it('finishes every retained page before stopping a completed job replay', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(sseResponse(page([event(1, 'tool', 'material-1', 'Read')], {
        status: 'succeeded', high_water_seq: 2, has_more: true,
      })))
      .mockResolvedValueOnce(sseResponse(page([event(2, 'job', null, 'Job completed')], {
        status: 'succeeded', high_water_seq: 2,
      })));
    vi.stubGlobal('fetch', fetchMock);
    const received: number[] = [];

    await watchBookActivity('job-1', {
      reconnectDelayMs: 0,
      onPage: (snapshot) => { received.push(...snapshot.events.map((entry) => entry.seq)); },
    });

    expect(received).toEqual([1, 2]);
    expect(fetchMock.mock.calls[1][0]).toContain('after_seq=1');
  });

  it('reconnects from the greatest event sequence successfully merged', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(sseResponse(page([
        event(1, 'job', null, 'Job started'),
        event(200, 'material', 'material-1', 'Material committed'),
      ], { high_water_seq: 500 })))
      .mockResolvedValueOnce(sseResponse(page([
        event(201, 'material', 'material-2', 'Material committed'),
        event(500, 'job', null, 'Job completed'),
      ], { status: 'succeeded', high_water_seq: 500 })));
    vi.stubGlobal('fetch', fetchMock);
    const received: number[] = [];

    await watchBookActivity('job-1', {
      reconnectDelayMs: 0,
      onPage: (snapshot) => { received.push(...snapshot.events.map((entry) => entry.seq)); },
    });

    expect(received).toEqual([1, 200, 201, 500]);
    expect(fetchMock.mock.calls[0][0]).toContain('after_seq=0');
    expect(fetchMock.mock.calls[1][0]).toContain('after_seq=200');
  });

  it('does not advance from an empty page even when high water is newer', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(sseResponse(page([], { high_water_seq: 500 })))
      .mockResolvedValueOnce(sseResponse(page([
        event(1, 'job', null, 'Job completed'),
      ], { status: 'succeeded', high_water_seq: 500 })));
    vi.stubGlobal('fetch', fetchMock);

    await watchBookActivity('job-1', { reconnectDelayMs: 0, onPage: vi.fn() });

    expect(fetchMock.mock.calls[1][0]).toContain('after_seq=0');
  });

  it('does not advance after an invalid page and reconnects from the prior cursor', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(sseResponse({ ...page([]), events: [{ seq: 'invalid' }] }))
      .mockResolvedValueOnce(sseResponse(page([
        event(1, 'job', null, 'Job completed'),
      ], { status: 'succeeded' })));
    vi.stubGlobal('fetch', fetchMock);

    await watchBookActivity('job-1', { reconnectDelayMs: 0, onPage: vi.fn() });

    expect(fetchMock.mock.calls[1][0]).toContain('after_seq=0');
  });

  it('deduplicates replayed event sequences before merging a page', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(sseResponse(page([
        event(1, 'job', null, 'Job started'),
        event(2, 'tool', 'material-1', 'Running Read'),
      ])))
      .mockResolvedValueOnce(sseResponse(page([
        event(2, 'tool', 'material-1', 'Running Read'),
        event(3, 'job', null, 'Job completed'),
      ], { status: 'succeeded' })));
    vi.stubGlobal('fetch', fetchMock);
    const merged: number[][] = [];

    await watchBookActivity('job-1', {
      reconnectDelayMs: 0,
      onPage: (snapshot) => { merged.push(snapshot.events.map((entry) => entry.seq)); },
    });

    expect(merged).toEqual([[1, 2], [3]]);
  });

  it('clears cached activity and restarts from zero when the cursor expires', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(sseResponse(page([], {
        cursor_expired: true,
        high_water_seq: 8,
      })))
      .mockResolvedValueOnce(sseResponse(page([
        event(1, 'job', null, 'Job completed'),
      ], { status: 'succeeded' })));
    vi.stubGlobal('fetch', fetchMock);
    const onCursorExpired = vi.fn();

    await watchBookActivity('job-1', {
      afterSeq: 12,
      reconnectDelayMs: 0,
      onCursorExpired,
      onPage: vi.fn(),
    });

    expect(onCursorExpired).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0][0]).toContain('after_seq=12');
    expect(fetchMock.mock.calls[1][0]).toContain('after_seq=0');
  });

  it('reports reconnecting without turning a network disconnect into job failure', async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError('connection reset'))
      .mockResolvedValueOnce(sseResponse(page([
        event(1, 'job', null, 'Job completed'),
      ], { status: 'succeeded' })));
    vi.stubGlobal('fetch', fetchMock);
    const states: string[] = [];

    await watchBookActivity('job-1', {
      reconnectDelayMs: 0,
      onConnectionChange: (state) => { states.push(state); },
      onPage: vi.fn(),
    });

    expect(states).toContain('reconnecting');
    expect(states.at(-1)).toBe('connected');
  });

  it('cancels the active stream reader when aborted', async () => {
    const cancel = vi.fn();
    const stream = new ReadableStream<Uint8Array>({ cancel });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(stream, {
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
    })));
    const controller = new AbortController();

    const watching = watchBookActivity('job-1', {
      signal: controller.signal,
      onPage: vi.fn(),
    });
    await Promise.resolve();
    controller.abort();
    await watching;

    expect(cancel).toHaveBeenCalledOnce();
  });
});

describe('RoutedBookActivityPanel', () => {
  it('pages compact diagnostics by 50 records and resets the window on a different job', () => {
    const events = Array.from({ length: 120 }, (_, index) => event(index + 1, 'tool', 'material-2', `诊断 ${index}`));
    const view = render(<BookActivityPanel job={job()} events={events} />);
    fireEvent.click(screen.getByRole('button', { name: '诊断明细（120）' }));
    expect(screen.getByText('诊断 119')).toBeInTheDocument();
    expect(screen.queryByText('诊断 0')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '更早的诊断' }));
    expect(screen.getByText('诊断 20')).toBeInTheDocument();
    expect(screen.queryByText('诊断 0')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '更早的诊断' }));
    expect(screen.getByText('诊断 0')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '更早的诊断' })).not.toBeInTheDocument();
    view.rerender(<BookActivityPanel job={job({ job_id: 'job-2' })} events={events} />);
    fireEvent.click(screen.getByRole('button', { name: '诊断明细（120）' }));
    expect(screen.queryByText('诊断 0')).not.toBeInTheDocument();
  });
  it('unmounts diagnostics by default and resets them when switching jobs', () => {
    const events = [event(1, 'tool', 'material-2', 'Running Bash')];
    const view = render(<BookActivityPanel job={job()} events={events} />);
    expect(screen.queryByText('Running Bash')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '诊断明细（1）' }));
    expect(screen.getByText('Running Bash')).toBeInTheDocument();
    view.rerender(<BookActivityPanel job={job({ job_id: 'job-2' })} events={events} />);
    expect(screen.queryByText('Running Bash')).not.toBeInTheDocument();
    view.rerender(<BookActivityPanel job={job()} events={events} />);
    expect(screen.queryByText('Running Bash')).not.toBeInTheDocument();
  });

  it('renders completed action history as neutral progress and titles as plain text', () => {
    const completed = job({ status: 'succeeded', items: [
      { ...item('material-1', 'material', 'succeeded', 1), knowledge_point_title: '<img src=x onerror=alert(1)>' },
    ] });
    const view = render(<BookActivityPanel job={completed} events={[
      event(1, 'progress', 'material-1', '正在澄清概念与术语', { stage: 'material_writing', action: 'clarifying_concepts' }),
      { ...event(2, 'material', 'material-1', '讲义已提交'), status: 'succeeded' },
    ]} />);
    expect(screen.getByText('知识点：<img src=x onerror=alert(1)>')).toBeInTheDocument();
    const progressRow = screen.getByText('正在澄清概念与术语').closest('li');
    expect(progressRow?.querySelector('.lucide-check')).toBeNull();
    expect(view.container.querySelector('img')).toBeNull();
    expect(screen.getByText('讲义已提交').closest('li')?.querySelector('.lucide-check')).not.toBeNull();
  });

  it('does not mark a cancelled job as successful', () => {
    const view = render(<BookActivityPanel job={job({ status: 'cancelled' })} events={[]} />);
    expect(view.container.querySelector('.lucide-check')).toBeNull();
    expect(screen.getAllByText('已取消').length).toBeGreaterThan(0);
  });

  it('stays closed until the activity query parameter names the job', () => {
    const closed = render(
      <MemoryRouter initialEntries={['/textbooks/book-1']}>
        <RoutedBookActivityPanel job={job()} events={[]} />
      </MemoryRouter>,
    );

    expect(screen.queryByRole('complementary', { name: '教材处理活动' })).not.toBeInTheDocument();
    closed.unmount();

    render(
      <MemoryRouter initialEntries={['/textbooks/book-1?activity=job-1']}>
        <RoutedBookActivityPanel job={job()} events={[]} />
      </MemoryRouter>,
    );
    expect(screen.getByRole('complementary', { name: '教材处理活动' })).toBeInTheDocument();
  });

  it('keeps URL and reader scroll stable when tool details are toggled', () => {
    render(
      <MemoryRouter initialEntries={['/textbooks/book-1?kp=lesson-3&activity=job-1']}>
        <div data-testid="reader" style={{ height: 20, overflow: 'auto' }}>
          <div style={{ height: 200 }} />
        </div>
        <RoutedBookActivityPanel
          job={job()}
          events={[event(1, 'tool', 'material-2', 'Running Read')]}
        />
        <LocationProbe />
      </MemoryRouter>,
    );
    const reader = screen.getByTestId('reader');
    reader.scrollTop = 73;

    fireEvent.click(screen.getByRole('button', { name: '诊断明细（1）' }));

    expect(screen.getByTestId('location')).toHaveTextContent('?kp=lesson-3&activity=job-1');
    expect(reader.scrollTop).toBe(73);
  });
});
