import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useState } from 'react';
import i18n from '@/i18n';
import { BookLiveActivity, BookLiveActivityView } from '../components/BookLiveActivity';
import { useBookLiveActivity } from '../components/useBookLiveActivity';
import { loadQuotePool } from '../quotePool';
import type { BookActivityEvent, BookJob, BookJobItem } from '../types';

vi.mock('../quotePool', () => ({ loadQuotePool: vi.fn() }));

let now = Date.parse('2026-10-03T02:00:00Z');
const activeItem: BookJobItem = { item_id: 'item-1', kind: 'material', position: 1, knowledge_point_id: 'kp', skill_kp_id: 'kp', status: 'running', attempt: 1, started_at: new Date(now - 1_000).toISOString(), finished_at: null, safe_error: null };
const job = { job_id: 'job-1', high_water_seq: 10 } as BookJob;
const quotes = [{ contents: '第一句', source: '第一位作者' }, { contents: '第二句', source: '第二位作者' }];
function event(seq: number, overrides: Partial<BookActivityEvent> = {}): BookActivityEvent {
  return { seq, job_id: 'job-1', item_id: 'item-1', kind: 'tool', status: 'running', message: 'Running Bash', metadata: {}, created_at: new Date(now).toISOString(), ...overrides };
}
beforeEach(() => {
  void i18n.changeLanguage('zh-CN');
  now = Date.parse('2026-10-03T02:00:00Z');
  vi.spyOn(Date, 'now').mockImplementation(() => now);
  vi.mocked(loadQuotePool).mockResolvedValue(quotes);
});
afterEach(() => vi.restoreAllMocks());

describe('BookLiveActivity', () => {
  it('presents one compact poem line and an author line without changing the activity trigger', () => {
    render(<BookLiveActivityView activity={{ active: true, recentAt: now, recentKind: '工具活动', quote: { contents: '欲穷千里目，更上一层楼。', source: '王之涣《登鹳雀楼》' } }} />);
    expect(screen.getByText('--王之涣')).toBeInTheDocument();
    expect(screen.getByText('欲穷千里目，更上一层楼。')).toHaveAttribute('title', '欲穷千里目，更上一层楼。');
    expect(screen.getByLabelText('等待时的名句')).toHaveClass('h-12');
    expect(loadQuotePool).not.toHaveBeenCalled();
  });
  it('keeps its quote and event fence when the layout remounts the presentation', async () => {
    function Harness() {
      const [layout, setLayout] = useState('page');
      const [events, setEvents] = useState<BookActivityEvent[]>([]);
      const activity = useBookLiveActivity(job, activeItem, events, true, 10);
      return <><button onClick={() => setEvents([event(11)])}>event</button><button onClick={() => setLayout('compact')}>layout</button><BookLiveActivityView key={layout} activity={activity} /></>;
    }
    render(<Harness />);
    fireEvent.click(screen.getByText('event'));
    await screen.findByText('第一句');
    now += 6000;
    fireEvent.click(screen.getByText('layout'));
    expect(screen.getByText('第一句')).toBeInTheDocument();
    expect(loadQuotePool).toHaveBeenCalledTimes(1);
  });
  it('accepts fresh service resource confirmations during preparation and ignores lease heartbeats', async () => {
    const props = { job, item: { ...activeItem, kind: 'structure' as const }, connected: true, events: [] as BookActivityEvent[] };
    const { rerender } = render(<BookLiveActivity {...props} />);
    rerender(<BookLiveActivity {...props} events={[event(11, { kind: 'heartbeat' })]} />);
    expect(loadQuotePool).not.toHaveBeenCalled();
    rerender(<BookLiveActivity {...props} events={[event(12, { kind: 'resource', metadata: { origin: 'service' } })]} />);
    await screen.findByText('第一句');
    expect(screen.getByText('存储确认')).toBeInTheDocument();
  });

  it('does not rotate on terminal callbacks', () => {
    render(<BookLiveActivity job={{ ...job, status: 'succeeded' }} item={activeItem} events={[event(11)]} connected />);
    expect(loadQuotePool).not.toHaveBeenCalled();
  });
  it('does not restart an interrupted load without a fresh diagnostic', async () => {
    let resolve!: (value: typeof quotes) => void;
    vi.mocked(loadQuotePool).mockImplementation(() => new Promise((done) => { resolve = done; }));
    const props = { job, item: activeItem, connected: true, events: [] as BookActivityEvent[] };
    const { rerender } = render(<BookLiveActivity {...props} />);
    rerender(<BookLiveActivity {...props} events={[event(11)]} />);
    const signal = vi.mocked(loadQuotePool).mock.calls[0][0];
    rerender(<BookLiveActivity {...props} events={[event(11)]} connected={false} />);
    expect(signal.aborted).toBe(true);
    now += 60_000;
    rerender(<BookLiveActivity {...props} events={[event(11)]} />);
    await act(async () => resolve(quotes));
    expect(loadQuotePool).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('第一句')).not.toBeInTheDocument();
    vi.mocked(loadQuotePool).mockResolvedValue(quotes);
    rerender(<BookLiveActivity {...props} events={[event(12)]} />);
    await screen.findByText('第一句');
    expect(loadQuotePool).toHaveBeenCalledTimes(2);
  });
  it('reserves the quote region while disconnected', () => {
    render(<BookLiveActivity job={job} item={activeItem} events={[]} connected={false} />);
    expect(screen.getByLabelText('等待时的名句')).toBeInTheDocument();
  });
  it('ignores reconnect catch-up even when its tools have recent timestamps', () => {
    const { rerender } = render(<BookLiveActivity job={job} item={activeItem} events={[]} connected liveAfterSeq={null} />);
    rerender(<BookLiveActivity job={job} item={activeItem} events={[event(11)]} connected liveAfterSeq={11} />);
    expect(loadQuotePool).not.toHaveBeenCalled();
  });
  it('ignores replay and only loads once for new diagnostics, with event-driven cooldown', async () => {
    const props = { job, item: activeItem, events: [event(10)], connected: true };
    const { rerender } = render(<BookLiveActivity {...props} />);
    expect(loadQuotePool).not.toHaveBeenCalled();
    rerender(<BookLiveActivity {...props} events={[event(10), event(11)]} />);
    await screen.findByText('第一句');
    expect(screen.getByText('最近活动')).toBeInTheDocument();
    now += 4_999;
    rerender(<BookLiveActivity {...props} events={[event(12)]} />);
    expect(screen.getByText('第一句')).toBeInTheDocument();
    now += 1;
    rerender(<BookLiveActivity {...props} events={[event(12)]} />);
    expect(screen.getByText('第一句')).toBeInTheDocument();
    rerender(<BookLiveActivity {...props} events={[event(13)]} />);
    await screen.findByText('第二句');
    expect(loadQuotePool).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('Running Bash')).not.toBeInTheDocument();
    expect(screen.getByLabelText('等待时的名句')).toHaveAttribute('aria-live', 'off');
  });

  it('ignores stale, previous attempt, foreign item/job and non-tool events', () => {
    render(<BookLiveActivity job={job} item={activeItem} connected events={[
      event(11, { job_id: 'other-job' }), event(12, { item_id: 'other-item' }),
      event(13, { created_at: new Date(now - 50_000).toISOString() }),
      event(14, { kind: 'progress' }),
      event(15, { created_at: new Date(now - 2_000).toISOString() }),
    ]} />);
    expect(loadQuotePool).not.toHaveBeenCalled();
  });

  it('does not update while disconnected or hidden and consumes those events', async () => {
    const { rerender } = render(<BookLiveActivity job={job} item={activeItem} events={[]} connected />);
    rerender(<BookLiveActivity job={job} item={activeItem} events={[event(11)]} connected={false} />);
    rerender(<BookLiveActivity job={job} item={activeItem} events={[event(11)]} connected />);
    expect(loadQuotePool).not.toHaveBeenCalled();
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
    act(() => document.dispatchEvent(new Event('visibilitychange')));
    rerender(<BookLiveActivity job={job} item={activeItem} events={[event(12)]} connected />);
    expect(loadQuotePool).not.toHaveBeenCalled();
  });

  it('keeps activity visible when static assets fail and does not retry per event', async () => {
    vi.mocked(loadQuotePool).mockRejectedValue(new Error('offline'));
    const { rerender } = render(<BookLiveActivity job={job} item={activeItem} events={[]} connected />);
    rerender(<BookLiveActivity job={job} item={activeItem} events={[event(11)]} connected />);
    await waitFor(() => expect(loadQuotePool).toHaveBeenCalledTimes(1));
    rerender(<BookLiveActivity job={job} item={activeItem} events={[event(12)]} connected />);
    expect(screen.getByText('最近活动')).toBeInTheDocument();
    expect(loadQuotePool).toHaveBeenCalledTimes(1);
  });

  it('aborts loading on unmount and discards late results', async () => {
    let resolve!: (value: typeof quotes) => void;
    vi.mocked(loadQuotePool).mockImplementation(() => new Promise((done) => { resolve = done; }));
    const { rerender, unmount } = render(<BookLiveActivity job={job} item={activeItem} events={[]} connected />);
    rerender(<BookLiveActivity job={job} item={activeItem} events={[event(11)]} connected />);
    const signal = vi.mocked(loadQuotePool).mock.calls[0][0];
    unmount();
    expect(signal.aborted).toBe(true);
    await act(async () => resolve(quotes));
    expect(screen.queryByText('第一句')).not.toBeInTheDocument();
  });
});
