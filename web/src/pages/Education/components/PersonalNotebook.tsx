import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Highlighter, MessageSquareText, NotebookPen, Sparkles } from 'lucide-react';
import { useLearningAssetMutations, useStudentLearningItems } from '../queries';
import { LessonAnnotationsProvider } from './LessonAnnotations';
import { useLessonAnnotations } from './lessonAnnotationContext';
import { parseLessonAnchor } from './lessonAnnotationAnchors';
import type { LearningItem } from '../types';

const labels = {
  question: '追问',
  highlight: '划重点',
  note: '批注',
  summary: '总结',
} as const;

export default function PersonalNotebook({
  assignmentId,
  skillNodeId,
  knowledgePointId,
}: {
  assignmentId: string;
  skillNodeId?: string;
  knowledgePointId?: string;
}) {
  const content = <NotebookContents {...{ assignmentId, skillNodeId, knowledgePointId }} />;
  return knowledgePointId ? <LessonAnnotationsProvider key={`${assignmentId}:${knowledgePointId}`} {...{ assignmentId, knowledgePointId, skillNodeId }}>{content}</LessonAnnotationsProvider> : content;
}

function NotebookEntry({ item }: { item: LearningItem }) {
  const annotations = useLessonAnnotations();
  const anchor = parseLessonAnchor(item.source_anchor);
  return <div className="mt-4 border-l-2 pl-3 text-sm" style={{ borderColor: 'var(--color-border-muted)' }}>
    <p className="font-mono text-[11px] text-muted-foreground">{labels[item.kind]}</p>
    {anchor && <blockquote className="mt-2 max-h-28 overflow-y-auto whitespace-pre-wrap text-muted-foreground">{anchor.exact}</blockquote>}
    {item.kind !== 'highlight' && <p className="mt-1 whitespace-pre-wrap break-words">{item.content}</p>}
    {!anchor && item.kind === 'highlight' && <p className="mt-1 whitespace-pre-wrap break-words">{item.content}</p>}
    {annotations && (item.kind === 'note' || item.kind === 'highlight') && <Button variant="ghost" size="sm" className="min-h-11" onClick={() => annotations.open(item.item_id)}>编辑 / 删除</Button>}
  </div>;
}

function NotebookContents({ assignmentId, skillNodeId, knowledgePointId }: { assignmentId: string; skillNodeId?: string; knowledgePointId?: string }) {
  const items = useStudentLearningItems(
    assignmentId,
    knowledgePointId ? { knowledgePointId } : { skillNodeId },
    Boolean(skillNodeId || knowledgePointId),
  );
  const [kind, setKind] = useState<'note' | 'highlight'>('note');
  const [content, setContent] = useState('');
  const [saveError, setSaveError] = useState(false);
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
      {skillNodeId && <Link to={`/education/learn/${assignmentId}/summary?node=${encodeURIComponent(skillNodeId)}`} className="mt-5 inline-flex min-h-10 items-center text-sm text-muted-foreground">打开个性化总结</Link>}
      {knowledgePointId && <div className="mt-5 grid gap-2"><select aria-label="学习素材类型" value={kind} onChange={(event) => setKind(event.target.value as 'note' | 'highlight')} className="h-11 border bg-background px-3 text-sm"><option value="note">批注</option><option value="highlight">划重点</option></select><textarea aria-label="学习素材内容" value={content} onChange={(event) => setContent(event.target.value)} className="min-h-20 border bg-background p-3 text-sm" placeholder={kind === 'note' ? '写下你的理解' : '摘录一句重点'} /><Button size="sm" className="min-h-11" disabled={!content.trim() || mutations.add.isPending} onClick={() => { setSaveError(false); void mutations.add.mutateAsync({ assignmentId, knowledgePointId, skillNodeId, kind, content }).then(() => setContent('')).catch(() => setSaveError(true)); }}>{mutations.add.isPending ? '正在保存' : '保存到笔记本'}</Button>{saveError && <p role="alert" className="text-sm text-destructive">保存失败，内容已保留。</p>}</div>}
      {items.isLoading ? <p role="status" className="mt-5 text-sm text-muted-foreground">正在加载学习素材…</p> : items.isError ? <p role="alert" className="mt-5 text-sm text-destructive">学习素材加载失败。<Button variant="ghost" onClick={() => void items.refetch()}>重试</Button></p> : data.length === 0 && <p className="mt-5 text-sm text-muted-foreground">还没有学习素材。</p>}
      <div className="max-h-[40vh] overflow-y-auto">{data.map((item) => <NotebookEntry key={item.item_id} item={item} />)}</div>
    </section>
  );
}
