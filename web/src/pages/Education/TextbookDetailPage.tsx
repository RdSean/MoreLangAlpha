import { useMemo, useState } from 'react';
import { ArrowLeft, BookOpen, ExternalLink, FileCog, Play, RotateCcw, Send, Upload } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { useToast } from '@/components/ui/use-toast';
import { getEducationAssetDownloadUrl, uploadEducationAsset } from './api';
import { useEducationAssets, useEducationMembers, useParentLearningRecords, useParentLearningTranscript, useTextbook, useTextbookMutations } from './queries';
import type { EducationAsset, TextbookVersion, TextbookVersionStatus } from './types';

const statusLabels: Record<TextbookVersionStatus, string> = { draft: '草稿', processing: '加工中', review: '待审阅', published: '已发布', failed: '加工失败' };
type ReviewTab = 'overview' | 'contents' | 'teaching' | 'students';

function formatSize(size: number) {
  return size >= 1024 * 1024 ? `${(size / (1024 * 1024)).toFixed(1)} MB` : `${Math.max(1, Math.ceil(size / 1024))} KB`;
}

function userMessage(error: unknown, fallback: string) {
  return error instanceof Error && error.message ? error.message : fallback;
}

function StartProcessingDialog({ textbookId }: { textbookId: string }) {
  const [file, setFile] = useState<File | null>(null);
  const [selectedAssetIds, setSelectedAssetIds] = useState<string[]>([]);
  const [open, setOpen] = useState(false);
  const assets = useEducationAssets();
  const mutations = useTextbookMutations();
  const { toast } = useToast();
  const toggleAsset = (assetId: string) => setSelectedAssetIds((current) => current.includes(assetId) ? current.filter((id) => id !== assetId) : [...current, assetId]);
  const submit = async () => {
    try {
      const upload = file ? await uploadEducationAsset(file) : null;
      const sourceAssetIds = [...new Set([...selectedAssetIds, ...(upload ? [upload.asset_id] : [])])];
      if (sourceAssetIds.length === 0) return;
      await mutations.start.mutateAsync({ textbookId, sourceAssetIds });
      setFile(null);
      setSelectedAssetIds([]);
      setOpen(false);
    } catch (error) {
      toast({ variant: 'destructive', title: '无法创建加工任务', description: userMessage(error, '请检查资料并重试。') });
    }
  };
  const canSubmit = selectedAssetIds.length > 0 || Boolean(file);

  return <Dialog open={open} onOpenChange={setOpen}><DialogTrigger asChild><Button><Upload className="mr-2 size-4" aria-hidden="true" />开始加工</Button></DialogTrigger><DialogContent variant="centered" className="max-w-lg"><DialogHeader><DialogTitle>选择教材资料</DialogTitle></DialogHeader><div className="grid gap-5"><section><h3 className="text-sm font-medium" style={{ color: 'var(--color-text-primary)' }}>已上传资料</h3>{assets.isLoading ? <p className="mt-2 text-sm text-muted-foreground">正在加载资料…</p> : (assets.data ?? []).length === 0 ? <p className="mt-2 text-sm" style={{ color: 'var(--color-text-secondary)' }}>暂无可选资料。</p> : <div className="mt-2 divide-y border" style={{ borderColor: 'var(--color-border-muted)' }}>{assets.data!.map((asset) => <label key={asset.asset_id} className="flex min-h-11 cursor-pointer items-center gap-3 px-3 py-2 text-sm"><input type="checkbox" aria-label={asset.original_filename} checked={selectedAssetIds.includes(asset.asset_id)} onChange={() => toggleAsset(asset.asset_id)} /><span className="min-w-0 flex-1 truncate" style={{ color: 'var(--color-text-primary)' }}>{asset.original_filename}</span><span className="font-mono text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>{formatSize(asset.size_bytes)}</span></label>)}</div>}</section><label className="grid gap-1.5 text-sm font-medium">另行上传资料（可选）<Input type="file" accept="application/pdf,image/jpeg,image/png,image/webp" onChange={(event) => setFile(event.target.files?.[0] ?? null)} /></label><DialogFooter><Button onClick={() => void submit()} disabled={!canSubmit || mutations.start.isPending}>{mutations.start.isPending ? '正在创建任务' : '创建加工任务'}</Button></DialogFooter></div></DialogContent></Dialog>;
}

function AssignDialog({ publicationId }: { publicationId: string }) {
  const [studentUserId, setStudentUserId] = useState('');
  const [open, setOpen] = useState(false);
  const members = useEducationMembers(true).data ?? [];
  const students = members.filter((member) => member.role === 'student');
  const mutations = useTextbookMutations();
  const { toast } = useToast();
  const assign = async () => {
    try {
      await mutations.assign.mutateAsync({ publicationId, studentUserId });
      setOpen(false);
    } catch (error) {
      toast({ variant: 'destructive', title: '无法分配教材', description: userMessage(error, '请稍后重试。') });
    }
  };
  return <Dialog open={open} onOpenChange={setOpen}><DialogTrigger asChild><Button size="sm" variant="outline"><Send className="mr-2 size-4" aria-hidden="true" />分配学生</Button></DialogTrigger><DialogContent variant="centered" className="max-w-md"><DialogHeader><DialogTitle>分配已发布教材</DialogTitle></DialogHeader><div className="grid gap-4"><label className="grid gap-1.5 text-sm font-medium">学生<select value={studentUserId} onChange={(event) => setStudentUserId(event.target.value)} className="h-10 border border-input bg-background px-3 text-sm"><option value="">选择学生</option>{students.map((student) => <option key={student.user_id} value={student.user_id}>{student.name}</option>)}</select></label><DialogFooter><Button onClick={() => void assign()} disabled={!studentUserId || mutations.assign.isPending}>{mutations.assign.isPending ? '正在分配' : '分配教材'}</Button></DialogFooter></div></DialogContent></Dialog>;
}

function AssignmentRecords({ assignmentId, studentName }: { assignmentId: string; studentName: string }) {
  const [open, setOpen] = useState(false);
  const records = useParentLearningRecords(assignmentId, open);
  const transcript = useParentLearningTranscript(assignmentId, open);
  return <Dialog open={open} onOpenChange={setOpen}><DialogTrigger asChild><Button size="sm" variant="ghost">查看记录：{studentName}</Button></DialogTrigger><DialogContent variant="centered" className="max-w-2xl"><DialogHeader><DialogTitle>{studentName}的学习记录</DialogTitle></DialogHeader><div className="border-t" style={{ borderColor: 'var(--color-border-muted)' }}>{records.isLoading ? <p className="py-6 text-sm text-muted-foreground">正在加载记录…</p> : (records.data?.records ?? []).length === 0 ? <p className="py-6 text-sm text-muted-foreground">尚无学习记录。</p> : records.data!.records.map((record) => <div key={record.chapter_id} className="grid grid-cols-[minmax(0,1fr)_auto] gap-4 border-b py-3 text-sm" style={{ borderColor: 'var(--color-border-muted)' }}><span style={{ color: 'var(--color-text-primary)' }}>{record.chapter_title}</span><span className="font-mono text-xs" style={{ color: 'var(--color-text-secondary)' }}>{record.status} · {record.correct_count}/{record.answer_count}</span></div>)}</div><div className="mt-6 border-t pt-4" style={{ borderColor: 'var(--color-border-muted)' }}><h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>学习问答记录</h3>{transcript.isLoading ? <p className="py-4 text-sm text-muted-foreground">正在加载问答…</p> : (transcript.data?.messages ?? []).length === 0 ? <p className="py-4 text-sm" style={{ color: 'var(--color-text-secondary)' }}>尚无学习问答。</p> : <div className="mt-3 grid max-h-80 gap-3 overflow-y-auto">{transcript.data!.messages.map((message, index) => <div key={`${message.timestamp ?? index}-${index}`} className="border-l-2 pl-3 text-sm leading-6" style={{ borderColor: 'var(--color-border-muted)', color: 'var(--color-text-secondary)' }}><p className="font-mono text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>{message.role === 'user' ? studentName : '学习助手'}</p><p>{message.content}</p></div>)}</div>}</div></DialogContent></Dialog>;
}

function SourceOpenButton({ asset }: { asset: EducationAsset }) {
  const [opening, setOpening] = useState(false);
  const { toast } = useToast();
  const open = async () => {
    setOpening(true);
    try {
      const url = await getEducationAssetDownloadUrl(asset.asset_id);
      window.open(url, '_blank', 'noopener,noreferrer');
    } catch (error) {
      toast({ variant: 'destructive', title: '无法打开来源文件', description: userMessage(error, '请稍后重试。') });
    } finally {
      setOpening(false);
    }
  };
  return <Button size="sm" variant="ghost" onClick={() => void open()} disabled={opening} aria-label={`打开 ${asset.original_filename}`}><ExternalLink className="mr-2 size-4" aria-hidden="true" />{opening ? '正在打开' : '打开'}</Button>;
}

function VersionPanel({ textbookId, version }: { textbookId: string; version: TextbookVersion }) {
  const [tab, setTab] = useState<ReviewTab>('overview');
  const mutations = useTextbookMutations();
  const { toast } = useToast();
  const canRun = version.processing_job_status === 'queued' && Boolean(version.processing_job_id);
  const canRetry = version.status === 'failed' && version.processing_job_status === 'failed' && Boolean(version.processing_job_id);
  const canPublish = version.status === 'review';
  const act = async (action: () => Promise<unknown>, failureTitle: string) => {
    try {
      await action();
    } catch (error) {
      toast({ variant: 'destructive', title: failureTitle, description: userMessage(error, '请稍后重试。') });
    }
  };
  const tabs: Array<{ id: ReviewTab; label: string }> = [{ id: 'overview', label: '概览' }, { id: 'contents', label: '内容' }, { id: 'teaching', label: '教学' }, { id: 'students', label: '学生' }];
  return <section className="border" style={{ borderColor: 'var(--color-border-muted)' }}><div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3" style={{ borderColor: 'var(--color-border-muted)' }}><div><h2 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>v{version.sequence}</h2><p className="mt-1 font-mono text-xs" style={{ color: 'var(--color-text-tertiary)' }}>{version.extractor_name ?? '等待加工'} {version.extractor_version ? `/${version.extractor_version}` : ''}</p></div><div className="flex flex-wrap items-center gap-2"><span className="border px-2 py-1 font-mono text-[11px]" style={{ borderColor: 'var(--color-border-muted)', color: 'var(--color-text-secondary)' }}>{statusLabels[version.status]}</span>{canRun && <Button size="sm" variant="outline" onClick={() => void act(() => mutations.run.mutateAsync(version.processing_job_id!), '无法执行加工')} disabled={mutations.run.isPending}><Play className="mr-2 size-4" aria-hidden="true" />执行本地加工</Button>}{canRetry && <Button size="sm" variant="outline" onClick={() => void act(() => mutations.retry.mutateAsync(version.processing_job_id!), '无法重试加工')} disabled={mutations.retry.isPending}><RotateCcw className="mr-2 size-4" aria-hidden="true" />重试加工</Button>}{canPublish && <Button size="sm" onClick={() => void act(() => mutations.publish.mutateAsync({ textbookId, versionId: version.version_id }), '无法发布版本')} disabled={mutations.publish.isPending}>{mutations.publish.isPending ? '正在发布' : '发布版本'}</Button>}{version.publication_id && <AssignDialog publicationId={version.publication_id} />}</div></div>{version.processing_error && <p className="border-b px-4 py-3 text-sm" role="alert" style={{ borderColor: 'var(--color-border-muted)', color: 'var(--color-danger)' }}>{version.processing_error}</p>}<div className="flex flex-wrap gap-1 border-b px-4 pt-2" role="tablist" aria-label={`版本 ${version.sequence} 审阅`} style={{ borderColor: 'var(--color-border-muted)' }}>{tabs.map((item) => <Button key={item.id} type="button" variant={tab === item.id ? 'secondary' : 'ghost'} size="sm" role="tab" aria-selected={tab === item.id} onClick={() => setTab(item.id)}>{item.label}</Button>)}</div><div className="p-4">{tab === 'overview' && <div className="grid gap-4"><section><h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>冻结来源</h3>{version.sources.length === 0 ? <p className="mt-2 text-sm" style={{ color: 'var(--color-text-secondary)' }}>加工任务尚未锁定来源。</p> : <div className="mt-2 divide-y border" style={{ borderColor: 'var(--color-border-muted)' }}>{version.sources.map((source) => <div key={source.asset_id} className="flex flex-wrap items-center justify-between gap-3 px-3 py-2"><div><p className="text-sm" style={{ color: 'var(--color-text-primary)' }}>{source.original_filename}</p><p className="font-mono text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>{source.content_type} · {formatSize(source.size_bytes)}</p></div><SourceOpenButton asset={source} /></div>)}</div>}</section><p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>共 {version.chapter_count} 章，审阅后才可发布给学生。</p></div>}{tab === 'contents' && <div className="grid divide-y border" style={{ borderColor: 'var(--color-border-muted)' }}>{version.chapters.map((chapter) => <article key={chapter.chapter_id} className="px-4 py-4"><div className="flex flex-wrap items-center gap-2"><BookOpen className="size-4" style={{ color: 'var(--color-text-secondary)' }} /><h3 className="text-sm font-medium" style={{ color: 'var(--color-text-primary)' }}>{chapter.position}. {chapter.title}</h3>{chapter.page_start != null && chapter.page_end != null && <span className="font-mono text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>第 {chapter.page_start}-{chapter.page_end} 页</span>}</div><div className="mt-3 whitespace-pre-wrap text-sm leading-6" style={{ color: 'var(--color-text-secondary)' }}>{chapter.markdown}</div></article>)}</div>}{tab === 'teaching' && <div className="grid divide-y border" style={{ borderColor: 'var(--color-border-muted)' }}>{version.chapters.map((chapter) => <article key={chapter.chapter_id} className="px-4 py-4"><h3 className="text-sm font-medium" style={{ color: 'var(--color-text-primary)' }}>{chapter.position}. {chapter.title}</h3><div className="mt-3 whitespace-pre-wrap text-sm leading-6" style={{ color: 'var(--color-text-secondary)' }}>{chapter.teaching_material}</div><div className="mt-4 grid gap-3">{chapter.questions.map((question) => <div key={question.question_id} className="border-l-2 pl-3 text-sm" style={{ borderColor: 'var(--color-border-muted)' }}><p style={{ color: 'var(--color-text-primary)' }}>{question.position}. {question.prompt}</p><p className="mt-1 font-mono text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>{question.knowledge_point}</p></div>)}</div></article>)}</div>}{tab === 'students' && <div>{version.assignments.length === 0 ? <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>发布后可分配给家庭学生。</p> : <div className="flex flex-wrap gap-2">{version.assignments.map((assignment) => <AssignmentRecords key={assignment.assignment_id} assignmentId={assignment.assignment_id} studentName={assignment.student_name ?? assignment.student_user_id} />)}</div>}</div>}</div></section>;
}

export default function TextbookDetailPage() {
  const { textbookId } = useParams();
  const textbook = useTextbook(textbookId);
  const data = textbook.data;
  const versions = useMemo(() => data?.versions ?? [], [data?.versions]);
  if (textbook.isLoading) return <main className="h-full overflow-y-auto bg-canvas"><p className="p-8 text-sm text-muted-foreground">正在加载教材…</p></main>;
  if (!data) return <main className="h-full overflow-y-auto bg-canvas"><p className="p-8 text-sm text-muted-foreground">教材不存在或无权访问。</p></main>;
  const isUnprocessedDraft = versions.length === 0;
  return <main className="h-full min-h-0 overflow-y-auto bg-canvas" data-testid="textbook-detail-page"><div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 py-6 sm:px-6 lg:px-8 lg:py-8"><header className="border-b pb-5" style={{ borderColor: 'var(--color-border-muted)' }}><Link to="/education" className="inline-flex items-center gap-2 text-sm" style={{ color: 'var(--color-text-secondary)' }}><ArrowLeft className="size-4" />家庭教材库</Link><div className="mt-4 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between"><div><p className="font-mono text-xs" style={{ color: 'var(--color-text-tertiary)' }}>TEXTBOOK</p><h1 className="title-font mt-2 text-2xl font-semibold" style={{ color: 'var(--color-text-primary)' }}>{data.title}</h1><p className="mt-1 text-sm" style={{ color: 'var(--color-text-secondary)' }}>候选版本需经审阅与显式发布，学生不会自动切换版本。</p></div>{!isUnprocessedDraft && <StartProcessingDialog textbookId={data.textbook_id} />}</div></header><section aria-label="教材版本" className="grid gap-4">{isUnprocessedDraft ? <div className="border p-6" style={{ borderColor: 'var(--color-border-muted)' }}><FileCog className="size-5" style={{ color: 'var(--color-text-tertiary)' }} /><h2 className="mt-4 text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>下一步：添加教材资料</h2><p className="mt-2 max-w-xl text-sm" style={{ color: 'var(--color-text-secondary)' }}>选择已有资料或上传一份资料，创建加工任务后即可执行加工、审阅、发布并分配给学生。</p><div className="mt-4"><StartProcessingDialog textbookId={data.textbook_id} /></div></div> : versions.map((version) => <VersionPanel key={version.version_id} textbookId={data.textbook_id} version={version} />)}</section></div></main>;
}
