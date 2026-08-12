import { useMemo, useState } from 'react';
import { ArrowLeft, BookOpen, FileCog, Play, RotateCcw, Send, Upload } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { useEducationMembers, useParentLearningRecords, useParentLearningTranscript, useTextbook, useTextbookMutations } from './queries';
import { uploadEducationAsset } from './api';
import type { TextbookVersion, TextbookVersionStatus } from './types';

const statusLabels: Record<TextbookVersionStatus, string> = { draft: '草稿', processing: '加工中', review: '待审阅', published: '已发布', failed: '加工失败' };

function StartProcessingDialog({ textbookId }: { textbookId: string }) {
  const [file, setFile] = useState<File | null>(null);
  const [open, setOpen] = useState(false);
  const mutations = useTextbookMutations();
  const submit = async () => {
    if (!file) return;
    const asset = await uploadEducationAsset(file);
    await mutations.start.mutateAsync({ textbookId, sourceAssetIds: [asset.asset_id] });
    setFile(null);
    setOpen(false);
  };
  return <Dialog open={open} onOpenChange={setOpen}><DialogTrigger asChild><Button><Upload className="mr-2 size-4" aria-hidden="true" />开始加工</Button></DialogTrigger><DialogContent variant="centered" className="max-w-md"><DialogHeader><DialogTitle>选择教材资料</DialogTitle></DialogHeader><div className="grid gap-4"><label className="grid gap-1.5 text-sm font-medium">教材文件<Input type="file" accept="application/pdf,image/jpeg,image/png,image/webp" onChange={(event) => setFile(event.target.files?.[0] ?? null)} /></label><DialogFooter><Button onClick={() => void submit()} disabled={!file || mutations.start.isPending}>{mutations.start.isPending ? '正在创建任务' : '开始加工'}</Button></DialogFooter></div></DialogContent></Dialog>;
}

function AssignDialog({ publicationId }: { publicationId: string }) {
  const [studentUserId, setStudentUserId] = useState('');
  const [open, setOpen] = useState(false);
  const members = useEducationMembers(true).data ?? [];
  const students = members.filter((member) => member.role === 'student');
  const mutations = useTextbookMutations();
  const assign = async () => { await mutations.assign.mutateAsync({ publicationId, studentUserId }); setOpen(false); };
  return <Dialog open={open} onOpenChange={setOpen}><DialogTrigger asChild><Button size="sm" variant="outline"><Send className="mr-2 size-4" aria-hidden="true" />分配学生</Button></DialogTrigger><DialogContent variant="centered" className="max-w-md"><DialogHeader><DialogTitle>分配已发布教材</DialogTitle></DialogHeader><div className="grid gap-4"><label className="grid gap-1.5 text-sm font-medium">学生<select value={studentUserId} onChange={(event) => setStudentUserId(event.target.value)} className="h-10 border border-input bg-background px-3 text-sm"><option value="">选择学生</option>{students.map((student) => <option key={student.user_id} value={student.user_id}>{student.name}</option>)}</select></label><DialogFooter><Button onClick={() => void assign()} disabled={!studentUserId || mutations.assign.isPending}>分配教材</Button></DialogFooter></div></DialogContent></Dialog>;
}

function AssignmentRecords({ assignmentId, studentName }: { assignmentId: string; studentName: string }) {
  const [open, setOpen] = useState(false);
  const records = useParentLearningRecords(assignmentId, open);
  const transcript = useParentLearningTranscript(assignmentId, open);
  return <Dialog open={open} onOpenChange={setOpen}><DialogTrigger asChild><Button size="sm" variant="ghost">查看记录：{studentName}</Button></DialogTrigger><DialogContent variant="centered" className="max-w-2xl"><DialogHeader><DialogTitle>{studentName}的学习记录</DialogTitle></DialogHeader><div className="border-t" style={{ borderColor: 'var(--color-border-muted)' }}>{records.isLoading ? <p className="py-6 text-sm text-muted-foreground">正在加载记录…</p> : (records.data?.records ?? []).length === 0 ? <p className="py-6 text-sm text-muted-foreground">尚无学习记录。</p> : records.data!.records.map((record) => <div key={record.chapter_id} className="grid grid-cols-[minmax(0,1fr)_auto] gap-4 border-b py-3 text-sm" style={{ borderColor: 'var(--color-border-muted)' }}><span style={{ color: 'var(--color-text-primary)' }}>{record.chapter_title}</span><span className="font-mono text-xs" style={{ color: 'var(--color-text-secondary)' }}>{record.status} · {record.correct_count}/{record.answer_count}</span></div>)}</div><div className="mt-6 border-t pt-4" style={{ borderColor: 'var(--color-border-muted)' }}><h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>学习问答记录</h3>{transcript.isLoading ? <p className="py-4 text-sm text-muted-foreground">正在加载问答…</p> : (transcript.data?.messages ?? []).length === 0 ? <p className="py-4 text-sm" style={{ color: 'var(--color-text-secondary)' }}>尚无学习问答。</p> : <div className="mt-3 grid max-h-80 gap-3 overflow-y-auto">{transcript.data!.messages.map((message, index) => <div key={`${message.timestamp ?? index}-${index}`} className="border-l-2 pl-3 text-sm leading-6" style={{ borderColor: 'var(--color-border-muted)', color: 'var(--color-text-secondary)' }}><p className="font-mono text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>{message.role === 'user' ? studentName : '学习助手'}</p><p>{message.content}</p></div>)}</div>}</div></DialogContent></Dialog>;
}

function VersionPanel({ textbookId, version }: { textbookId: string; version: TextbookVersion }) {
  const mutations = useTextbookMutations();
  const canRun = version.processing_job_status === 'queued' && Boolean(version.processing_job_id);
  const canRetry = version.status === 'failed' && version.processing_job_status === 'failed' && Boolean(version.processing_job_id);
  const canPublish = version.status === 'review';
  return <section className="border" style={{ borderColor: 'var(--color-border-muted)' }}><div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3" style={{ borderColor: 'var(--color-border-muted)' }}><div><h2 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>v{version.sequence}</h2><p className="mt-1 font-mono text-xs" style={{ color: 'var(--color-text-tertiary)' }}>{version.extractor_name ?? '等待加工'} {version.extractor_version ? `/${version.extractor_version}` : ''}</p></div><div className="flex flex-wrap items-center gap-2"><span className="border px-2 py-1 font-mono text-[11px]" style={{ borderColor: 'var(--color-border-muted)', color: 'var(--color-text-secondary)' }}>{statusLabels[version.status]}</span>{canRun && <Button size="sm" variant="outline" onClick={() => void mutations.run.mutateAsync(version.processing_job_id!)} disabled={mutations.run.isPending}><Play className="mr-2 size-4" aria-hidden="true" />执行本地加工</Button>}{canRetry && <Button size="sm" variant="outline" onClick={() => void mutations.retry.mutateAsync(version.processing_job_id!)} disabled={mutations.retry.isPending}><RotateCcw className="mr-2 size-4" aria-hidden="true" />重试加工</Button>}{canPublish && <Button size="sm" onClick={() => void mutations.publish.mutateAsync({ textbookId, versionId: version.version_id })} disabled={mutations.publish.isPending}>发布版本</Button>}{version.publication_id && <AssignDialog publicationId={version.publication_id} />}</div></div>{version.processing_error && <p className="border-b px-4 py-3 text-sm" role="alert" style={{ borderColor: 'var(--color-border-muted)', color: 'var(--color-danger)' }}>{version.processing_error}</p>}<div className="grid divide-y" style={{ borderColor: 'var(--color-border-muted)' }}>{version.chapters.map((chapter) => <article key={chapter.chapter_id} className="px-4 py-4"><div className="flex items-center gap-2"><BookOpen className="size-4" style={{ color: 'var(--color-text-secondary)' }} /><h3 className="text-sm font-medium" style={{ color: 'var(--color-text-primary)' }}>{chapter.position}. {chapter.title}</h3></div><p className="mt-2 whitespace-pre-line text-sm leading-6" style={{ color: 'var(--color-text-secondary)' }}>{chapter.teaching_material}</p><p className="mt-3 font-mono text-xs" style={{ color: 'var(--color-text-tertiary)' }}>{chapter.questions.length} 道默认知识检查</p></article>)}</div>{version.assignments.length > 0 && <div className="border-t px-4 py-3" style={{ borderColor: 'var(--color-border-muted)' }}><p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>已分配</p><div className="mt-2 flex flex-wrap gap-2">{version.assignments.map((assignment) => <AssignmentRecords key={assignment.assignment_id} assignmentId={assignment.assignment_id} studentName={assignment.student_name ?? assignment.student_user_id} />)}</div></div>}</section>;
}

export default function TextbookDetailPage() {
  const { textbookId } = useParams();
  const textbook = useTextbook(textbookId);
  const data = textbook.data;
  const versions = useMemo(() => data?.versions ?? [], [data?.versions]);
  if (textbook.isLoading) return <main className="h-full overflow-y-auto bg-canvas"><p className="p-8 text-sm text-muted-foreground">正在加载教材…</p></main>;
  if (!data) return <main className="h-full overflow-y-auto bg-canvas"><p className="p-8 text-sm text-muted-foreground">教材不存在或无权访问。</p></main>;
  return <main className="h-full min-h-0 overflow-y-auto bg-canvas" data-testid="textbook-detail-page"><div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 py-6 sm:px-6 lg:px-8 lg:py-8"><header className="border-b pb-5" style={{ borderColor: 'var(--color-border-muted)' }}><Link to="/education" className="inline-flex items-center gap-2 text-sm" style={{ color: 'var(--color-text-secondary)' }}><ArrowLeft className="size-4" />家庭教材库</Link><div className="mt-4 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between"><div><p className="font-mono text-xs" style={{ color: 'var(--color-text-tertiary)' }}>TEXTBOOK</p><h1 className="title-font mt-2 text-2xl font-semibold" style={{ color: 'var(--color-text-primary)' }}>{data.title}</h1><p className="mt-1 text-sm" style={{ color: 'var(--color-text-secondary)' }}>候选版本需经审阅与显式发布，学生不会自动切换版本。</p></div><StartProcessingDialog textbookId={data.textbook_id} /></div></header><section aria-label="教材版本" className="grid gap-4">{versions.length === 0 ? <div className="border py-12 text-center" style={{ borderColor: 'var(--color-border-muted)' }}><FileCog className="mx-auto size-6" style={{ color: 'var(--color-text-tertiary)' }} /><p className="mt-3 text-sm" style={{ color: 'var(--color-text-secondary)' }}>上传一份资料后开始加工。</p></div> : versions.map((version) => <VersionPanel key={version.version_id} textbookId={data.textbook_id} version={version} />)}</section></div></main>;
}
