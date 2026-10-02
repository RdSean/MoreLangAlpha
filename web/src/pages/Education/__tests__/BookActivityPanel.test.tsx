import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { watchBookActivity } from '../api';
import {
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

    fireEvent.click(screen.getByText('运行明细（1）'));

    expect(screen.getByTestId('location')).toHaveTextContent('?kp=lesson-3&activity=job-1');
    expect(reader.scrollTop).toBe(73);
  });
});
