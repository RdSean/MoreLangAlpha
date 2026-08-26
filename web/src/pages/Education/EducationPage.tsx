import { useMemo, useRef, useState } from 'react';
import { CheckCircle2, ClipboardPlus, RotateCcw, Send, XCircle } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { useAuth } from '@/contexts/AuthContext';
import { createRequestKeyTracker } from '@/pages/ChatAgent/hooks/utils/requestKey';
import { uploadEducationAsset } from './api';
import { useEducationHomeworkDictionaries, useEducationMembers, useEducationTaskMutations, useEducationTasks, useLearningAssignments } from './queries';
import type { CreateEducationTaskInput, EducationHomeworkDictionaries, EducationMember, EducationTask, EducationTaskStatus } from './types';

const statusLabels: Record<EducationTaskStatus, string> = {
  open: '待完成',
  completed: '已完成',
  cancelled: '已取消',
};

function localDate(value: string) {
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(value));
}

async function uploadSelectedFiles(files: File[]): Promise<string[]> {
  const assets = await Promise.all(files.map((file) => uploadEducationAsset(file)));
  return assets.map((asset) => asset.asset_id);
}

type ParentCreateInput = {
  assignedStudentId: string;
  title: string;
  description: string;
  dueAt: string;
  subjectCode: string;
  typeCode: string;
  practiceSourceCode: string | null;
  frequency: CreateEducationTaskInput['frequency'];
  weekdays: number[] | null;
  files: File[];
};

const weeklyDayOptions = [
  [1, '周一'], [2, '周二'], [3, '周三'], [4, '周四'], [5, '周五'], [6, '周六'], [7, '周日'],
] as const;

function readableError(error: unknown) {
  return error instanceof Error ? error.message : '操作失败，请重试。';
}

function ParentCreateDialog({ students, dictionaries, onSubmit, isPending }: {
  students: EducationMember[];
  dictionaries: EducationHomeworkDictionaries | undefined;
  onSubmit: (input: ParentCreateInput) => Promise<void>;
  isPending: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [assignedStudentId, setAssignedStudentId] = useState('');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [dueAt, setDueAt] = useState('');
  const [subjectCode, setSubjectCode] = useState('');
  const [typeCode, setTypeCode] = useState('');
  const [practiceSourceCode, setPracticeSourceCode] = useState('');
  const [frequency, setFrequency] = useState<CreateEducationTaskInput['frequency']>('once');
  const [weekdays, setWeekdays] = useState<number[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const subject = dictionaries?.subjects.find((item) => item.code === subjectCode);
  const selectedStudent = students.find((student) => student.user_id === assignedStudentId);
  const isDictionaryReady = Boolean(dictionaries);
  const hasStudentGrade = Boolean(selectedStudent?.grade_code);
  const gradeName = dictionaries?.grade_levels.find((grade) => grade.code === selectedStudent?.grade_code)?.name ?? '未设置年级';
  const isPractice = typeCode === 'practice';
  const needsWeekdaySelection = frequency === 'weekly';

  const updateFrequency = (nextFrequency: CreateEducationTaskInput['frequency']) => {
    setFrequency(nextFrequency);
    if (nextFrequency !== 'weekly') setWeekdays([]);
  };
  const toggleWeekday = (weekday: number) => {
    setWeekdays((current) => current.includes(weekday)
      ? current.filter((item) => item !== weekday)
      : [...current, weekday].sort((left, right) => left - right));
  };

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitError(null);
    try {
      await onSubmit({
        assignedStudentId,
        title,
        description,
        dueAt,
        subjectCode,
        typeCode,
        practiceSourceCode: isPractice ? practiceSourceCode : null,
        frequency,
        weekdays: needsWeekdaySelection ? weekdays : null,
        files,
      });
      setOpen(false);
    } catch (error) {
      setSubmitError(readableError(error));
    }
  };

  return <Dialog open={open} onOpenChange={setOpen}>
    <DialogTrigger asChild><Button><ClipboardPlus className="mr-2 size-4" aria-hidden="true" />创建作业</Button></DialogTrigger>
    <DialogContent variant="centered" className="max-w-lg">
      <DialogHeader><DialogTitle>创建作业</DialogTitle><DialogDescription>分配给家庭中的学生，并设定完成时间。</DialogDescription></DialogHeader>
      <form className="grid gap-4" onSubmit={(event) => void submit(event)}>
        <label className="grid gap-1.5 text-sm font-medium">学生<select value={assignedStudentId} onChange={(event) => setAssignedStudentId(event.target.value)} className="h-10 rounded-md border border-input bg-background px-3 text-sm" required><option value="" disabled>选择学生</option>{students.map((student) => <option value={student.user_id} key={student.user_id}>{student.name}</option>)}</select></label>
        {selectedStudent && !isDictionaryReady && <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>正在加载作业字典…</p>}
        {selectedStudent && isDictionaryReady && <p className="text-sm" style={{ color: hasStudentGrade ? 'var(--color-text-secondary)' : 'var(--color-loss)' }}>当前年级：{gradeName}</p>}
        {selectedStudent && isDictionaryReady && !hasStudentGrade && <p className="text-sm" style={{ color: 'var(--color-loss)' }}>请先在‘设置 &gt; 家庭账户’中为该学生设置当前年级。</p>}
        <label className="grid gap-1.5 text-sm font-medium">科目<select value={subjectCode} onChange={(event) => { setSubjectCode(event.target.value); setTypeCode(''); setPracticeSourceCode(''); }} className="h-10 rounded-md border border-input bg-background px-3 text-sm" required><option value="" disabled>选择科目</option>{(dictionaries?.subjects ?? []).map((item) => <option value={item.code} key={item.code}>{item.name}</option>)}</select></label>
        <label className="grid gap-1.5 text-sm font-medium">作业类型<select value={typeCode} onChange={(event) => { setTypeCode(event.target.value); setPracticeSourceCode(''); }} className="h-10 rounded-md border border-input bg-background px-3 text-sm" required disabled={!subject}><option value="" disabled>选择作业类型</option>{subject?.homework_types.map((item) => <option value={item.code} key={item.code}>{item.name}</option>)}</select></label>
        {isPractice && <label className="grid gap-1.5 text-sm font-medium">练习来源<select value={practiceSourceCode} onChange={(event) => setPracticeSourceCode(event.target.value)} className="h-10 rounded-md border border-input bg-background px-3 text-sm" required><option value="" disabled>选择练习来源</option>{(dictionaries?.practice_sources ?? []).map((item) => <option value={item.code} key={item.code}>{item.name}</option>)}</select></label>}
        <label className="grid gap-1.5 text-sm font-medium">标题<Input value={title} onChange={(event) => setTitle(event.target.value)} required /></label>
        <label className="grid gap-1.5 text-sm font-medium">说明<Textarea value={description} onChange={(event) => setDescription(event.target.value)} /></label>
        <label className="grid gap-1.5 text-sm font-medium">截止时间<Input type="datetime-local" value={dueAt} onChange={(event) => setDueAt(event.target.value)} required /></label>
        <label className="grid gap-1.5 text-sm font-medium">重复方式<select value={frequency} onChange={(event) => updateFrequency(event.target.value as CreateEducationTaskInput['frequency'])} className="h-10 rounded-md border border-input bg-background px-3 text-sm"><option value="once">一次</option><option value="daily">每天</option><option value="weekdays">工作日</option><option value="weekly">每周指定日期</option></select></label>
        {needsWeekdaySelection && <fieldset className="grid gap-2"><legend className="text-sm font-medium">每周日期</legend><div className="flex flex-wrap gap-x-4 gap-y-2">{weeklyDayOptions.map(([weekday, label]) => <label className="flex items-center gap-2 text-sm" key={weekday}><input type="checkbox" checked={weekdays.includes(weekday)} onChange={() => toggleWeekday(weekday)} />{label}</label>)}</div></fieldset>}
        <label className="grid gap-1.5 text-sm font-medium">材料附件<Input type="file" multiple accept="application/pdf,image/jpeg,image/png,image/webp" onChange={(event) => setFiles(Array.from(event.target.files ?? []))} />{files.length > 0 && <span className="text-xs font-normal" style={{ color: 'var(--color-text-secondary)' }}>已选择 {files.length} 份附件</span>}</label>
        {submitError && <p role="alert" className="text-sm" style={{ color: 'var(--color-loss)' }}>{submitError}</p>}
        <DialogFooter><Button type="submit" disabled={isPending || !isDictionaryReady || !assignedStudentId || !hasStudentGrade || !subjectCode || !typeCode || (isPractice && !practiceSourceCode) || (needsWeekdaySelection && weekdays.length === 0)}>{isPending ? '正在创建' : '创建作业'}</Button></DialogFooter>
      </form>
    </DialogContent>
  </Dialog>;
}

function TaskActions({ task, role }: { task: EducationTask; role: 'parent' | 'student' }) {
  const mutations = useEducationTaskMutations();
  const [text, setText] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [open, setOpen] = useState(false);
  const requestKeyTracker = useRef(createRequestKeyTracker());

  const makeRequestKey = () => requestKeyTracker.current.take([task.task_id, text, ...files.map((file) => `${file.name}:${file.size}:${file.lastModified}`)].join('\u0000'));
  const checkIn = async () => {
    await mutations.checkIn.mutateAsync({ taskId: task.task_id, submission_text: '', idempotency_key: makeRequestKey(), asset_ids: [] });
    requestKeyTracker.current.clear();
  };
  const appendRevision = async () => {
    const assetIds = await uploadSelectedFiles(files);
    await mutations.appendRevision.mutateAsync({ taskId: task.task_id, submission_text: text, idempotency_key: makeRequestKey(), asset_ids: assetIds });
    requestKeyTracker.current.clear();
    setOpen(false);
    setText('');
    setFiles([]);
  };
  const review = async (decision: 'feedback' | 'revision_requested') => {
    await mutations.review.mutateAsync({ taskId: task.task_id, decision, feedbackText: text });
    setOpen(false);
    setText('');
  };

  if (role === 'student' && task.status === 'open') {
    return <Button size="sm" onClick={() => void checkIn()} disabled={mutations.checkIn.isPending}><CheckCircle2 className="mr-2 size-4" aria-hidden="true" />{mutations.checkIn.isPending ? '正在打卡' : '完成打卡'}</Button>;
  }
  if (role === 'student' && task.status === 'completed') {
    return <Dialog open={open} onOpenChange={setOpen}><DialogTrigger asChild><Button size="sm" variant="outline"><Send className="mr-2 size-4" aria-hidden="true" />补充提交</Button></DialogTrigger><DialogContent variant="centered" className="max-w-lg"><DialogHeader><DialogTitle>补充提交</DialogTitle><DialogDescription>可追加文字说明或多份 PDF、图片附件。</DialogDescription></DialogHeader><div className="grid gap-4"><Textarea value={text} onChange={(event) => setText(event.target.value)} placeholder="补充说明或修改内容" /><label className="grid gap-1.5 text-sm font-medium">附件<Input type="file" multiple accept="application/pdf,image/jpeg,image/png,image/webp" onChange={(event) => setFiles(Array.from(event.target.files ?? []))} /></label><DialogFooter><Button onClick={() => void appendRevision()} disabled={mutations.appendRevision.isPending || (!text.trim() && files.length === 0)}>{mutations.appendRevision.isPending ? '正在提交' : '提交补充'}</Button></DialogFooter></div></DialogContent></Dialog>;
  }
  if (role === 'parent' && task.status === 'completed') {
    return <Dialog open={open} onOpenChange={setOpen}><DialogTrigger asChild><Button size="sm" variant="outline"><RotateCcw className="mr-2 size-4" aria-hidden="true" />反馈</Button></DialogTrigger><DialogContent variant="centered" className="max-w-lg"><DialogHeader><DialogTitle>作业反馈</DialogTitle><DialogDescription>反馈不会改变学生已完成状态。</DialogDescription></DialogHeader><div className="grid gap-4"><Textarea value={text} onChange={(event) => setText(event.target.value)} placeholder="写下修改建议或完成反馈" /><DialogFooter><Button variant="outline" onClick={() => void review('revision_requested')} disabled={!text.trim() || mutations.review.isPending}>请求修改</Button><Button onClick={() => void review('feedback')} disabled={!text.trim() || mutations.review.isPending}>保存反馈</Button></DialogFooter></div></DialogContent></Dialog>;
  }
  return null;
}

function TaskRows({ tasks, role }: { tasks: EducationTask[]; role: 'parent' | 'student' }) {
  const mutations = useEducationTaskMutations();
  if (tasks.length === 0) return <p className="py-8 text-sm text-muted-foreground">暂无作业。</p>;
  return <>{tasks.map((task) => <article key={task.task_id} className="grid gap-3 border-b py-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center" style={{ borderColor: 'var(--color-border-muted)' }}><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h2 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>{task.title}</h2><span className="rounded border px-2 py-0.5 font-mono text-[11px]" style={{ borderColor: 'var(--color-border-muted)', color: 'var(--color-text-secondary)' }}>{statusLabels[task.status]}</span></div>{task.description && <p className="mt-1 text-sm" style={{ color: 'var(--color-text-secondary)' }}>{task.description}</p>}{task.latest_feedback_text && <p className="mt-2 border-l-2 pl-3 text-sm" style={{ borderColor: 'var(--color-border-muted)', color: 'var(--color-text-secondary)' }}>反馈：{task.latest_feedback_text}</p>}<p className="mt-2 font-mono text-xs" style={{ color: 'var(--color-text-tertiary)' }}>截止 {localDate(task.due_at)}</p></div><div className="flex flex-wrap items-center gap-2"><TaskActions task={task} role={role} />{role === 'parent' && task.status === 'open' && <TooltipProvider><Tooltip><TooltipTrigger asChild><Button size="icon" variant="ghost" aria-label="取消作业" onClick={() => void mutations.cancel.mutateAsync(task.task_id)}><XCircle className="size-4" aria-hidden="true" /></Button></TooltipTrigger><TooltipContent>取消作业</TooltipContent></Tooltip></TooltipProvider>}{task.status === 'completed' && <CheckCircle2 className="size-5" aria-label="已完成" style={{ color: 'var(--color-success)' }} />}</div></article>)}</>;
}

export default function EducationPage() {
  const { member } = useAuth();
  const tasksQuery = useEducationTasks();
  const dictionariesQuery = useEducationHomeworkDictionaries();
  const mutations = useEducationTaskMutations();
  const tasks = useMemo(() => tasksQuery.data ?? [], [tasksQuery.data]);
  const role = member?.role ?? 'student';
  const membersQuery = useEducationMembers(role === 'parent');
  const learningAssignments = useLearningAssignments(role === 'student');
  const students = useMemo(() => (membersQuery.data ?? []).filter((item) => item.role === 'student'), [membersQuery.data]);
  const create = async ({ assignedStudentId, title, description, dueAt, subjectCode, typeCode, practiceSourceCode, frequency, weekdays, files }: ParentCreateInput) => {
    const materialAssetIds = await uploadSelectedFiles(files);
    const input: CreateEducationTaskInput = { assigned_student_id: assignedStudentId, title, description, due_at: new Date(dueAt).toISOString(), subject_code: subjectCode, type_code: typeCode, practice_source_code: practiceSourceCode, frequency, weekdays, material_asset_ids: materialAssetIds };
    await mutations.create.mutateAsync(input);
  };

  if (role === 'parent') return <main className="h-full min-h-0 overflow-y-auto bg-canvas" data-testid="education-page"><div className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-4 py-6 sm:px-6 lg:px-8 lg:py-8"><header className="flex flex-col gap-4 border-b pb-5 sm:flex-row sm:items-end sm:justify-between" style={{ borderColor: 'var(--color-border-muted)' }}><div><p className="font-mono text-xs" style={{ color: 'var(--color-text-tertiary)' }}>FAMILY EDUCATION</p><h1 className="title-font mt-2 text-2xl font-semibold" style={{ color: 'var(--color-text-primary)' }}>家庭作业</h1><p className="mt-1 text-sm" style={{ color: 'var(--color-text-secondary)' }}>创建任务、查看学生打卡并给出文字反馈。</p></div><div className="flex flex-wrap gap-2"><Link to="/education/textbooks"><Button variant="outline">家庭教材库</Button></Link><ParentCreateDialog students={students} dictionaries={dictionariesQuery.data} onSubmit={create} isPending={mutations.create.isPending} /></div></header><section aria-label="作业列表" className="border-t" style={{ borderColor: 'var(--color-border-muted)' }}>{tasksQuery.isLoading ? <p className="py-8 text-sm text-muted-foreground">正在加载作业…</p> : <TaskRows tasks={tasks} role={role} />}</section></div></main>;

  return <main className="h-full min-h-0 overflow-y-auto bg-canvas" data-testid="education-page"><div className="mx-auto flex w-full max-w-5xl flex-col gap-8 px-4 py-6 sm:px-6 lg:px-8 lg:py-8"><header className="border-b pb-5" style={{ borderColor: 'var(--color-border-muted)' }}><p className="font-mono text-xs" style={{ color: 'var(--color-text-tertiary)' }}>MY LEARNING</p><h1 className="title-font mt-2 text-2xl font-semibold" style={{ color: 'var(--color-text-primary)' }}>我的学习</h1><p className="mt-1 text-sm" style={{ color: 'var(--color-text-secondary)' }}>继续阅读已分配教材，并完成章节知识检查。</p></header><section aria-label="已分配教材" className="border-t" style={{ borderColor: 'var(--color-border-muted)' }}>{learningAssignments.isLoading ? <p className="py-8 text-sm text-muted-foreground">正在加载学习材料…</p> : (learningAssignments.data ?? []).length === 0 ? <p className="py-8 text-sm text-muted-foreground">暂未分配教材。</p> : (learningAssignments.data ?? []).map((assignment) => <article key={assignment.assignment_id} className="grid gap-3 border-b py-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center" style={{ borderColor: 'var(--color-border-muted)' }}><div><h2 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>{assignment.textbook_title}</h2><p className="mt-1 text-sm" style={{ color: 'var(--color-text-secondary)' }}>v{assignment.version_sequence} · {assignment.completed_chapter_count}/{assignment.chapter_count} 章已学习</p></div><Link to={`/education/learn/${assignment.assignment_id}/`}><Button size="sm">继续学习</Button></Link></article>)}</section><section aria-label="作业列表" className="border-t" style={{ borderColor: 'var(--color-border-muted)' }}><h2 className="py-4 text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>我的作业</h2>{tasksQuery.isLoading ? <p className="pb-6 text-sm text-muted-foreground">正在加载作业…</p> : <TaskRows tasks={tasks} role={role} />}</section></div></main>;
}
