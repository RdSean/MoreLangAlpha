import { useState } from 'react';
import { BookOpenCheck, ChevronRight, Plus } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { useTextbookLibrary, useTextbookMutations } from './queries';
import type { TextbookVersionStatus } from './types';

const statusLabels: Record<TextbookVersionStatus, string> = {
  draft: '草稿', processing: '加工中', review: '待审阅', published: '已发布', failed: '加工失败',
};

function CreateTextbookDialog() {
  const [title, setTitle] = useState('');
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const mutations = useTextbookMutations();
  const create = async () => {
    const textbook = await mutations.create.mutateAsync({ title });
    setTitle('');
    setOpen(false);
    navigate(`/textbooks/${textbook.textbook_id}`);
  };
  return <Dialog open={open} onOpenChange={setOpen}>
    <DialogTrigger asChild><Button><Plus className="mr-2 size-4" aria-hidden="true" />新建教材</Button></DialogTrigger>
    <DialogContent variant="centered" className="max-w-md">
      <DialogHeader><DialogTitle>新建家庭教材</DialogTitle></DialogHeader>
      <form className="grid gap-4" onSubmit={(event) => { event.preventDefault(); void create(); }}>
        <label className="grid gap-1.5 text-sm font-medium">教材名称<Input value={title} onChange={(event) => setTitle(event.target.value)} autoFocus required /></label>
        <DialogFooter><Button type="submit" disabled={!title.trim() || mutations.create.isPending}>{mutations.create.isPending ? '正在创建' : '创建教材'}</Button></DialogFooter>
      </form>
    </DialogContent>
  </Dialog>;
}

export default function TextbooksPage() {
  const library = useTextbookLibrary();
  const textbooks = library.data ?? [];
  return <main className="h-full min-h-0 overflow-y-auto bg-canvas" data-testid="textbook-library-page">
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
      <header className="flex flex-col gap-4 border-b pb-5 sm:flex-row sm:items-end sm:justify-between" style={{ borderColor: 'var(--color-border-muted)' }}>
        <div><p className="font-mono text-xs" style={{ color: 'var(--color-text-tertiary)' }}>TEXTBOOK WORKFLOW</p><h1 className="title-font mt-2 text-2xl font-semibold" style={{ color: 'var(--color-text-primary)' }}>教材加工</h1><p className="mt-1 text-sm" style={{ color: 'var(--color-text-secondary)' }}>从图书馆选择 Markdown，依次完成结构、知识点课程和发布。</p></div>
        <CreateTextbookDialog />
      </header>
      {library.isLoading ? <p className="py-8 text-sm text-muted-foreground">正在加载教材…</p> : textbooks.length === 0 ? <section className="border py-12 text-center" style={{ borderColor: 'var(--color-border-muted)' }}><BookOpenCheck className="mx-auto size-6" style={{ color: 'var(--color-text-tertiary)' }} /><p className="mt-3 text-sm" style={{ color: 'var(--color-text-secondary)' }}>尚未创建教材。</p></section> : <div className="overflow-x-auto border-y" style={{ borderColor: 'var(--color-border-muted)' }}><table className="w-full min-w-[680px] text-left text-sm"><thead className="font-mono text-xs" style={{ color: 'var(--color-text-tertiary)' }}><tr><th scope="col" className="px-3 py-3 font-medium">教材</th><th scope="col" className="px-3 py-3 font-medium">当前版本</th><th scope="col" className="px-3 py-3 font-medium">状态</th><th scope="col" className="px-3 py-3 font-medium">章节</th><th scope="col" className="px-3 py-3 font-medium">学生</th><th scope="col" className="px-3 py-3"><span className="sr-only">打开教材</span></th></tr></thead><tbody>{textbooks.map((textbook) => <tr key={textbook.textbook_id} className="border-t" style={{ borderColor: 'var(--color-border-muted)' }}><td className="px-3 py-4 font-medium" style={{ color: 'var(--color-text-primary)' }}>{textbook.title}</td><td className="px-3 py-4 font-mono text-xs" style={{ color: 'var(--color-text-secondary)' }}>{textbook.latest_version_sequence ? `v${textbook.latest_version_sequence}` : '未加工'}</td><td className="px-3 py-4"><span className="border px-2 py-1 font-mono text-[11px]" style={{ borderColor: 'var(--color-border-muted)', color: 'var(--color-text-secondary)' }}>{textbook.latest_version_status ? statusLabels[textbook.latest_version_status] : '草稿'}</span></td><td className="px-3 py-4" style={{ color: 'var(--color-text-secondary)' }}>{textbook.chapter_count} 章</td><td className="px-3 py-4" style={{ color: 'var(--color-text-secondary)' }}>{textbook.assignment_count} 人</td><td className="px-3 py-4 text-right"><Link to={`/textbooks/${textbook.textbook_id}`} aria-label={`打开 ${textbook.title}`} className="inline-flex size-10 items-center justify-center" style={{ color: 'var(--color-text-secondary)' }}><ChevronRight className="size-4" /></Link></td></tr>)}</tbody></table></div>}
    </div>
  </main>;
}
