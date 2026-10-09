import { useRef, useState } from 'react';
import type { KeyboardEvent, MouseEvent } from 'react';
import { Activity, BookOpenCheck, ImagePlus, Library, MoreHorizontal, Trash2, Users, X } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useDeleteTextbookCover, useDeleteManagedTextbook, useManagedTextbookLibrary, useUploadTextbookCover } from './queries';
import { educationErrorMessage } from './errorMessage';
import type { BookStructureStatus, ManagedTextbookSummary } from './types';
import { BookAssignmentDialog } from './components/BookAssignmentDialog';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';

const STRUCTURE_STATUS: Record<BookStructureStatus, string> = { queued: '等待结构分析', running: '正在分析结构', ready: '结构已就绪', failed: '结构分析失败' };
const MAX_COVER_BYTES = 10 * 1024 * 1024;
const COVER_TYPES = new Set(['image/png', 'image/jpeg', 'image/webp']);

function validateCoverFile(file: File): string | null {
  if (!COVER_TYPES.has(file.type)) return '封面仅支持 PNG、JPEG 或 WebP 图片。';
  if (file.size === 0 || file.size > MAX_COVER_BYTES) return '封面图片不能为空且不能超过 10 MB。';
  return null;
}

function TextbookCard({ textbook, canManage, onAssign, onDelete }: { textbook: ManagedTextbookSummary; canManage: boolean; onAssign: () => void; onDelete: () => void }) {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const upload = useUploadTextbookCover();
  const removeCover = useDeleteTextbookCover();
  const [coverError, setCoverError] = useState<string | null>(null);
  const chooseCover = async (file: File | undefined) => {
    if (!file) return;
    const validationError = validateCoverFile(file);
    if (validationError) { setCoverError(validationError); return; }
    setCoverError(null);
    try { await upload.mutateAsync({ textbookId: textbook.textbook_id, file }); }
    catch (error) { setCoverError(educationErrorMessage(error, '封面上传失败，请稍后重试。')); }
    finally { if (inputRef.current) inputRef.current.value = ''; }
  };
  const remove = async () => {
    setCoverError(null);
    try { await removeCover.mutateAsync(textbook.textbook_id); }
    catch (error) { setCoverError(educationErrorMessage(error, '封面移除失败，请稍后重试。')); }
  };
  const openFromCard = (event: MouseEvent<HTMLElement>) => {
    if ((event.target as HTMLElement).closest('a,button,input,[role="menuitem"]')) return;
    navigate(`/textbooks/${textbook.textbook_id}`);
  };
  const openFromKeyboard = (event: KeyboardEvent<HTMLElement>) => {
    if (event.target !== event.currentTarget || (event.key !== 'Enter' && event.key !== ' ')) return;
    event.preventDefault();
    navigate(`/textbooks/${textbook.textbook_id}`);
  };
  return (
    <article aria-label={textbook.title} tabIndex={0} onClick={openFromCard} onKeyDown={openFromKeyboard} className="group flex min-h-[25rem] cursor-pointer flex-col overflow-hidden rounded-lg border bg-card text-card-foreground shadow-sm transition-shadow hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" style={{ borderColor: 'var(--color-border-muted)' }}>
      <Link to={`/textbooks/${textbook.textbook_id}`} aria-label={`打开 ${textbook.title}`} className="block focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset">
        <div className="aspect-[3/4] w-full overflow-hidden bg-[var(--color-bg-hover)]">
          {textbook.cover_available ? <img src={`/api/v1/education/textbooks/${encodeURIComponent(textbook.textbook_id)}/cover`} alt={`${textbook.title}封面`} className="h-full w-full object-cover transition-transform duration-200 group-hover:scale-[1.02]" loading="lazy" /> : <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center text-muted-foreground"><BookOpenCheck className="size-10" aria-hidden="true" /><span className="text-sm">暂无封面</span></div>}
        </div>
      </Link>
      <div className="space-y-3 p-4">
        <Link to={`/textbooks/${textbook.textbook_id}`} className="block"><h2 className="line-clamp-2 min-h-12 text-base font-semibold leading-6 text-foreground">{textbook.title}</h2></Link>
        <div className="flex flex-wrap gap-2 text-xs text-muted-foreground"><span className="rounded-sm border px-2 py-1" style={{ borderColor: 'var(--color-border-muted)' }}>{STRUCTURE_STATUS[textbook.structure_status]}</span><span className="rounded-sm border px-2 py-1 tabular-nums" style={{ borderColor: 'var(--color-border-muted)' }}>讲义 {textbook.materials.ready} / {textbook.materials.total}</span></div>
        {textbook.current_job ? <Link to={`/textbooks/${textbook.textbook_id}?activity=${textbook.current_job.job_id}`} aria-label={`查看 ${textbook.title} 的处理活动`} className="inline-flex min-h-10 items-center gap-2 rounded-md px-2 text-sm text-muted-foreground hover:bg-[var(--color-bg-hover)] hover:text-foreground"><Activity className="size-4" aria-hidden="true" />{textbook.current_job.status === 'queued' ? '等待开始' : '处理中'}</Link> : <span className="text-sm text-muted-foreground">无进行中任务</span>}
      </div>
      <div className="mt-auto flex items-center justify-between gap-2 border-t px-3 py-2" style={{ borderColor: 'var(--color-border-muted)' }}>
        <Link to={`/textbooks/${textbook.textbook_id}`} className="text-sm font-medium text-muted-foreground hover:text-foreground">打开教材</Link>
        {canManage && <>
          <input ref={inputRef} type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" aria-label={`选择${textbook.title}封面`} onChange={(event) => void chooseCover(event.target.files?.[0])} />
          <DropdownMenu><DropdownMenuTrigger asChild><Button variant="ghost" size="icon" aria-label={`${textbook.title} 更多`} title="更多"><MoreHorizontal className="size-4" /></Button></DropdownMenuTrigger><DropdownMenuContent align="end">
            <DropdownMenuItem disabled={textbook.structure_status !== 'ready'} onSelect={onAssign}><Users className="size-4" />给学生使用</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => inputRef.current?.click()} disabled={upload.isPending}><ImagePlus className="size-4" />{textbook.cover_available ? '更换封面' : '设置封面'}</DropdownMenuItem>
            {textbook.cover_available && <DropdownMenuItem onSelect={() => void remove()} disabled={removeCover.isPending} className="text-destructive"><X className="size-4" />移除封面</DropdownMenuItem>}
            <DropdownMenuSeparator /><DropdownMenuItem onSelect={onDelete} disabled={Boolean(textbook.current_job) || upload.isPending || removeCover.isPending} className="text-destructive"><Trash2 className="size-4" />删除教材</DropdownMenuItem>
          </DropdownMenuContent></DropdownMenu>
        </>}
      </div>
      {coverError && <p role="alert" className="px-4 pb-3 text-xs text-destructive">{coverError}</p>}
    </article>
  );
}

export default function TextbooksPage() {
  const { member } = useAuth();
  const library = useManagedTextbookLibrary();
  const deletion = useDeleteManagedTextbook();
  const [target, setTarget] = useState<ManagedTextbookSummary | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [assignmentTarget, setAssignmentTarget] = useState<string | null>(null);
  const textbooks = library.data ?? [];
  const remove = async () => {
    if (!target || deletion.isPending) return;
    setDeleteError(null);
    try { await deletion.mutateAsync(target.textbook_id); setTarget(null); }
    catch (error) { setDeleteError(educationErrorMessage(error, '删除失败，请稍后重试。')); }
  };
  return <main className="h-full min-h-0 overflow-y-auto bg-canvas" data-testid="textbook-library-page"><div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
    <header className="flex flex-col gap-4 border-b pb-5 sm:flex-row sm:items-end sm:justify-between" style={{ borderColor: 'var(--color-border-muted)' }}><div><h1 className="text-2xl font-semibold text-foreground">教材</h1><p className="mt-1 text-sm text-muted-foreground">阅读原文与讲义，生成内容和查看处理活动都在教材工作台完成。</p></div><Link to="/documents?useAsTextbook=1" className="inline-flex min-h-10 self-start items-center justify-center rounded-md bg-[var(--color-btn-primary-bg)] px-4 py-2 text-sm font-medium text-[var(--color-btn-primary-text)] hover:opacity-90 sm:self-auto"><Library className="mr-2 size-4" aria-hidden="true" />从图书馆添加</Link></header>
    {library.isLoading ? <p className="py-8 text-sm text-muted-foreground">正在加载教材…</p> : textbooks.length === 0 ? <section className="border-y py-12 text-center" style={{ borderColor: 'var(--color-border-muted)' }}><BookOpenCheck className="mx-auto size-6 text-muted-foreground" aria-hidden="true" /><p className="mt-3 text-sm text-muted-foreground">尚未添加教材。</p><Link className="mt-4 inline-flex min-h-11 items-center text-sm font-medium underline underline-offset-4" to="/documents?useAsTextbook=1">从图书馆选择来源</Link></section> : <section aria-label="教材列表" className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">{textbooks.map((textbook) => <TextbookCard key={textbook.textbook_id} textbook={textbook} canManage={member?.role === 'parent'} onAssign={() => setAssignmentTarget(textbook.textbook_id)} onDelete={() => { setDeleteError(null); setTarget(textbook); }} />)}</section>}
  </div>{assignmentTarget && <BookAssignmentDialog textbookId={assignmentTarget} open onOpenChange={(open) => { if (!open) setAssignmentTarget(null); }} />}<Dialog open={target !== null} onOpenChange={(open) => { if (!open && !deletion.isPending) setTarget(null); }}><DialogContent className="max-w-md"><DialogHeader><DialogTitle>永久删除教材</DialogTitle><DialogDescription className="break-words">删除“{target?.title}”及其结构、讲义、加工记录、学生授权和学习记录，无法恢复。图书馆原文件及解析产物会保留。</DialogDescription></DialogHeader>{deleteError && <p role="alert" className="text-sm text-destructive">{deleteError}</p>}<DialogFooter><Button variant="outline" disabled={deletion.isPending} onClick={() => setTarget(null)}>取消</Button><Button variant="destructive" disabled={deletion.isPending} onClick={() => void remove()}><Trash2 className="mr-2 size-4" aria-hidden="true" />{deletion.isPending ? '正在删除…' : '永久删除'}</Button></DialogFooter></DialogContent></Dialog></main>;
}
