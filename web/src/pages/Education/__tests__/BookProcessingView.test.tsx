import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { BookProcessingView } from '../components/BookProcessingView';
import { projectBookTiming } from '../components/bookTimingProjection';
import { processingJob } from './bookProcessingFixtures';

describe('BookProcessingView', () => {
  it('exposes earlier non-completed activity without mounting it by default', () => {
    const base = processingJob();
    const items = Array.from({ length: 60 }, (_, index) => ({
      ...base.items[0],
      item_id: `item-${index}`,
      status: 'failed' as const,
    }));
    const job = processingJob({ items, status: 'failed' });
    const events = items.map((item, index) => ({
      seq: index + 1,
      item_id: item.item_id,
      job_id: job.job_id,
      kind: 'item',
      status: 'failed',
      message: `失败项${index}`,
      metadata: {},
      created_at: job.created_at,
    }));
    render(
      <BookProcessingView
        job={job}
        events={events}
        connected={false}
        timing={projectBookTiming(job, null)}
        onReturnToReading={vi.fn()}
      />,
    );
    expect(screen.queryByText('失败项0')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '更早的活动记录' }));
    expect(screen.getByText('失败项0')).toBeInTheDocument();
  });

  it('keeps supplementary timing separate from material samples', () => {
    const job = processingJob();
    const stats = {
      job_id: job.job_id,
      request_round: 1,
      server_now: job.server_now!,
      status: 'available' as const,
      round_total_ms: 10000,
      material_sample_count: 0,
      material_median_ms: null,
      material_longest_ms: null,
      next_cursor: null,
      supplementary: [
        {
          item_id: 'extra',
          kind: 'supplementary' as const,
          status: 'succeeded' as const,
          knowledge_point_title: null,
          timing: { ...job.items[0].timing_summary!, total_ms: 2000 },
        },
      ],
      attempts: [],
    };
    render(
      <BookProcessingView
        job={job}
        events={[]}
        connected={false}
        timing={projectBookTiming(job, null)}
        onReturnToReading={vi.fn()}
        historyOpen
        onHistoryOpenChange={vi.fn()}
        statistics={[stats]}
      />,
    );
    expect(
      screen.getByRole('region', { name: '附加材料统计' }),
    ).toHaveTextContent('2 秒');
  });
  it('does not wait for a source manifest after entering the runtime queue', () => {
    const job = processingJob();
    job.items[0].execution_phase = 'runtime_queue';
    job.items[0].preparation_progress = {
      verified_resources: 3,
      total_resources: 3,
    };
    render(
      <BookProcessingView
        job={job}
        events={[]}
        connected={false}
        timing={projectBookTiming(job, null)}
        onReturnToReading={vi.fn()}
      />,
    );
    expect(screen.queryByText('等待来源清单确认')).not.toBeInTheDocument();
  });
  it('bounds completed groups and never follows scroll until explicitly enabled', () => {
    const base = processingJob();
    const items = Array.from({ length: 30 }, (_, index) => ({
      ...base.items[0],
      item_id: `item-${index}`,
      kind: 'material' as const,
      status: 'succeeded' as const,
      skill_kp_id: `kp-${index}`,
      knowledge_point_title: `知识点 ${index}`,
    }));
    const job = processingJob({
      kind: 'materials',
      items,
      status: 'succeeded',
    });
    const events = items.map((item, index) => ({
      seq: index + 1,
      item_id: item.item_id,
      job_id: job.job_id,
      kind: 'material',
      status: 'succeeded',
      message: `讲义${index}提交`,
      metadata: {},
      created_at: job.created_at,
    }));
    const scrollIntoView = vi.fn();
    HTMLElement.prototype.scrollIntoView = scrollIntoView;
    const view = render(
      <BookProcessingView
        job={job}
        events={events}
        connected={false}
        timing={projectBookTiming(job, null)}
        onReturnToReading={vi.fn()}
      />,
    );
    expect(screen.queryByText('讲义0提交')).not.toBeInTheDocument();
    expect(scrollIntoView).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '已完成记录（30）' }));
    expect(screen.getByText('讲义0提交')).toBeInTheDocument();
    expect(screen.queryByText('讲义29提交')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '更多已完成记录' }));
    expect(screen.getByText('讲义29提交')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '跟随最新' }));
    expect(scrollIntoView).toHaveBeenCalledOnce();
    const scroller = screen.getByTestId('book-processing-scroll');
    Object.defineProperty(scroller, 'scrollHeight', {
      value: 1000,
      configurable: true,
    });
    Object.defineProperty(scroller, 'clientHeight', {
      value: 200,
      configurable: true,
    });
    scroller.scrollTop = 100;
    fireEvent.scroll(scroller);
    view.rerender(
      <BookProcessingView
        job={job}
        events={[...events]}
        connected={false}
        timing={projectBookTiming(job, null)}
        onReturnToReading={vi.fn()}
      />,
    );
    expect(scrollIntoView).toHaveBeenCalledOnce();
  });
  it('shows verified resources without implying parsing or a finished structure', () => {
    const job = processingJob();
    render(
      <BookProcessingView
        job={job}
        events={[]}
        connected={false}
        timing={projectBookTiming(job, Date.parse(job.server_now!))}
        onReturnToReading={vi.fn()}
      />,
    );
    expect(screen.getByText('正在准备教材来源')).toBeInTheDocument();
    expect(screen.getByText('已校验 2/3 个资源')).toBeInTheDocument();
    expect(screen.queryByText('正在解析文档')).not.toBeInTheDocument();
    expect(screen.getByText('显示最后确认的时间')).toBeInTheDocument();
  });

  it('keeps Agent actions neutral and tools folded, and returns only on command', () => {
    const job = processingJob({
      status: 'succeeded',
      finished_at: '2026-10-05T00:01:00Z',
    });
    const onReturn = vi.fn();
    const { container } = render(
      <BookProcessingView
        job={job}
        connected={false}
        timing={projectBookTiming(job, null)}
        onReturnToReading={onReturn}
        events={[
          {
            seq: 1,
            job_id: job.job_id,
            item_id: 'item-1',
            kind: 'progress',
            status: 'succeeded',
            message: '正在组织教材结构',
            metadata: { stage: 'structure_organizing' },
            created_at: job.created_at,
          },
          {
            seq: 2,
            job_id: job.job_id,
            item_id: 'item-1',
            kind: 'tool',
            status: 'succeeded',
            message: 'Running Bash',
            metadata: {},
            created_at: job.created_at,
          },
        ]}
      />,
    );
    expect(
      screen
        .getByText('正在组织教材结构')
        .closest('li')
        ?.querySelector('.lucide-check'),
    ).toBeNull();
    expect(screen.queryByText('Running Bash')).not.toBeInTheDocument();
    expect(
      container.querySelector('[data-testid="book-processing-scroll"]'),
    ).not.toBeNull();
    expect(onReturn).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '返回阅读' }));
    expect(onReturn).toHaveBeenCalledOnce();
  });
});
