import { useMemo } from 'react';
import { ChevronLeft, Sparkles } from 'lucide-react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import EducationMarkdown from './components/EducationMarkdown';
import { useLearningAssetMutations, useStudentLearningItems, useStudentTextbookStructure } from './queries';
import type { BookStructureNode } from './types';

const kindLabels = {
  question: '追问',
  highlight: '划重点',
  note: '批注',
  summary: '总结',
} as const;

function findNode(nodes: readonly BookStructureNode[], nodeId: string): BookStructureNode | undefined {
  for (const node of nodes) {
    if (node.id === nodeId) return node;
    const child = findNode(node.children ?? [], nodeId);
    if (child) return child;
  }
  return undefined;
}

export default function PersonalizedSummaryPage() {
  const { assignmentId } = useParams();
  const [searchParams] = useSearchParams();
  const structure = useStudentTextbookStructure(assignmentId);
  const requestedNodeId = searchParams.get('node') ?? undefined;
  const activeNode = useMemo(
    () => requestedNodeId && structure.data
      ? findNode(structure.data.structure.nodes, requestedNodeId)
      : structure.data?.structure.nodes[0],
    [requestedNodeId, structure.data],
  );
  const items = useStudentLearningItems(
    assignmentId,
    { skillNodeId: activeNode?.id },
    Boolean(activeNode),
  );
  const mutations = useLearningAssetMutations();

  if (structure.isLoading || items.isLoading) return <main className="h-full overflow-y-auto bg-canvas p-8 text-sm text-muted-foreground">正在加载学习总结…</main>;
  if (!assignmentId || !activeNode || !structure.data) return <main className="h-full overflow-y-auto bg-canvas p-8 text-sm text-muted-foreground">学习总结不存在。</main>;

  const data = items.data ?? [];
  const summaries = data.filter((item) => item.kind === 'summary');
  const knowledgePointTitle = new Map(
    structure.data.knowledge_points
      .filter((point) => point.unit_skill_node_id === activeNode.id || point.node_skill_ids.includes(activeNode.id))
      .map((point) => [point.knowledge_point_id, point.title]),
  );

  return (
    <main className="h-full overflow-y-auto bg-canvas" data-testid="personalized-summary-page">
      <div className="mx-auto max-w-4xl px-5 py-8">
        <Link to={`/education/learn/${assignmentId}?node=${encodeURIComponent(activeNode.id)}&view=source`} className="inline-flex items-center gap-2 text-sm text-muted-foreground"><ChevronLeft className="size-4" />返回教材</Link>
        <div className="mt-6 flex flex-wrap items-end justify-between gap-4 border-b pb-5" style={{ borderColor: 'var(--color-border-muted)' }}>
          <div><p className="font-mono text-xs text-muted-foreground">PERSONALIZED SUMMARY</p><h1 className="title-font mt-2 text-2xl font-semibold">{activeNode.title}</h1></div>
          <Button onClick={() => void mutations.summarize.mutateAsync({ assignmentId, skillNodeId: activeNode.id })} disabled={mutations.summarize.isPending}><Sparkles className="mr-2 size-4" />{mutations.summarize.isPending ? '正在生成' : '生成个性化总结'}</Button>
        </div>
        {summaries[0] && <section className="mt-8 border-l-2 pl-5" style={{ borderColor: 'var(--color-accent-primary)' }}><EducationMarkdown content={summaries[0].content} variant="summary" /></section>}
        <section className="mt-10">
          <h2 className="text-sm font-semibold">学习素材</h2>
          {data.length === 0 ? <p className="mt-4 text-sm text-muted-foreground">本节还没有追问、划重点或批注。</p> : <div className="mt-4 grid gap-4">{data.filter((item) => item.kind !== 'summary').map((item) => <article key={item.item_id} className="border-b pb-4" style={{ borderColor: 'var(--color-border-muted)' }}><p className="font-mono text-[11px] text-muted-foreground">{kindLabels[item.kind]} · {knowledgePointTitle.get(item.knowledge_point_id ?? '') ?? '本节'}</p><p className="mt-2 whitespace-pre-wrap text-sm leading-6">{item.content}</p></article>)}</div>}
        </section>
      </div>
    </main>
  );
}
