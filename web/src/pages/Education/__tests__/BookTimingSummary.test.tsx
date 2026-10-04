import {
  act,
  fireEvent,
  render,
  renderHook,
  screen,
} from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { BookTimingSummary } from '../components/BookTimingSummary';
import { projectBookTiming } from '../components/bookTimingProjection';
import { useBookElapsedTime } from '../components/useBookElapsedTime';
import { processingJob } from './bookProcessingFixtures';

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('reliable book timing', () => {
  it('adds recorded prior segments to the live window but preserves interrupted gaps as unknown', () => {
    const job = processingJob();
    const phase = job.items[0].timing_summary!.phases[0];
    phase.segment_count = 2;
    phase.measured_ms = 1000;
    expect(
      projectBookTiming(job, Date.parse(job.server_now!)).phases[1].ms,
    ).toBe(9000);
    phase.status = 'partial';
    phase.measured_ms = null;
    expect(
      projectBookTiming(job, Date.parse(job.server_now!)).phases[1].ms,
    ).toBeNull();
  });

  it('pauses in the background and removes its interval at terminal state', () => {
    vi.useFakeTimers();
    let visibility: DocumentVisibilityState = 'visible';
    vi.spyOn(document, 'visibilityState', 'get').mockImplementation(
      () => visibility,
    );
    const job = processingJob();
    const { result, rerender } = renderHook(
      ({ job }) => useBookElapsedTime(job, true),
      { initialProps: { job } },
    );
    expect(vi.getTimerCount()).toBe(1);
    visibility = 'hidden';
    act(() => document.dispatchEvent(new Event('visibilitychange')));
    expect(vi.getTimerCount()).toBe(0);
    expect(result.current).toBe(Date.parse(job.server_now!));
    visibility = 'visible';
    act(() => document.dispatchEvent(new Event('visibilitychange')));
    rerender({ job: { ...job, status: 'succeeded' } });
    expect(vi.getTimerCount()).toBe(0);
  });
  it('uses confirmed service time and keeps missing data distinct from zero', () => {
    const job = processingJob();
    const timing = projectBookTiming(job, Date.parse(job.server_now!));
    expect(timing.roundMs).toBe(10000);
    expect(timing.attemptMs).toBe(10000);
    expect(
      timing.phases.find((phase) => phase.phase === 'source_freezing')?.ms,
    ).toBe(8000);
    expect(
      timing.phases.find((phase) => phase.phase === 'ptc_execution')?.ms,
    ).toBeNull();
    const stale = processingJob({ items: [{ ...job.items[0], attempt: 2 }] });
    expect(
      projectBookTiming(stale, Date.parse(job.server_now!)).attemptMs,
    ).toBeNull();
  });

  it('renders unavailable durations explicitly and opens service phase detail on demand', () => {
    render(
      <BookTimingSummary
        timing={projectBookTiming(
          processingJob({
            server_now: null,
            round_accepted_at: null,
            items: [],
          }),
          null,
        )}
      />,
    );
    expect(screen.getAllByText('未记录').length).toBeGreaterThan(0);
    expect(screen.queryByText('PTC 执行')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '服务区间' }));
    expect(screen.getByText('PTC 执行')).toBeInTheDocument();
  });

  it('ticks from a monotonic clock, freezes at confirmed time offline and resets on a new attempt', () => {
    vi.useFakeTimers();
    let monotonic = 1000;
    vi.spyOn(performance, 'now').mockImplementation(() => monotonic);
    const job = processingJob();
    const { result, rerender } = renderHook(
      ({ connected, job }) => useBookElapsedTime(job, connected),
      { initialProps: { connected: true, job } },
    );
    monotonic += 3000;
    act(() => vi.advanceTimersByTime(1000));
    expect(result.current).toBe(Date.parse(job.server_now!) + 3000);
    rerender({ connected: false, job });
    expect(result.current).toBe(Date.parse(job.server_now!));
    monotonic += 100000;
    rerender({
      connected: true,
      job: {
        ...job,
        server_now: '2026-10-05T00:00:20Z',
        items: [{ ...job.items[0], attempt: 2 }],
      },
    });
    expect(result.current).toBe(Date.parse('2026-10-05T00:00:20Z'));
  });
});
