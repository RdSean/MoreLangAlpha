import { useMemo, useState } from 'react';
import { CheckCircle2, ClipboardPlus, RotateCcw, Send, XCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { useAuth } from '@/contexts/AuthContext';
import { uploadEducationAsset } from './api';
import { useEducationMembers, useEducationTaskMutations, useEducationTasks } from './queries';
import type { EducationMember, EducationTask, EducationTaskStatus } from './types';

const statusLabels: Record<EducationTaskStatus, string> = {
  open: '待完成',
  submitted: '待反馈',
  revision_requested: '需要修改',
  completed: '已完成',
  cancelled: '已取消',
};

function localDate(value: string) {
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(value));
}

async function uploadSelectedFile(file: File | null): Promise<string[]> {
  if (!file) return [];
  const asset = await uploadEducationAsset(file);
  return [asset.asset_id];
}

function ParentCreateDialog({ students, onSubmit, isPending }: { students: EducationMember[]; onSubmit: (input: { assignedStudentId: string; title: string; description: string; dueAt: string; frequency: 'once' | 'daily'; file: File | null }) => Promise<void>; isPending: boolean }) {
  const [open, setOpen] = useState(false);
  const [assignedStudentId, setAssignedStudentId] = useState('');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [dueAt, setDueAt] = useState('');
  const [frequency, setFrequency] = useState<'once' | 'daily'>('once');
  const [file, setFile] = useState<File | null>(null);

  return <Dialog open={open} onOpenChange={setOpen}>
    <DialogTrigger asChild><Button><ClipboardPlus className="mr-2 size-4" aria-hidden="true" />创建作业</Button></DialogTrigger>
    <DialogContent variant="centered" className="max-w-lg">
      <DialogHeader><DialogTitle>创建作业</DialogTitle><DialogDescription>分配给家庭中的学生，并设定提交时间。</DialogDescription></DialogHeader>
      <form className="grid gap-4" onSubmit={async (event) => { event.preventDefault(); await onSubmit({ assignedStudentId, title, description, dueAt, frequency, file }); setOpen(false); }}>
        <label className="grid gap-1.5 text-sm font-medium">学生<select value={assignedStudentId} onChange={(event) => setAssignedStudentId(event.target.value)} className="h-10 rounded-md border border-input bg-background px-3 text-sm" required><option value="" disabled>选择学生</option>{students.map((student) => <option value={student.user_id} key={student.user_id}>{student.name}</option>)}</select></label>
        <label className="grid gap-1.5 text-sm font-medium">标题<Input value={title} onChange={(event) => setTitle(event.target.value)} required /></label>
        <label className="grid gap-1.5 text-sm font-medium">说明<Textarea value={description} onChange={(event) => setDescription(event.target.value)} /></label>
        <label className="grid gap-1.5 text-sm font-medium">截止时间<Input type="datetime-local" value={dueAt} onChange={(event) => setDueAt(event.target.value)} required /></label>
        <label className="grid gap-1.5 text-sm font-medium">重复方式<select value={frequency} onChange={(event) => setFrequency(event.target.value as 'once' | 'daily')} className="h-10 rounded-md border border-input bg-background px-3 text-sm"><option value="once">一次</option><option value="daily">每天</option></select></label>
        <label className="grid gap-1.5 text-sm font-medium">材料附件<Input type="file" accept="application/pdf,image/jpeg,image/png,image/webp" onChange={(event) => setFile(event.target.files?.[0] ?? null)} /></label>
        <DialogFooter><Button type="submit" disabled={isPending || !assignedStudentId}>{isPending ? '正在创建' : '创建作业'}</Button></DialogFooter>
      </form>
    </DialogContent>
  </Dialog>;
}

function TaskActions({ task, role }: { task: EducationTask; role: 'parent' | 'student' }) {
  const mutations = useEducationTaskMutations();
  const [text, setText] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [open, setOpen] = useState(false);
  const canSubmit = role === 'student' && (task.status === 'open' || task.status === 'revision_requested');
  const canReview = role === 'parent' && task.status === 'submitted';
  const submit = async () => { const assetIds = await uploadSelectedFile(file); await mutations.submit.mutateAsync({ taskId: task.task_id, submission_text: text, idempotency_key: crypto.randomUUID(), asset_ids: assetIds }); setOpen(false); setText(''); setFile(null); };
  const review = async (decision: 'revision_requested' | 'completed') => { await mutations.review.mutateAsync({ taskId: task.task_id, decision, feedbackText: text }); setOpen(false); setText(''); };
  if (canSubmit) return <Dialog open={open} onOpenChange={setOpen}><DialogTrigger asChild><Button size="sm"><Send className="mr-2 size-4" aria-hidden="true" />提交作业</Button></DialogTrigger><DialogContent variant="centered" className="max-w-lg"><DialogHeader><DialogTitle>提交作业</DialogTitle><DialogDescription>可添加简短说明和一份 PDF 或图片附件。</DialogDescription></DialogHeader><div className="grid gap-4"><Textarea value={text} onChange={(event) => setText(event.target.value)} placeholder="写下完成情况" /><label className="grid gap-1.5 text-sm font-medium">附件<Input type="file" accept="application/pdf,image/jpeg,image/png,image/webp" onChange={(event) => setFile(event.target.files?.[0] ?? null)} /></label><DialogFooter><Button onClick={() => void submit()} disabled={mutations.submit.isPending || (!text.trim() && !file)}>{mutations.submit.isPending ? '正在提交' : '提交'}</Button></DialogFooter></div></DialogContent></Dialog>;
  if (canReview) return <Dialog open={open} onOpenChange={setOpen}><DialogTrigger asChild><Button size="sm" variant="outline"><RotateCcw className="mr-2 size-4" aria-hidden="true" />反馈</Button></DialogTrigger><DialogContent variant="centered" className="max-w-lg"><DialogHeader><DialogTitle>作业反馈</DialogTitle><DialogDescription>反馈仅支持纯文本。</DialogDescription></DialogHeader><div className="grid gap-4"><Textarea value={text} onChange={(event) => setText(event.target.value)} placeholder="写下修改建议或完成反馈" /><DialogFooter><Button variant="outline" onClick={() => void review('revision_requested')} disabled={!text.trim() || mutations.review.isPending}>请求修改</Button><Button onClick={() => void review('completed')} disabled={!text.trim() || mutations.review.isPending}>标记完成</Button></DialogFooter></div></DialogContent></Dialog>;
  return null;
}

export default function EducationPage() {
  const { member } = useAuth();
  const tasksQuery = useEducationTasks();
  const mutations = useEducationTaskMutations();
  const tasks = useMemo(() => tasksQuery.data ?? [], [tasksQuery.data]);
  const role = member?.role ?? 'student';
  const membersQuery = useEducationMembers(role === 'parent');
  const students = useMemo(() => (membersQuery.data ?? []).filter((member) => member.role === 'student'), [membersQuery.data]);
  const create = async ({ assignedStudentId, title, description, dueAt, frequency, file }: { assignedStudentId: string; title: string; description: string; dueAt: string; frequency: 'once' | 'daily'; file: File | null }) => {
    const materialAssetIds = await uploadSelectedFile(file);
    await mutations.create.mutateAsync({ assigned_student_id: assignedStudentId, title, description, due_at: new Date(dueAt).toISOString(), frequency, material_asset_ids: materialAssetIds });
  };
  return <main className="h-full min-h-0 overflow-y-auto bg-canvas" data-testid="education-page"><div className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-4 py-6 sm:px-6 lg:px-8 lg:py-8"><header className="flex flex-col gap-4 border-b pb-5 sm:flex-row sm:items-end sm:justify-between" style={{ borderColor: 'var(--color-border-muted)' }}><div><p className="font-mono text-xs" style={{ color: 'var(--color-text-tertiary)' }}>FAMILY EDUCATION</p><h1 className="title-font mt-2 text-2xl font-semibold" style={{ color: 'var(--color-text-primary)' }}>{role === 'parent' ? '家庭作业' : '我的作业'}</h1><p className="mt-1 text-sm" style={{ color: 'var(--color-text-secondary)' }}>{role === 'parent' ? '创建任务、查看提交并给出文字反馈。' : '查看任务、提交作业并根据反馈修改。'}</p></div>{role === 'parent' && <ParentCreateDialog students={students} onSubmit={create} isPending={mutations.create.isPending} />}</header><section aria-label="作业列表" className="border-t" style={{ borderColor: 'var(--color-border-muted)' }}>{tasksQuery.isLoading ? <p className="py-8 text-sm text-muted-foreground">正在加载作业…</p> : tasks.length === 0 ? <p className="py-8 text-sm text-muted-foreground">暂无作业。</p> : tasks.map((task) => <article key={task.task_id} className="grid gap-3 border-b py-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center" style={{ borderColor: 'var(--color-border-muted)' }}><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h2 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>{task.title}</h2><span className="rounded border px-2 py-0.5 font-mono text-[11px]" style={{ borderColor: 'var(--color-border-muted)', color: 'var(--color-text-secondary)' }}>{statusLabels[task.status]}</span></div>{task.description && <p className="mt-1 text-sm" style={{ color: 'var(--color-text-secondary)' }}>{task.description}</p>}{task.latest_feedback_text && <p className="mt-2 border-l-2 pl-3 text-sm" style={{ borderColor: 'var(--color-border-muted)', color: 'var(--color-text-secondary)' }}>反馈：{task.latest_feedback_text}</p>}<p className="mt-2 font-mono text-xs" style={{ color: 'var(--color-text-tertiary)' }}>截止 {localDate(task.due_at)}</p></div><div className="flex flex-wrap items-center gap-2"><TaskActions task={task} role={role} />{role === 'parent' && task.status !== 'completed' && task.status !== 'cancelled' && <TooltipProvider><Tooltip><TooltipTrigger asChild><Button size="icon" variant="ghost" aria-label="取消作业" onClick={() => void mutations.cancel.mutateAsync(task.task_id)}><XCircle className="size-4" aria-hidden="true" /></Button></TooltipTrigger><TooltipContent>取消作业</TooltipContent></Tooltip></TooltipProvider>}{task.status === 'completed' && <CheckCircle2 className="size-5" aria-label="已完成" style={{ color: 'var(--color-success)' }} />}</div></article>)}</section></div></main>;
}
