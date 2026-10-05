import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/i18n';
import { BookProcessingView } from '../components/BookProcessingView';
import { projectBookTiming } from '../components/bookTimingProjection';
import { processingJob } from './bookProcessingFixtures';
beforeEach(() => { void i18n.changeLanguage('zh-CN'); });

describe('BookProcessingView', () => {
  it('keeps tool diagnostics in the PTC phase and resets disclosure when the phase changes', () => {
    const job = processingJob();
    job.items[0].execution_phase = 'ptc_execution';
    const events = [{ seq: 1, job_id: job.job_id, item_id: 'item-1', kind: 'tool', status: 'running', message: 'Running Bash', metadata: {}, created_at: '2026-10-05T00:00:06Z' }];
    const props = { job, events, connected: true, timing: projectBookTiming(job, null), onReturnToReading: vi.fn() };
    const view = render(<BookProcessingView {...props} />);
    fireEvent.click(screen.getByRole('button', { name: '最新诊断' }));
    expect(screen.getByRole('listitem', { name: 'PTC 执行' })).toHaveTextContent('Bash 执行中');
    job.items[0].execution_phase = 'finalization';
    view.rerender(<BookProcessingView {...props} />);
    expect(screen.getByRole('listitem', { name: '验收提交' })).not.toHaveTextContent('Bash 执行中');
    expect(screen.queryByRole('button', { name: '最新诊断' })).not.toBeInTheDocument();
    job.items[0].execution_phase = 'ptc_execution';
    view.rerender(<BookProcessingView {...props} />);
    expect(screen.getByRole('button', { name: '最新诊断' })).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('Bash 执行中')).not.toBeInTheDocument();
  });
  it('keeps only the latest current attempt report and has no growing history controls', () => {
    const job = processingJob();
    job.items[0].execution_phase = 'ptc_execution';
    const events = Array.from({ length: 60 }, (_, index) => ({
      seq: index + 1, job_id: job.job_id, item_id: 'item-1', kind: 'progress',
      status: 'running', message: `业务动作 ${index}`,
      metadata: { stage: 'structure_organizing', action: `action-${index}` },
      created_at: '2026-10-05T00:00:06Z',
    }));
    render(<BookProcessingView job={job} events={events} connected timing={projectBookTiming(job, null)} onReturnToReading={vi.fn()} />);
    expect(screen.getAllByText('业务动作 59')).toHaveLength(1);
    expect(screen.queryByText('业务动作 0')).not.toBeInTheDocument();
    expect(screen.queryByText('尝试与批量统计')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '跟随最新' })).not.toBeInTheDocument();
  });

  it('shows a manual learning entry and missing token usage after completion', () => {
    const job = processingJob({ status: 'succeeded', finished_at: '2026-10-05T00:00:10Z' });
    job.items[0].status = 'succeeded';
    const enter = vi.fn();
    render(<BookProcessingView job={job} events={[]} connected={false} timing={projectBookTiming(job, null)} onReturnToReading={enter} />);
    expect(screen.getByText('Token 消耗')).toBeInTheDocument();
    expect(enter).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '进入学习空间' }));
    expect(enter).toHaveBeenCalledOnce();
  });
  it('uses the book title and original PDF pages, without inventing a page count', () => {
    const job = processingJob();
    const source = { document_id: 'doc', parse_job_id: 'parse', primary_artifact_id: 'artifact', filename: 'book.pdf', media_type: 'application/pdf', page_count: 25, parser_id: 'parser', parser_name: 'Parser', completed_at: job.created_at, content_sha256: 'sha', size_bytes: 1000, image_count: 2, frozen_at: null };
    const props = { job, events: [], connected: false, timing: projectBookTiming(job, null), onReturnToReading: vi.fn(), bookTitle: '原始书名', source };
    const view = render(<BookProcessingView {...props} />);
    expect(screen.getByRole('heading', { name: '原始书名' })).toBeInTheDocument();
    expect(screen.getByText('PDF · 25 页')).toBeInTheDocument();
    view.rerender(<BookProcessingView {...props} source={{ ...source, page_count: null }} />);
    expect(screen.getByText('PDF')).toBeInTheDocument();
    expect(screen.queryByText(/25 页/)).not.toBeInTheDocument();
    expect(screen.queryByText(/行数/)).not.toBeInTheDocument();
  });
  it('labels partial token records and localizes completion to the selected language', async () => {
    await i18n.changeLanguage('en-US');
    const job = processingJob({ status: 'succeeded', token_usage: { status: 'partial', input_tokens: 300, output_tokens: 50, total_tokens: 350, recorded_calls: 1 } });
    job.items[0].status = 'succeeded';
    render(<BookProcessingView job={job} events={[]} connected={false} timing={projectBookTiming(job, null)} onReturnToReading={vi.fn()} />);
    expect(screen.getByText('Recorded tokens')).toBeInTheDocument();
    expect(screen.getByText('350')).toBeInTheDocument();
    expect(screen.getByText('Partially recorded')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Enter learning space' })).toBeInTheDocument();
    expect(screen.queryByText('未记录')).not.toBeInTheDocument();
  });
  it('does not place a late service or Agent report under an unrelated current phase', () => {
    const job = processingJob();
    job.items[0].execution_phase = 'finalization';
    const events = [{ seq: 1, job_id: job.job_id, item_id: 'item-1', kind: 'progress', status: 'running', message: '旧输入准备', metadata: { stage: 'service_preparing', origin: 'service' }, created_at: '2026-10-05T00:00:06Z' }, { seq: 2, job_id: job.job_id, item_id: 'item-1', kind: 'progress', status: 'running', message: '旧模型动作', metadata: { stage: 'structure_organizing' }, created_at: '2026-10-05T00:00:07Z' }];
    render(<BookProcessingView job={job} events={events} connected timing={projectBookTiming(job, null)} onReturnToReading={vi.fn()} />);
    expect(screen.queryByText('旧输入准备')).not.toBeInTheDocument();
    expect(screen.queryByText('旧模型动作')).not.toBeInTheDocument();
    expect(screen.getByRole('listitem', { name: '验收提交' })).toHaveTextContent('进行中');
  });
  it('keeps the next queued lesson waiting after the first lesson was submitted', () => {
    const base = processingJob();
    const completed = {
      ...base.items[0],
      kind: 'material' as const,
      status: 'succeeded' as const,
      execution_phase: 'finalization' as const,
      skill_kp_id: 'first',
      knowledge_point_title: '首份讲义',
    };
    const queued = {
      ...completed,
      item_id: 'item-next',
      status: 'queued' as const,
      position: 2,
      attempt: 0,
      started_at: null,
      execution_phase: 'initial_queue' as const,
      timing_summary: null,
      skill_kp_id: 'next',
      knowledge_point_title: '下一份讲义',
    };
    const job = processingJob({
      kind: 'materials',
      succeeded_items: 1,
      total_items: 2,
      items: [completed, queued],
    });
    const timing = projectBookTiming(job, null);
    render(
      <BookProcessingView
        job={job}
        events={[]}
        connected={false}
        timing={timing}
        onReturnToReading={vi.fn()}
      />,
    );
    expect(screen.getByText('知识点：下一份讲义')).toBeInTheDocument();
    expect(screen.getByRole('listitem', { name: 'PTC 执行' })).toHaveTextContent('等待');
    expect(screen.getByRole('listitem', { name: 'PTC 执行' })).not.toHaveTextContent('已完成');
    expect(screen.getByRole('listitem', { name: '验收提交' })).toHaveTextContent('等待');
    expect(timing.attemptMs).toBeNull();
    expect(timing.phases.every((phase) => phase.ms === null)).toBe(true);
  });
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
  it('keeps large batch results bounded and the first committed lesson readable', () => {
    const base = processingJob();
    const job = processingJob({ kind: 'materials', status: 'succeeded', items: Array.from({ length: 60 }, (_, index) => ({ ...base.items[0], kind: 'material' as const, status: 'succeeded' as const, item_id: `item-${index}`, skill_kp_id: `kp-${index}`, knowledge_point_title: `知识点 ${index}` })) });
    const open = vi.fn();
    render(<BookProcessingView job={job} events={[]} connected={false} timing={projectBookTiming(job, null)} onReturnToReading={vi.fn()} onOpenMaterial={open} />);
    expect(screen.getByRole('button', { name: '阅读讲义：知识点 0' })).toBeInTheDocument();
    expect(screen.queryByText('知识点 59')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /更多已完成/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '阅读讲义：知识点 0' }));
    expect(open).toHaveBeenCalledWith('kp-0');
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
    expect(screen.getByRole('listitem', { name: '来源准备' })).toHaveTextContent('进行中');
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
    fireEvent.click(screen.getByRole('button', { name: '进入学习空间' }));
    expect(onReturn).toHaveBeenCalledOnce();
  });
});
