import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';
import { queryKeys } from '@/lib/queryKeys';
import { afterEach, describe, expect, it, vi } from 'vitest';
import * as educationApi from '../api';
import {
  createCoalescedRefreshScheduler,
  useBookActivity,
} from '../queries';
import type { BookActivityPage, BookJob } from '../types';

const NOW = '2026-10-02T06:00:00Z';

function runningJob(): BookJob {
  return {
    job_id: 'job-1',
    textbook_id: 'book-1',
    kind: 'materials',
    status: 'running',
    total_items: 1,
    succeeded_items: 0,
    failed_items: 0,
    cancelled_items: 0,
    not_run_items: 0,
    high_water_seq: 0,
    activity_status: 'available',
    created_at: NOW,
    started_at: NOW,
    finished_at: null,
    safe_error: null,
    depth: 'lesson',
    requirements: null,
    replace_existing: false,
    include_supplementary: false,
    items: [{
      item_id: 'item-1',
      kind: 'material',
      position: 1,
      knowledge_point_id: 'kp-1',
      skill_kp_id: 'skill-kp-1',
      status: 'running',
      attempt: 1,
      safe_error: null,
      started_at: NOW,
      finished_at: null,
    }],
  };
}

function activityPage(): BookActivityPage {
  return {
    job_id: 'job-1',
    status: 'running',
    high_water_seq: 1,
    activity_status: 'available',
    cursor_expired: false,
    has_more: false,
    events: [{
      seq: 1,
      job_id: 'job-1',
      item_id: 'item-1',
      kind: 'progress',
      status: 'running',
      message: '正在撰写讲义',
      metadata: { stage: 'material_writing' },
      created_at: NOW,
    }],
  };
}

function wrapper(client: QueryClient) {
  return function Wrapper({ children }: PropsWithChildren) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('createCoalescedRefreshScheduler', () => {
  it('runs once immediately and preserves one trailing refresh per second', async () => {
    vi.useFakeTimers();
    const refresh = vi.fn().mockResolvedValue(undefined);
    const scheduler = createCoalescedRefreshScheduler(refresh, { minimumIntervalMs: 1_000 });

    scheduler.notify();
    scheduler.notify();
    scheduler.notify();
    await vi.advanceTimersByTimeAsync(0);
    expect(refresh).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(999);
    expect(refresh).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(refresh).toHaveBeenCalledTimes(2);

    scheduler.dispose();
  });
});

describe('useBookActivity', () => {
  it('loads retained activity when first opening an already completed job', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const completed = { ...runningJob(), status: 'succeeded' as const, succeeded_items: 1 };
    client.setQueryData(queryKeys.education.bookJob('job-1'), completed);
    vi.spyOn(educationApi, 'getBookJob').mockResolvedValue(completed);
    const watch = vi.spyOn(educationApi, 'watchBookActivity').mockImplementation(async (_jobId, options) => {
      await options.onPage({ ...activityPage(), status: 'succeeded' });
    });
    const view = renderHook(() => useBookActivity('job-1', 'book-1'), { wrapper: wrapper(client) });

    await waitFor(() => expect(view.result.current.events).toHaveLength(1));
    expect(watch).toHaveBeenCalledTimes(1);
    view.unmount();
  });

  it('refreshes immediately on foreground restore even if the activity stream never connects', async () => {
    let visibility: DocumentVisibilityState = 'visible';
    vi.spyOn(document, 'visibilityState', 'get').mockImplementation(() => visibility);
    const getJob = vi.spyOn(educationApi, 'getBookJob').mockResolvedValue(runningJob());
    const watch = vi.spyOn(educationApi, 'watchBookActivity').mockImplementation((_jobId, options) => (
      new Promise((resolve) => options.signal?.addEventListener('abort', () => resolve()))
    ));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } } });
    const view = renderHook(
      () => useBookActivity('job-1', 'book-1', true),
      { wrapper: wrapper(client) },
    );
    await waitFor(() => expect(view.result.current.data).toBeDefined());

    await act(async () => {
      visibility = 'hidden';
      document.dispatchEvent(new Event('visibilitychange'));
    });
    const callsBeforeRestore = getJob.mock.calls.length;
    getJob.mockResolvedValue({ ...runningJob(), succeeded_items: 1 });
    await act(async () => {
      visibility = 'visible';
      document.dispatchEvent(new Event('visibilitychange'));
    });

    await waitFor(() => {
      expect(getJob.mock.calls.length).toBeGreaterThan(callsBeforeRestore);
      expect(view.result.current.data?.succeeded_items).toBe(1);
    }, { timeout: 500 });
    expect(watch).toHaveBeenCalledTimes(2);
    view.unmount();
  });

  it('aborts the stream when the subscription unmounts', async () => {
    vi.spyOn(educationApi, 'getBookJob').mockResolvedValue(runningJob());
    let subscribedSignal: AbortSignal | undefined;
    vi.spyOn(educationApi, 'watchBookActivity').mockImplementation((_jobId, options) => {
      subscribedSignal = options.signal;
      return new Promise((resolve) => options.signal?.addEventListener('abort', () => resolve()));
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    const view = renderHook(
      () => useBookActivity('job-1', 'book-1', true),
      { wrapper: wrapper(client) },
    );
    await waitFor(() => expect(subscribedSignal).toBeDefined());

    view.unmount();

    expect(subscribedSignal?.aborted).toBe(true);
  });

  it('clears cached events and refreshes the job after cursor expiry', async () => {
    const getJob = vi.spyOn(educationApi, 'getBookJob').mockResolvedValue(runningJob());
    let streamOptions: educationApi.WatchBookActivityOptions | undefined;
    vi.spyOn(educationApi, 'watchBookActivity').mockImplementation((_jobId, options) => {
      streamOptions = options;
      return new Promise((resolve) => options.signal?.addEventListener('abort', () => resolve()));
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = renderHook(
      () => useBookActivity('job-1', 'book-1', true),
      { wrapper: wrapper(client) },
    );
    await waitFor(() => expect(streamOptions).toBeDefined());

    await act(async () => { await streamOptions?.onPage(activityPage()); });
    expect(view.result.current.events).toHaveLength(1);
    const callsBeforeExpiry = getJob.mock.calls.length;

    await act(async () => { await streamOptions?.onCursorExpired?.(); });

    expect(view.result.current.events).toEqual([]);
    expect(getJob.mock.calls.length).toBeGreaterThan(callsBeforeExpiry);
    view.unmount();
  });
});
