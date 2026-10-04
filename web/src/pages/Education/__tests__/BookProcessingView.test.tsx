import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { BookProcessingView } from '../components/BookProcessingView';
import { projectBookTiming } from '../components/bookTimingProjection';
import { processingJob } from './bookProcessingFixtures';

describe('BookProcessingView', () => {
  it('shows waiting service stages and does not equate N/N resource count with frozen source readiness', () => {
    const job = processingJob();
    job.items[0].preparation_progress = {
      verified_resources: 3,
      total_resources: 3,
    };
    const view = render(
      <BookProcessingView
        job={job}
        events={[]}
        connected={false}
        timing={projectBookTiming(job, null)}
        sourceStatus="preparing"
        onReturnToReading={vi.fn()}
      />,
    );
    expect(
      screen.getByRole('listitem', { name: '来源准备' }),
    ).toHaveTextContent('进行中');
    expect(
      screen.getByRole('listitem', { name: '验收提交' }),
    ).toHaveTextContent('等待');
    expect(
      screen.getByRole('listitem', { name: 'PTC 执行' }),
    ).toHaveTextContent('未记录');
    job.items[0].execution_phase = 'runtime_queue';
    view.rerender(
      <BookProcessingView
        job={job}
        events={[]}
        connected={false}
        timing={projectBookTiming(job, null)}
        sourceStatus="ready"
        onReturnToReading={vi.fn()}
      />,
    );
    expect(
      screen.getByRole('listitem', { name: '来源准备' }),
    ).toHaveTextContent('已完成');
    expect(
      screen.getByRole('listitem', { name: '执行等待' }),
    ).toHaveTextContent('等待');
  });

  it('keeps missing phase duration visible and places only Agent reports under the PTC milestone', () => {
    const job = processingJob();
    job.items[0].execution_phase = 'ptc_execution';
    const events = [
      {
        seq: 1,
        job_id: job.job_id,
        item_id: 'item-1',
        kind: 'progress',
        status: 'succeeded',
        message: '正在组织教材结构',
        metadata: { stage: 'structure_organizing' },
        created_at: '2026-10-05T00:00:06Z',
      },
      {
        seq: 2,
        job_id: job.job_id,
        item_id: 'item-1',
        kind: 'tool',
        status: 'succeeded',
        message: 'Running Bash',
        metadata: {},
        created_at: '2026-10-05T00:00:07Z',
      },
    ];
    render(
      <BookProcessingView
        job={job}
        events={events}
        connected={false}
        timing={projectBookTiming(job, null)}
        sourceStatus="ready"
        onReturnToReading={vi.fn()}
      />,
    );
    const ptc = screen.getByRole('listitem', { name: 'PTC 执行' });
    expect(ptc).toHaveTextContent('进行中');
    expect(ptc).toHaveTextContent('未记录');
    expect(ptc).toHaveTextContent('正在组织教材结构');
    expect(screen.getAllByText('正在组织教材结构')).toHaveLength(1);
    expect(
      screen.getByText('正在组织教材结构').closest('li')?.querySelector('time'),
    ).toHaveAttribute('dateTime', events[0].created_at);
    expect(
      screen
        .getByText('正在组织教材结构')
        .closest('li')
        ?.querySelector('.lucide-check'),
    ).toBeNull();
    expect(screen.queryByText('Running Bash')).not.toBeInTheDocument();
  });

  it('marks cancellation at its actual phase without calling later stages completed', () => {
    const job = processingJob({ status: 'cancelled' });
    job.items[0].status = 'cancelled';
    render(
      <BookProcessingView
        job={job}
        events={[]}
        connected={false}
        timing={projectBookTiming(job, null)}
        sourceStatus="cancelled"
        onReturnToReading={vi.fn()}
      />,
    );
    expect(
      screen.getByRole('listitem', { name: '来源准备' }),
    ).toHaveTextContent('已取消');
    expect(
      screen.getByRole('listitem', { name: '验收提交' }),
    ).toHaveTextContent('未执行');
  });

  it('offers submitted and older materials from snapshots when activities are unavailable', () => {
    const base = processingJob();
    const successful = {
      ...base.items[0],
      item_id: 'material-1',
      kind: 'material' as const,
      status: 'succeeded' as const,
      position: 1,
      knowledge_point_id: 'kp-db-1',
      skill_kp_id: 'skill-kp-1',
      knowledge_point_title: '已提交项',
      timing_summary: {
        ...base.items[0].timing_summary!,
        terminal_at: base.server_now!,
        total_ms: 2000,
      },
    };
    const failed = {
      ...successful,
      item_id: 'material-2',
      position: 2,
      status: 'failed' as const,
      knowledge_point_id: 'kp-db-2',
      skill_kp_id: 'skill-kp-2',
      knowledge_point_title: '失败重做项',
      timing_summary: null,
    };
    const job = processingJob({
      kind: 'materials',
      status: 'partially_succeeded',
      activity_status: 'unavailable',
      items: [successful, failed],
    });
    const onOpen = vi.fn();
    render(
      <BookProcessingView
        job={job}
        events={[]}
        connected={false}
        timing={projectBookTiming(job, null)}
        onReturnToReading={vi.fn()}
        onOpenMaterial={onOpen}
        knowledgePoints={[
          {
            knowledge_point_id: 'kp-db-2',
            skill_kp_id: 'skill-kp-2',
            title: '失败重做项',
            material_available: true,
            position: 2,
            unit_skill_node_id: null,
            node_skill_ids: [],
            start_line: 1,
            end_line: 2,
            content_file: 'old.md',
          },
        ]}
      />,
    );
    expect(
      screen.getByRole('listitem', { name: '已提交项' }),
    ).toHaveTextContent('已提交');
    expect(
      screen.getByRole('listitem', { name: '已提交项' }),
    ).toHaveTextContent('2 秒');
    expect(
      screen.getByRole('listitem', { name: '失败重做项' }),
    ).toHaveTextContent('处理失败');
    expect(
      screen.getByRole('listitem', { name: '失败重做项' }),
    ).toHaveTextContent('未记录');
    expect(screen.getByText('旧版讲义仍可阅读')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '阅读讲义：已提交项' }));
    expect(onOpen).toHaveBeenCalledWith('skill-kp-1');
    fireEvent.click(
      screen.getByRole('button', { name: '阅读旧版讲义：失败重做项' }),
    );
    expect(onOpen).toHaveBeenCalledWith('skill-kp-2');
  });
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
            created_at: '2026-10-05T00:00:06Z',
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
