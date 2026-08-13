import { Activity, CircleCheck, Clock3, RefreshCcw, XCircle } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import type { TeachingJob, TeachingJobPhase } from './types';

const phaseLabels: Record<TeachingJobPhase, string> = {
  queued: '等待开始',
  preparing: '准备教材内容',
  building_skill: '整理知识要点',
  generating_teaching: '生成教学材料',
  validating: '校验教学包',
  review: '等待家长审阅',
  failed: '运行未完成',
  cancelled: '已取消',
};

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
          {job.error_message && <p className="mt-3 text-sm" role="alert" style={{ color: 'var(--color-danger)' }}>{job.error_message}</p>}
        </section>

        <section aria-label="运行阶段" className="grid gap-3">
          <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>阶段记录</h3>
          {job.events.length === 0 ? (
            <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>正在等待首个阶段记录。</p>
          ) : (
            <ol className="grid gap-3 border-l pl-4" style={{ borderColor: 'var(--color-border-muted)' }}>
              {job.events.map((event) => (
                <li key={`${event.sequence}-${event.phase}`} className="grid gap-1 text-sm">
                  <p style={{ color: 'var(--color-text-primary)' }}>{event.summary}</p>
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
