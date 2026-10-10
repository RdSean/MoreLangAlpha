import { useEffect, useMemo, useRef, useState } from 'react';
import { CheckCircle2, ClipboardPlus, RotateCcw, Send, XCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { createDateFormatter } from '@/lib/format';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { useAuth } from '@/contexts/AuthContext';
import { SubjectIcon } from '@/components/icons/SubjectIcon';
import { createRequestKeyTracker } from '@/pages/ChatAgent/hooks/utils/requestKey';
import { deleteEducationAsset, uploadEducationAsset } from './api';
import { useEducationHomeworkDictionaries, useEducationMembers, useEducationTaskMutations, useLearningAssignments } from './queries';
import EducationNotebook from './EducationNotebook';
import HomeworkTaskDetail from './HomeworkTaskDetail';
import { createCompletionSound } from './completionSound';
import type { CreateEducationTaskInput, EducationHomeworkDictionaries, EducationMember, EducationTask, EducationTaskStatus } from './types';

const statusLabels: Record<EducationTaskStatus, string> = {
  open: '待完成',
  completed: '已完成',
  cancelled: '已取消',
};

function householdWallClockToIso(value: string, timeZone: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value);
  if (!match) throw new Error('截止时间无效。');
  const [year, month, day, hour, minute] = match.slice(1).map(Number);
  const wallClockUtc = Date.UTC(year, month - 1, day, hour, minute);
  const formatter = new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  });
  let instant = wallClockUtc;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const parts = Object.fromEntries(formatter.formatToParts(new Date(instant))
      .filter((part) => part.type !== 'literal')
      .map((part) => [part.type, Number(part.value)]));
    const localClockUtc = Date.UTC(parts.year, parts.month - 1, parts.day, parts.hour, parts.minute);
    instant = wallClockUtc - (localClockUtc - instant);
  }
  return new Date(instant).toISOString();
}

const maxEducationAttachments = 20;

function assertAttachmentLimit(files: File[]) {
  if (files.length > maxEducationAttachments) {
    throw new Error(`最多可上传 ${maxEducationAttachments} 份附件。`);
  }
}

type StagedAttachmentAttempt = {
  fingerprint: string;
  idempotencyKey: string;
  assetIds: string[];
};

async function uploadSelectedFiles(
  files: File[],
  stagingKey: string,
  assetIds: string[],
): Promise<string[]> {
  assertAttachmentLimit(files);
  for (let index = assetIds.length; index < files.length; index += 1) {
    const asset = await uploadEducationAsset(files[index], { stagingKey, stagingSlot: index });
    assetIds.push(asset.asset_id);
  }
  return assetIds;
}

async function cleanupStagedAssets(attempt: StagedAttachmentAttempt): Promise<boolean> {
  const results = await Promise.all(attempt.assetIds.map(async (assetId) => {
    try {
      await deleteEducationAsset(assetId);
      return true;
    } catch {
      return false;
    }
  }));
  return results.every(Boolean);
}

function isDefinitiveRequestError(error: unknown): boolean {
  const response = asRecord(error)?.response;
  const status = asRecord(response)?.status;
  return typeof status === 'number' && status >= 400 && status < 500 && status !== 409;
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
  idempotencyKey: string;
  materialAssetIds: string[];
};

const weeklyDayOptions = [
  [1, '周一'], [2, '周二'], [3, '周三'], [4, '周四'], [5, '周五'], [6, '周六'], [7, '周日'],
] as const;

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null ? value as Record<string, unknown> : null;
}

function readableError(error: unknown) {
  const response = asRecord(error)?.response;
  const detail = asRecord(asRecord(response)?.data)?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  return error instanceof Error ? error.message : '操作失败，请重试。';
}

function ChoiceGroup({
  label,
  value,
  options,
  onChange,
  colorForOption,
}: {
  label: string;
  value: string;
  options: Array<{ value: string; label: string }>;
  onChange: (value: string) => void;
  colorForOption?: (value: string) => string | undefined;
}) {
  return <fieldset className="grid gap-2">
    <legend className="text-sm font-medium">{label}</legend>
    <div className="flex flex-wrap gap-0" role="group" aria-label={label}>
      {options.map((option) => {
        const selected = option.value === value;
        const color = colorForOption?.(option.value);
        return <Button
          key={option.value}
          type="button"
          size="sm"
          variant={selected ? 'secondary' : 'outline'}
          className="rounded-none border-r-0 first:rounded-l-md last:border-r last:rounded-r-md"
          aria-pressed={selected}
          onClick={() => onChange(option.value)}
          style={{
            borderColor: selected ? (color ?? 'var(--color-text-primary)') : 'var(--color-border-default)',
            ...(selected ? { backgroundColor: color ?? 'var(--color-text-primary)', color: '#fff' } : {}),
          }}
        >{color && <SubjectIcon
          // The subject group is the only one that passes `colorForOption`,
          // and its option values are the dictionary's subject codes — so the
          // icon can be resolved from `option.value` directly. On a selected
          // button the icon sits on the subject's own colour, so it goes white
          // there and takes the subject colour otherwise.
          subject={option.value}
          color={selected ? '#fff' : color}
          size={22}
          className="mr-2"
        />}{option.label}</Button>;
      })}
    </div>
  </fieldset>;
}

export function CreateHomeworkPage() {
  const { member } = useAuth();
  const dictionariesQuery = useEducationHomeworkDictionaries();
  const membersQuery = useEducationMembers(member?.role === 'parent');
  const mutations = useEducationTaskMutations();
  const students = useMemo(() => (membersQuery.data ?? []).filter((item) => item.role === 'student'), [membersQuery.data]);

  if (member?.role !== 'parent') return <Navigate to="/education" replace />;
  const create = async ({ assignedStudentId, title, description, dueAt, subjectCode, typeCode, practiceSourceCode, frequency, weekdays, idempotencyKey, materialAssetIds }: ParentCreateInput) => {
    await mutations.create.mutateAsync({ idempotency_key: idempotencyKey, assigned_student_id: assignedStudentId, title, description, due_at: householdWallClockToIso(dueAt, dictionariesQuery.data?.timezone ?? 'UTC'), subject_code: subjectCode, type_code: typeCode, practice_source_code: practiceSourceCode, frequency, weekdays, material_asset_ids: materialAssetIds });
  };
  return <ParentCreateDialog page students={students} dictionaries={dictionariesQuery.data} onSubmit={create} isPending={mutations.create.isPending} />;
}

export function ParentCreateDialog({ students, dictionaries, onSubmit, isPending, page = false, open: controlledOpen, onOpenChange, initialDate }: {
  students: EducationMember[];
  dictionaries: EducationHomeworkDictionaries | undefined;
  onSubmit: (input: ParentCreateInput) => Promise<void>;
  isPending: boolean;
  page?: boolean;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  initialDate?: string;
}) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [assignedStudentId, setAssignedStudentId] = useState('');
  const [description, setDescription] = useState('');
  const [dueAt, setDueAt] = useState('');
  const [subjectCode, setSubjectCode] = useState('');
  const [typeCode, setTypeCode] = useState('');
  const [practiceSourceCode, setPracticeSourceCode] = useState('');
  const [frequency, setFrequency] = useState<CreateEducationTaskInput['frequency']>('once');
  const [weekdays, setWeekdays] = useState<number[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const requestKeyTracker = useRef(createRequestKeyTracker());
  const stagedAttempt = useRef<StagedAttachmentAttempt | null>(null);
  const subject = dictionaries?.subjects.find((item) => item.code === subjectCode);
  const selectedStudent = students.find((student) => student.user_id === assignedStudentId);
  const isDictionaryReady = Boolean(dictionaries);
  const hasStudentGrade = Boolean(selectedStudent?.grade_code);
  const gradeName = dictionaries?.grade_levels.find((grade) => grade.code === selectedStudent?.grade_code)?.name ?? '未设置年级';
  const isPractice = typeCode === 'practice';
  const needsWeekdaySelection = frequency === 'weekly';
  const householdTimezone = dictionaries?.timezone ?? 'UTC';
  const dialogOpen = controlledOpen ?? open;
  const changeOpen = (nextOpen: boolean) => { setOpen(nextOpen); onOpenChange?.(nextOpen); };

  useEffect(() => {
    if (controlledOpen && initialDate) setDueAt(`${initialDate}T20:00`);
  }, [controlledOpen, initialDate]);

  useEffect(() => {
    if (!dictionaries || students.length === 0) return;
    setAssignedStudentId((current) => current || students[0].user_id);
    setSubjectCode((current) => current || dictionaries.subjects.find((item) => item.code === 'math')?.code || dictionaries.subjects[0]?.code || '');
  }, [dictionaries, students]);

  useEffect(() => {
    if (!subject) return;
    setTypeCode((current) => current && subject.homework_types.some((item) => item.code === current)
      ? current
      : subject.homework_types.find((item) => item.code === 'practice')?.code || subject.homework_types[0]?.code || '');
  }, [subject]);

  useEffect(() => {
    if (!isPractice || !dictionaries) return;
    setPracticeSourceCode((current) => current || dictionaries.practice_sources.find((item) => item.code === 'homework')?.code || dictionaries.practice_sources[0]?.code || '');
  }, [dictionaries, isPractice]);

  const discardStagedAttempt = async () => {
    const attempt = stagedAttempt.current;
    if (!attempt) return true;
    const cleaned = await cleanupStagedAssets(attempt);
    if (cleaned) {
      stagedAttempt.current = null;
      requestKeyTracker.current.clear();
    }
    return cleaned;
  };
  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen && (isSubmitting || isPending)) return;
    if (!nextOpen) void discardStagedAttempt();
    changeOpen(nextOpen);
  };

  const updateFrequency = (nextFrequency: CreateEducationTaskInput['frequency']) => {
    setFrequency(nextFrequency);
    if (nextFrequency !== 'weekly') setWeekdays([]);
  };
  const toggleWeekday = (weekday: number) => {
    setWeekdays((current) => {
      const next = current.includes(weekday)
        ? current.filter((item) => item !== weekday)
        : [...current, weekday].sort((left, right) => left - right);
      return next;
    });
  };

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setIsSubmitting(true);
    setSubmitError(null);
    let attempt: StagedAttachmentAttempt | null = null;
    try {
      assertAttachmentLimit(files);
      const generatedTitle = [subject?.name, typeCode && subject?.homework_types.find((item) => item.code === typeCode)?.name].filter(Boolean).join('') || '家庭作业';
      const fingerprint = [assignedStudentId, generatedTitle, description, dueAt, subjectCode, typeCode, practiceSourceCode, frequency, ...weekdays.map(String), ...files.map((file) => `${file.name}:${file.size}:${file.lastModified}`)].join('\u0000');
      const idempotencyKey = requestKeyTracker.current.take(fingerprint);
      attempt = stagedAttempt.current;
      if (!attempt || attempt.fingerprint !== fingerprint || attempt.idempotencyKey !== idempotencyKey) {
        if (attempt && !(await discardStagedAttempt())) throw new Error('暂存附件回收失败，请再次尝试。');
        attempt = { fingerprint, idempotencyKey, assetIds: [] };
        stagedAttempt.current = attempt;
      }
      const materialAssetIds = await uploadSelectedFiles(files, idempotencyKey, attempt.assetIds);
      await onSubmit({
        assignedStudentId,
        title: generatedTitle,
        description,
        dueAt,
        subjectCode,
        typeCode,
        practiceSourceCode: isPractice ? practiceSourceCode : null,
        frequency,
        weekdays: needsWeekdaySelection ? weekdays : null,
        idempotencyKey,
        materialAssetIds,
      });
      stagedAttempt.current = null;
      requestKeyTracker.current.clear();
      if (page) navigate('/education');
      else {
        changeOpen(false);
        setDescription(''); setFiles([]); setWeekdays([]); setFrequency('once'); setDueAt('');
      }
    } catch (error) {
      if (attempt && isDefinitiveRequestError(error)) {
        await discardStagedAttempt();
      }
      setSubmitError(readableError(error));
    } finally {
      setIsSubmitting(false);
    }
  };

  const form = <form className="grid gap-5" onSubmit={(event) => void submit(event)}>
        <ChoiceGroup label="学生" value={assignedStudentId} options={students.map((student) => ({ value: student.user_id, label: student.name }))} onChange={setAssignedStudentId} />
        {selectedStudent && !isDictionaryReady && <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>正在加载作业字典…</p>}
        {selectedStudent && isDictionaryReady && <p className="text-sm" style={{ color: hasStudentGrade ? 'var(--color-text-secondary)' : 'var(--color-loss)' }}>当前年级：{gradeName}</p>}
        {selectedStudent && isDictionaryReady && !hasStudentGrade && <p className="text-sm" style={{ color: 'var(--color-loss)' }}>请先在‘设置 &gt; 家庭账户’中为该学生设置当前年级。</p>}
        <ChoiceGroup label="科目" value={subjectCode} options={(dictionaries?.subjects ?? []).map((item) => ({ value: item.code, label: item.name }))} onChange={(value) => { setSubjectCode(value); setTypeCode(''); setPracticeSourceCode(''); }} colorForOption={(value) => dictionaries?.subjects.find((item) => item.code === value)?.color} />
        <ChoiceGroup label="作业类型" value={typeCode} options={(subject?.homework_types ?? []).map((item) => ({ value: item.code, label: item.name }))} onChange={(value) => { setTypeCode(value); setPracticeSourceCode(''); }} />
        {isPractice && <ChoiceGroup label="练习来源" value={practiceSourceCode} options={(dictionaries?.practice_sources ?? []).map((item) => ({ value: item.code, label: item.name }))} onChange={setPracticeSourceCode} />}
        <label className="grid gap-1.5 text-sm font-medium">说明<Textarea value={description} onChange={(event) => setDescription(event.target.value)} /></label>
        <label className="grid gap-1.5 text-sm font-medium"><span>截止时间</span><span className="text-xs font-normal" style={{ color: 'var(--color-text-secondary)' }}>家庭时区：{householdTimezone}</span><Input aria-label="截止时间" type="datetime-local" value={dueAt} onChange={(event) => setDueAt(event.target.value)} required /></label>
        <p className="text-xs text-muted-foreground">重复作业从创建当天开始，按所选频率安排至截止日期（含当天）；时间部分为每次作业的截止时刻。</p>
        <ChoiceGroup label="重复方式" value={frequency} options={[{ value: 'once', label: '一次' }, { value: 'daily', label: '每天' }, { value: 'weekdays', label: '工作日' }, { value: 'weekly', label: '每周指定日期' }]} onChange={(value) => updateFrequency(value as CreateEducationTaskInput['frequency'])} />
        {needsWeekdaySelection && <fieldset className="grid gap-2"><legend className="text-sm font-medium">每周日期</legend><div className="flex flex-wrap gap-x-4 gap-y-2">{weeklyDayOptions.map(([weekday, label]) => <label className="flex items-center gap-2 text-sm" key={weekday}><input type="checkbox" checked={weekdays.includes(weekday)} onChange={() => toggleWeekday(weekday)} />{label}</label>)}</div></fieldset>}
        <label className="grid gap-1.5 text-sm font-medium">材料附件<Input type="file" multiple accept="application/pdf,image/jpeg,image/png,image/webp" onChange={(event) => setFiles(Array.from(event.target.files ?? []))} />{files.length > 0 && <span className="text-xs font-normal" style={{ color: 'var(--color-text-secondary)' }}>已选择 {files.length} 份附件</span>}</label>
        {submitError && <p role="alert" className="text-sm" style={{ color: 'var(--color-loss)' }}>{submitError}</p>}
        <DialogFooter><Button type="submit" disabled={isSubmitting || isPending || !isDictionaryReady || !assignedStudentId || !hasStudentGrade || !subjectCode || !typeCode || (isPractice && !practiceSourceCode) || (needsWeekdaySelection && weekdays.length === 0)}>{isSubmitting || isPending ? '正在创建' : '创建作业'}</Button></DialogFooter>
  </form>;

  if (page) return <main className="h-full min-h-0 overflow-y-auto bg-canvas" data-testid="create-homework-page"><div className="mx-auto w-full max-w-3xl px-4 py-6 sm:px-6 lg:px-8 lg:py-10"><nav aria-label="面包屑" className="mb-8 flex items-center gap-2 text-sm" style={{ color: 'var(--color-text-secondary)' }}><Link to="/education" className="hover:underline">家庭作业</Link><span aria-hidden="true">/</span><span style={{ color: 'var(--color-text-primary)' }}>创建作业</span></nav><header className="mb-8 border-b pb-5" style={{ borderColor: 'var(--color-border-default)' }}><h1 className="title-font flex items-center gap-2 text-2xl font-semibold" style={{ color: 'var(--color-text-primary)' }}><ClipboardPlus className="size-5" aria-hidden="true" />创建作业</h1><p className="mt-2 text-sm" style={{ color: 'var(--color-text-secondary)' }}>分配给家庭中的学生，并设定完成时间。</p></header><section className="border bg-background p-5 sm:p-7" style={{ borderColor: 'var(--color-border-default)' }}>{form}</section></div></main>;

  return <Dialog open={dialogOpen} onOpenChange={handleOpenChange}>
    {controlledOpen === undefined && <DialogTrigger asChild><Button><ClipboardPlus className="mr-2 size-4" aria-hidden="true" />创建作业</Button></DialogTrigger>}
    <DialogContent variant="centered" className={controlledOpen === undefined ? 'max-w-lg' : 'left-auto right-0 top-0 h-dvh max-h-dvh max-w-xl translate-x-0 translate-y-0 content-start rounded-none border-y-0 border-r-0 data-[state=open]:slide-in-from-right data-[state=closed]:slide-out-to-right data-[state=open]:zoom-in-100 data-[state=closed]:zoom-out-100'} dismissible={!isSubmitting && !isPending} onEscapeKeyDown={(event) => { if (isSubmitting || isPending) event.preventDefault(); }} onPointerDownOutside={(event) => { if (isSubmitting || isPending) event.preventDefault(); }}>
      <DialogHeader><DialogTitle>创建作业</DialogTitle><DialogDescription>分配给家庭中的学生，并设定完成时间。</DialogDescription></DialogHeader>
      {form}
    </DialogContent>
  </Dialog>;
}

function TaskActions({ task, role, onCompleted }: { task: EducationTask; role: 'parent' | 'student'; onCompleted?: () => void }) {
  const mutations = useEducationTaskMutations();
  const [text, setText] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [checkInOpen, setCheckInOpen] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const requestKeyTracker = useRef(createRequestKeyTracker());
  const stagedAttempt = useRef<StagedAttachmentAttempt | null>(null);

  const discardStagedAttempt = async () => {
    const attempt = stagedAttempt.current;
    if (!attempt) return true;
    const cleaned = await cleanupStagedAssets(attempt);
    if (cleaned) {
      stagedAttempt.current = null;
      requestKeyTracker.current.clear();
    }
    return cleaned;
  };
  const handleCheckInOpenChange = (nextOpen: boolean) => {
    if (!nextOpen && isSubmitting) return;
    if (!nextOpen) void discardStagedAttempt();
    setCheckInOpen(nextOpen);
  };
  const handleDialogOpenChange = (nextOpen: boolean) => {
    if (!nextOpen && isSubmitting) return;
    if (!nextOpen) void discardStagedAttempt();
    setDialogOpen(nextOpen);
  };
  const preventCloseWhileSubmitting = (event: { preventDefault: () => void }) => {
    if (isSubmitting) event.preventDefault();
  };

  const submitWithAttachments = async (
    kind: 'check-in' | 'revision',
    submit: (idempotencyKey: string, assetIds: string[]) => Promise<void>,
  ) => {
    assertAttachmentLimit(files);
    const fingerprint = [kind, task.task_id, text, ...files.map((file) => `${file.name}:${file.size}:${file.lastModified}`)].join('\u0000');
    const idempotencyKey = requestKeyTracker.current.take(fingerprint);
    let attempt = stagedAttempt.current;
    if (!attempt || attempt.fingerprint !== fingerprint || attempt.idempotencyKey !== idempotencyKey) {
      if (attempt && !(await discardStagedAttempt())) throw new Error('暂存附件回收失败，请再次尝试。');
      attempt = { fingerprint, idempotencyKey, assetIds: [] };
      stagedAttempt.current = attempt;
    }
    try {
      const assetIds = await uploadSelectedFiles(files, idempotencyKey, attempt.assetIds);
      await submit(idempotencyKey, assetIds);
    } catch (error) {
      if (isDefinitiveRequestError(error)) {
        await discardStagedAttempt();
      }
      throw error;
    }
  };
  const runAction = async (action: () => Promise<void>) => {
    setIsSubmitting(true);
    setActionError(null);
    try {
      await action();
    } catch (error) {
      setActionError(readableError(error));
    } finally {
      setIsSubmitting(false);
    }
  };
  const resetSubmission = () => {
    requestKeyTracker.current.clear();
    stagedAttempt.current = null;
    setText('');
    setFiles([]);
  };
  const checkIn = () => {
    const sound = createCompletionSound();
    return runAction(async () => {
    await submitWithAttachments('check-in', async (idempotencyKey, assetIds) => {
      await mutations.checkIn.mutateAsync({ taskId: task.task_id, submission_text: text, idempotency_key: idempotencyKey, asset_ids: assetIds });
    });
    resetSubmission();
    sound.play();
    onCompleted?.();
    setCheckInOpen(false);
    }).finally(() => sound.close());
  };
  const appendRevision = () => runAction(async () => {
    await submitWithAttachments('revision', async (idempotencyKey, assetIds) => {
      await mutations.appendRevision.mutateAsync({ taskId: task.task_id, submission_text: text, idempotency_key: idempotencyKey, asset_ids: assetIds });
    });
    resetSubmission();
    setDialogOpen(false);
  });
  const review = (decision: 'feedback' | 'revision_requested') => runAction(async () => {
    await mutations.review.mutateAsync({ taskId: task.task_id, decision, feedbackText: text });
    setDialogOpen(false);
    setText('');
  });

  const errorMessage = actionError && <p role="alert" className="text-sm" style={{ color: 'var(--color-loss)' }}>{actionError}</p>;

  if (task.status === 'open') {
    return <Dialog open={checkInOpen} onOpenChange={handleCheckInOpenChange}>
      <DialogTrigger asChild><Button size="sm" className="min-h-11"><CheckCircle2 className="mr-2 size-4" aria-hidden="true" />完成打卡</Button></DialogTrigger>
      <DialogContent variant="centered" className="max-w-lg" onEscapeKeyDown={preventCloseWhileSubmitting} onPointerDownOutside={preventCloseWhileSubmitting}>
        <DialogHeader><DialogTitle>完成打卡</DialogTitle><DialogDescription>可直接确认完成，也可以补充文字和多份 PDF、图片附件。</DialogDescription></DialogHeader>
        <div className="grid gap-4">
          <Textarea value={text} onChange={(event) => setText(event.target.value)} placeholder="可选的完成说明" />
          <label className="grid gap-1.5 text-sm font-medium">附件<Input type="file" multiple accept="application/pdf,image/jpeg,image/png,image/webp" onChange={(event) => setFiles(Array.from(event.target.files ?? []))} /></label>
          {errorMessage}
          <DialogFooter><Button onClick={() => void checkIn()} disabled={isSubmitting || mutations.checkIn.isPending}>{isSubmitting || mutations.checkIn.isPending ? '正在打卡' : '确认打卡'}</Button></DialogFooter>
        </div>
      </DialogContent>
    </Dialog>;
  };
  if (role === 'student' && task.status === 'completed') {
    return <Dialog open={dialogOpen} onOpenChange={handleDialogOpenChange}><DialogTrigger asChild><Button size="sm" className="min-h-11" variant="outline"><Send className="mr-2 size-4" aria-hidden="true" />补充提交</Button></DialogTrigger><DialogContent variant="centered" className="max-w-lg" onEscapeKeyDown={preventCloseWhileSubmitting} onPointerDownOutside={preventCloseWhileSubmitting}><DialogHeader><DialogTitle>补充提交</DialogTitle><DialogDescription>可追加文字说明或多份 PDF、图片附件。</DialogDescription></DialogHeader><div className="grid gap-4"><Textarea value={text} onChange={(event) => setText(event.target.value)} placeholder="补充说明或修改内容" /><label className="grid gap-1.5 text-sm font-medium">附件<Input type="file" multiple accept="application/pdf,image/jpeg,image/png,image/webp" onChange={(event) => setFiles(Array.from(event.target.files ?? []))} /></label>{errorMessage}<DialogFooter><Button onClick={() => void appendRevision()} disabled={isSubmitting || mutations.appendRevision.isPending || (!text.trim() && files.length === 0)}>{isSubmitting || mutations.appendRevision.isPending ? '正在提交' : '提交补充'}</Button></DialogFooter></div></DialogContent></Dialog>;
  }
  if (role === 'parent' && task.status === 'completed') {
    return <Dialog open={dialogOpen} onOpenChange={handleDialogOpenChange}><DialogTrigger asChild><Button size="sm" className="min-h-11" variant="outline"><RotateCcw className="mr-2 size-4" aria-hidden="true" />反馈</Button></DialogTrigger><DialogContent variant="centered" className="max-w-lg"><DialogHeader><DialogTitle>作业反馈</DialogTitle><DialogDescription>反馈不会改变学生已完成状态。</DialogDescription></DialogHeader><div className="grid gap-4">{dialogOpen && <HomeworkTaskDetail taskId={task.task_id} />}<Textarea value={text} onChange={(event) => setText(event.target.value)} placeholder="写下修改建议或完成反馈" />{errorMessage}<DialogFooter><Button variant="outline" onClick={() => void review('revision_requested')} disabled={!text.trim() || mutations.review.isPending}>请求修改</Button><Button onClick={() => void review('feedback')} disabled={!text.trim() || mutations.review.isPending}>保存反馈</Button></DialogFooter></div></DialogContent></Dialog>;
  }
  return null;
}

function TaskRecordDialog({ task }: { task: EducationTask }) {
  const [open, setOpen] = useState(false);
  return <Dialog open={open} onOpenChange={setOpen}>
    <DialogTrigger asChild><Button size="sm" variant="ghost" className="min-h-11">查看记录</Button></DialogTrigger>
    <DialogContent variant="centered" className="max-w-lg">
      <DialogHeader><DialogTitle>{task.title}</DialogTitle><DialogDescription>查看作业材料、打卡提交和家长反馈。</DialogDescription></DialogHeader>
      {open && <HomeworkTaskDetail taskId={task.task_id} />}
    </DialogContent>
  </Dialog>;
}

function TaskRows({ tasks, role, timezone, onCompleted, members }: {
  tasks: EducationTask[]; role: 'parent' | 'student'; timezone: string;
  onCompleted?: () => void; members: EducationMember[];
}) {
  useTranslation();
  const formatDue = useMemo(() => createDateFormatter({ timeZone: timezone, month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }), [timezone]);
  const mutations = useEducationTaskMutations();
  const [cancelError, setCancelError] = useState<{ taskId: string; message: string } | null>(null);
  const cancelTask = async (taskId: string) => {
    setCancelError(null);
    try { await mutations.cancel.mutateAsync(taskId); }
    catch (error) { setCancelError({ taskId, message: readableError(error) }); }
  };
  return <>{tasks.map((task, index) => <article key={task.task_id} className="grid gap-3 border-b py-5 last:border-b-0">
    <div className="min-w-0">
      <div className="flex items-start gap-2">
        <span className="pt-0.5 font-mono text-xs text-muted-foreground">{String(index + 1).padStart(2, '0')}</span>
        <h4 className="min-w-0 break-words text-sm font-semibold">{task.title}</h4>
        {task.status === 'completed' && <CheckCircle2 className="size-4 shrink-0" aria-hidden="true" />}
        <span className="shrink-0 text-xs text-muted-foreground">{statusLabels[task.status]}</span>
      </div>
      {role === 'parent' && <p className="mt-1 text-xs text-muted-foreground">{members.find(member => member.user_id === task.assigned_student_id)?.name ?? '学生'}</p>}
      {task.description && <p className="mt-2 whitespace-pre-wrap break-words text-sm text-muted-foreground">{task.description}</p>}
      {task.latest_feedback_text && <p className="mt-2 whitespace-pre-wrap break-words border-l-2 pl-3 text-sm text-muted-foreground">反馈：{task.latest_feedback_text}</p>}
      <p className="mt-2 text-xs tabular-nums text-muted-foreground">截止 {formatDue(new Date(task.due_at))}</p>
      {cancelError?.taskId === task.task_id && <p role="alert" className="mt-2 text-sm" style={{ color: 'var(--color-loss)' }}>{cancelError.message}</p>}
    </div>
    <div className="flex flex-wrap items-center gap-1">
      <TaskRecordDialog task={task} />
      <TaskActions task={task} role={role} onCompleted={onCompleted} />
      {role === 'parent' && task.status === 'open' && <TooltipProvider><Tooltip><TooltipTrigger asChild>
        <Button size="icon" variant="ghost" className="min-h-11 min-w-11" aria-label="取消作业" disabled={mutations.cancel.isPending} onClick={() => void cancelTask(task.task_id)}><XCircle className="size-4" aria-hidden="true" /></Button>
      </TooltipTrigger><TooltipContent>取消作业</TooltipContent></Tooltip></TooltipProvider>}
    </div>
  </article>)}</>;
}

export default function EducationPage() {
  const { member } = useAuth();
  const dictionaries = useEducationHomeworkDictionaries();
  const role = member?.role ?? 'student';
  const members = useEducationMembers(role === 'parent');
  const assignments = useLearningAssignments(role === 'student');
  const mutations = useEducationTaskMutations();
  const [createOpen, setCreateOpen] = useState(false);
  const [createDate, setCreateDate] = useState('');
  const [completionMessage, setCompletionMessage] = useState('');
  const create = async (input: ParentCreateInput) => {
    await mutations.create.mutateAsync({ idempotency_key: input.idempotencyKey, assigned_student_id: input.assignedStudentId, title: input.title, description: input.description, due_at: householdWallClockToIso(input.dueAt, dictionaries.data?.timezone ?? 'UTC'), subject_code: input.subjectCode, type_code: input.typeCode, practice_source_code: input.practiceSourceCode, frequency: input.frequency, weekdays: input.weekdays, material_asset_ids: input.materialAssetIds });
  };
  return <main className="h-full min-h-0 overflow-y-auto bg-canvas lg:overflow-hidden" data-testid="education-page" style={{ backgroundColor: 'var(--color-bg-canvas)' }}>
    <div className="flex w-full flex-col gap-5 px-3 py-5 pb-24 sm:px-6 md:pb-8 lg:h-full lg:px-6 lg:py-5">
      <p role="status" className="sr-only">{completionMessage}</p>
      {dictionaries.isError ? <p role="alert">作业设置加载失败，请刷新重试。</p> : !dictionaries.data ? <p role="status" className="p-6 text-sm text-muted-foreground">正在加载作业…</p> : <EducationNotebook
        key={`${member?.user_id}:${dictionaries.data.timezone}`}
        role={role} dictionaries={dictionaries.data} members={members.data ?? []}
        onCreateTask={role === 'parent' ? date => { setCreateDate(date); setCreateOpen(true); } : undefined}
        renderTasks={tasks => <TaskRows tasks={tasks} role={role} timezone={dictionaries.data!.timezone} members={members.data ?? []} onCompleted={() => setCompletionMessage('打卡成功，获得 1 积分。')} />}
      >
      {role === 'student' && <section aria-label="已分配教材" className="rounded-lg border bg-card px-4 py-5 sm:px-6">
        <h2 className="text-base font-semibold">我的教材</h2>
        {assignments.isLoading ? <p className="py-4 text-sm text-muted-foreground">正在加载学习材料…</p> : assignments.isError ? <p role="alert" className="py-4 text-sm text-muted-foreground">学习材料加载失败，请刷新重试。</p> : !(assignments.data ?? []).length ? <p className="py-4 text-sm text-muted-foreground">暂未分配教材。</p> : assignments.data?.map(assignment => <article key={assignment.assignment_id} className="flex flex-wrap items-center justify-between gap-3 border-b py-4 last:border-0">
          <div><h3 className="text-sm font-semibold">{assignment.textbook_title}</h3><p className="mt-1 text-sm text-muted-foreground">{assignment.completed_knowledge_point_count}/{assignment.knowledge_point_count} 个知识点已学习</p></div>
          <Link to={`/education/learn/${assignment.assignment_id}`}><Button size="sm" className="min-h-11">继续学习</Button></Link>
        </article>)}
      </section>}
      </EducationNotebook>}
    </div>
    {role === 'parent' && <ParentCreateDialog students={(members.data ?? []).filter(item => item.role === 'student')} dictionaries={dictionaries.data} onSubmit={create} isPending={mutations.create.isPending} open={createOpen} onOpenChange={setCreateOpen} initialDate={createDate} />}
  </main>;
}
