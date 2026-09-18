import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Highlighter, MessageSquareText, NotebookPen, Sparkles } from 'lucide-react';
import { useLearningAssetMutations, useStudentLearningItems } from '../queries';

const labels = {
  question: '追问',
  highlight: '划重点',
  note: '批注',
  summary: '总结',
} as const;

export default function PersonalNotebook({
  assignmentId,
  unitId,
  knowledgePointId,
}: {
  assignmentId: string;
  unitId?: string;
  knowledgePointId?: string;
}) {
  const items = useStudentLearningItems(
    assignmentId,
    { unitId, knowledgePointId },
    Boolean(unitId || knowledgePointId),
  );
  const [kind, setKind] = useState<'note' | 'highlight'>('note');
  const [content, setContent] = useState('');
  const mutations = useLearningAssetMutations();
  const data = items.data ?? [];
  const counts = {
    question: data.filter((item) => item.kind === 'question').length,
    highlight: data.filter((item) => item.kind === 'highlight').length,
    note: data.filter((item) => item.kind === 'note').length,
    summary: data.filter((item) => item.kind === 'summary').length,
  };

  return (
    <section aria-label="学习笔记">
      <p className="font-mono text-xs text-muted-foreground">便携笔记本</p>
      <div className="mt-4 grid grid-cols-2 gap-2">
        <div className="border p-3"><MessageSquareText className="size-4" /><p className="mt-2 font-mono text-lg">{counts.question}</p><p className="text-xs text-muted-foreground">追问</p></div>
        <div className="border p-3"><Highlighter className="size-4" /><p className="mt-2 font-mono text-lg">{counts.highlight}</p><p className="text-xs text-muted-foreground">划重点</p></div>
        <div className="border p-3"><NotebookPen className="size-4" /><p className="mt-2 font-mono text-lg">{counts.note}</p><p className="text-xs text-muted-foreground">批注</p></div>
        <div className="border p-3"><Sparkles className="size-4" /><p className="mt-2 font-mono text-lg">{counts.summary}</p><p className="text-xs text-muted-foreground">总结</p></div>
      </div>
      {unitId && <Link to={`/education/learn/${assignmentId}/summary?unit=${unitId}`} className="mt-5 inline-flex min-h-10 items-center text-sm text-muted-foreground">打开个性化总结</Link>}
      {knowledgePointId && <div className="mt-5 grid gap-2"><select aria-label="学习素材类型" value={kind} onChange={(event) => setKind(event.target.value as 'note' | 'highlight')} className="h-10 border bg-background px-3 text-sm"><option value="note">批注</option><option value="highlight">划重点</option></select><textarea aria-label="学习素材内容" value={content} onChange={(event) => setContent(event.target.value)} className="min-h-20 border bg-background p-3 text-sm" placeholder={kind === 'note' ? '写下你的理解' : '摘录一句重点'} /><Button size="sm" disabled={!content.trim() || mutations.add.isPending} onClick={() => void mutations.add.mutateAsync({ assignmentId, knowledgePointId, unitId, kind, content }).then(() => setContent(''))}>{mutations.add.isPending ? '正在保存' : '保存到笔记本'}</Button></div>}
      {data.length === 0 && <p className="mt-5 text-sm text-muted-foreground">还没有学习素材。</p>}
      {data.slice(0, 4).map((item) => <div key={item.item_id} className="mt-4 border-l-2 pl-3 text-sm" style={{ borderColor: 'var(--color-border-muted)' }}><p className="font-mono text-[11px] text-muted-foreground">{labels[item.kind]}</p><p className="mt-1 line-clamp-3">{item.content}</p></div>)}
    </section>
  );
}
