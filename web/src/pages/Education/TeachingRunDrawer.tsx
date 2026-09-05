import { Activity, CircleCheck, Clock3, RefreshCcw, XCircle } from 'lucide-react';
import { Link } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import type { TeachingJob, TeachingJobPhase } from './types';

const phaseLabels: Record<TeachingJobPhase, string> = {
  queued: '等待开始',
  preparing: '准备教材内容',
  building_skill: '整理知识要点',
  generating_teaching: '生成教学材料',
  validating: '校验教学包',
  planning: '规划知识资产',
  chapter_mapping: '章节映射',
  concept_linking: '概念关联',
  coverage_audit: '覆盖审计',
  practice_build: '练习构建',
  teaching_build: '教学材料生成',
  bundle_assembling: '汇总教学资产',
  validating_bundle: '校验教学资产',
  review: '等待家长审阅',
  failed: '运行未完成',
  cancelled: '已取消',
};

const assetLabels = {
  knowledge: '知识资产',
  toolkit: '工具包资产',
  practice: '练习资产',
  teaching: '教学材料',
} as const;

function statusIcon(phase: TeachingJobPhase) {
  if (phase === 'review') return <CircleCheck className="size-4" aria-hidden="true" />;
  if (phase === 'failed' || phase === 'cancelled') return <XCircle className="size-4" aria-hidden="true" />;
  return <Activity className="size-4" aria-hidden="true" />;
}

function formatTime(value: string | null | undefined) {
  if (!value) return '暂无时间记录';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '暂无时间记录' : date.toLocaleString('zh-CN', { hour12: false });
}

function formatDuration(start: string | null | undefined, end: string | null | undefined) {
  if (!start) return '暂无时长记录';
  const startedAt = new Date(start).getTime();
  const endedAt = end ? new Date(end).getTime() : Date.now();
  if (Number.isNaN(startedAt) || Number.isNaN(endedAt) || endedAt < startedAt) return '暂无时长记录';
  const totalMinutes = Math.floor((endedAt - startedAt) / 60_000);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return hours > 0 ? `${hours} 小时 ${minutes} 分钟` : `${minutes} 分钟`;
}

type Props = {
  job: TeachingJob;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCancel?: () => void;
  onResume?: () => void;
  cancelling?: boolean;
  resuming?: boolean;
};

export default function TeachingRunDrawer({
  job,
  open,
  onOpenChange,
  onCancel,
  onResume,
  cancelling = false,
  resuming = false,
}: Props) {
  const canCancel = job.actions.includes('cancel') && onCancel;
  const canResume = job.actions.includes('resume') && onResume;
  const needsModelConfiguration = job.error_message === '教材教学加工需要先配置模型服务，再继续运行。';
  const isActive = job.status === 'queued' || job.status === 'preparing' || job.status === 'running' || job.status === 'validating';
  const isVerified = job.status === 'completed' && job.phase === 'review';

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl" variant="default">
        <DialogHeader>
          <DialogTitle>教材教学包运行</DialogTitle>
          <DialogDescription>阶段进度会自动更新。</DialogDescription>
        </DialogHeader>

        <section aria-label="当前阶段" className="border-y py-4" style={{ borderColor: 'var(--color-border-muted)' }}>
          <div className="flex items-center gap-2 text-sm font-medium" style={{ color: 'var(--color-text-primary)' }}>
            {statusIcon(job.phase)}
            {phaseLabels[job.phase]}
          </div>
          <p className="mt-2 text-sm" style={{ color: 'var(--color-text-secondary)' }}>
            已完成 {job.completed_chapter_count} / {job.total_chapter_count} 章
          </p>
          <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2" style={{ color: 'var(--color-text-secondary)' }}>
            <div className="grid gap-0.5"><dt className="font-mono text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>运行时长</dt><dd>{formatDuration(job.created_at, job.completed_at)}</dd></div>
            <div className="grid gap-0.5"><dt className="font-mono text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>最近持久心跳</dt><dd>{formatTime(job.last_heartbeat_at)}</dd></div>
          </dl>
          {isActive && <p className="mt-3 text-sm" style={{ color: 'var(--color-text-secondary)' }}>正在等待 Agent/模型响应</p>}
          {job.error_message && <p className="mt-3 text-sm" role="alert" style={{ color: 'var(--color-loss)' }}>{job.error_message}</p>}
          {needsModelConfiguration && <Link to="/setup/method" className="mt-3 inline-flex text-sm underline" style={{ color: 'var(--color-accent-primary)' }}>配置模型服务</Link>}
        </section>

        <section aria-label="运行阶段" className="grid gap-3">
          <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>阶段记录</h3>
          {job.events.length === 0 ? (
            <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>正在等待首个阶段记录。</p>
          ) : (
            <ol className="grid gap-3 border-l pl-4" style={{ borderColor: 'var(--color-border-muted)' }}>
              {job.events.map((event) => (
                <li key={`${event.sequence}-${event.phase}`} className="grid gap-1 text-sm">
                  <div className="flex flex-wrap items-center gap-2"><span className="font-mono text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>{isVerified ? '已验证' : 'Agent 已报告'}</span><span style={{ color: 'var(--color-text-primary)' }}>{event.summary}</span>{event.asset_kind && <span className="border px-1.5 py-0.5 font-mono text-[11px]" style={{ borderColor: 'var(--color-border-muted)', color: 'var(--color-text-secondary)' }}>{assetLabels[event.asset_kind]}</span>}</div>
                  <time className="font-mono text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>{formatTime(event.created_at)}</time>
                </li>
              ))}
            </ol>
          )}
        </section>

        <section aria-label="运行尝试" className="grid gap-2 border-t pt-4" style={{ borderColor: 'var(--color-border-muted)' }}>
          <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>运行尝试</h3>
          <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--color-text-secondary)' }}>
            <Clock3 className="size-4" aria-hidden="true" />
            已创建 {job.attempt_count} 次尝试
          </div>
        </section>

        {(canCancel || canResume) && (
          <DialogFooter>
            {canCancel && <Button variant="outline" onClick={onCancel} disabled={cancelling}>{cancelling ? '正在取消' : '取消加工'}</Button>}
            {canResume && <Button onClick={onResume} disabled={resuming}><RefreshCcw className="mr-2 size-4" aria-hidden="true" />{resuming ? '正在继续' : '继续运行'}</Button>}
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
}
