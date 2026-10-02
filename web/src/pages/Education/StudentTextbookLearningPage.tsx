import { useEffect, useState } from 'react';
import { ChevronLeft, ListTree, MessageCircle, NotebookPen } from 'lucide-react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { BookNavigator } from './components/BookNavigator';
import { BookReader } from './components/BookReader';
import PersonalNotebook from './components/PersonalNotebook';
import StudentLessonFollowUp from './components/StudentLessonFollowUp';
import {
  useLearningAssetMutations,
  useManagedBookSourceSlice,
  useStudentKnowledgePointMaterial,
  useStudentTextbookStructure,
} from './queries';
import type { BookStructureNode } from './types';

const SOURCE_CONTEXT_LINES = 12;

function findNode(nodes: readonly BookStructureNode[], nodeId: string): BookStructureNode | undefined {
  for (const node of nodes) {
    if (node.id === nodeId) return node;
    const child = findNode(node.children ?? [], nodeId);
    if (child) return child;
  }
  return undefined;
}

export default function StudentTextbookLearningPage() {
  const { assignmentId } = useParams<{ assignmentId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const [navigatorOpen, setNavigatorOpen] = useState(false);
  const structure = useStudentTextbookStructure(assignmentId);
  const learningAssets = useLearningAssetMutations();
  const data = structure.data;
  const selectedSkillKpId = searchParams.get('kp') ?? undefined;
  const selectedNodeId = searchParams.get('node') ?? undefined;
  const selectedKnowledgePoint = data?.knowledge_points.find(
    (entry) => entry.skill_kp_id === selectedSkillKpId,
  );
  const selectedNode = selectedNodeId && data
    ? findNode(data.structure.nodes, selectedNodeId)
    : undefined;
  const requestedView = searchParams.get('view');
  const readerView: 'material' | 'source' = selectedNode
    ? 'source'
    : requestedView === 'material' && selectedKnowledgePoint?.material_available
      ? 'material'
      : 'source';

  useEffect(() => {
    if (!data) return;
    const validKp = selectedSkillKpId
      ? data.knowledge_points.find((entry) => entry.skill_kp_id === selectedSkillKpId)
      : undefined;
    const validNode = selectedNodeId
      ? findNode(data.structure.nodes, selectedNodeId)
      : undefined;
    const next = new URLSearchParams(searchParams);
    let changed = false;
    if (!validKp && !validNode) {
      const firstKnowledgePoint = data.knowledge_points[0];
      const firstNode = data.structure.nodes[0];
      if (firstKnowledgePoint) {
        next.set('kp', firstKnowledgePoint.skill_kp_id);
        next.delete('node');
        next.set('view', firstKnowledgePoint.material_available ? 'material' : 'source');
        changed = true;
      } else if (firstNode) {
        next.set('node', firstNode.id);
        next.delete('kp');
        next.set('view', 'source');
        changed = true;
      }
    } else if (validNode && requestedView !== 'source') {
      next.set('view', 'source');
      changed = true;
    } else if (validKp && requestedView !== 'source' && requestedView !== 'material') {
      next.set('view', validKp.material_available ? 'material' : 'source');
      changed = true;
    } else if (validKp && requestedView === 'material' && !validKp.material_available) {
      next.set('view', 'source');
      changed = true;
    }
    if (changed) setSearchParams(next, { replace: true });
  }, [
    data,
    requestedView,
    searchParams,
    selectedNodeId,
    selectedSkillKpId,
    setSearchParams,
  ]);

  const sourceRange = selectedKnowledgePoint
    ? { start: selectedKnowledgePoint.start_line, end: selectedKnowledgePoint.end_line }
    : selectedNode
      ? { start: selectedNode.anchor.start_line, end: selectedNode.anchor.end_line }
      : undefined;
  const sourceRequestRange = sourceRange && data
    ? {
        start: Math.max(1, sourceRange.start - SOURCE_CONTEXT_LINES),
        end: Math.min(data.structure.source.total_lines, sourceRange.end + SOURCE_CONTEXT_LINES),
      }
    : undefined;
  const source = useManagedBookSourceSlice(
    data?.textbook_id,
    sourceRequestRange?.start,
    sourceRequestRange?.end,
    Boolean(sourceRequestRange),
  );
  const material = useStudentKnowledgePointMaterial(
    assignmentId,
    selectedKnowledgePoint?.knowledge_point_id,
  );

  const updateSearch = (update: (next: URLSearchParams) => void) => {
    const next = new URLSearchParams(searchParams);
    update(next);
    setSearchParams(next);
  };
  const selectKnowledgePoint = (skillKpId: string) => {
    const target = data?.knowledge_points.find((entry) => entry.skill_kp_id === skillKpId);
    if (!target) return;
    updateSearch((next) => {
      next.set('kp', skillKpId);
      next.delete('node');
      next.set('view', target.material_available ? 'material' : 'source');
    });
    setNavigatorOpen(false);
  };
  const selectNode = (nodeId: string) => {
    updateSearch((next) => {
      next.set('node', nodeId);
      next.delete('kp');
      next.set('view', 'source');
    });
    setNavigatorOpen(false);
  };

  if (structure.isLoading) {
    return <main className="h-full overflow-y-auto bg-canvas p-8 text-sm text-muted-foreground">正在加载学习内容…</main>;
  }
  if (!data || !assignmentId || (!selectedKnowledgePoint && !selectedNode)) {
    return <main className="h-full overflow-y-auto bg-canvas p-8 text-sm text-muted-foreground">学习材料不存在或尚未完成分析。</main>;
  }

  const title = selectedKnowledgePoint?.title ?? selectedNode?.title ?? data.textbook_title;
  const notebook = (
    <PersonalNotebook
      assignmentId={assignmentId}
      skillNodeId={selectedKnowledgePoint?.unit_skill_node_id ?? selectedNode?.id}
      knowledgePointId={selectedKnowledgePoint?.knowledge_point_id}
    />
  );
  const followUp = selectedKnowledgePoint && material.data?.material_available ? (
    <StudentLessonFollowUp
      assignmentId={assignmentId}
      knowledgePointId={selectedKnowledgePoint.knowledge_point_id}
    />
  ) : null;
  const navigator = (
    <BookNavigator
      structure={data}
      selectedKnowledgePointSkillId={selectedKnowledgePoint?.skill_kp_id}
      selectedNodeId={selectedNode?.id}
      onSelectKnowledgePoint={selectKnowledgePoint}
      onSelectNode={selectNode}
    />
  );

  return (
    <main className="h-full min-h-0 overflow-hidden bg-canvas" data-testid="student-textbook-learning">
      <div className="grid h-full min-h-0 w-full lg:grid-cols-[280px_minmax(0,1fr)_320px]">
        <aside className="hidden min-h-0 border-r lg:flex lg:flex-col" style={{ borderColor: 'var(--color-border-muted)' }}>
          <div className="border-b px-4 py-4" style={{ borderColor: 'var(--color-border-muted)' }}>
            <Link to="/education" className="inline-flex min-h-10 items-center gap-2 text-sm text-muted-foreground"><ChevronLeft className="size-4" />我的学习</Link>
            <h2 className="mt-2 break-words text-base font-semibold">{data.textbook_title}</h2>
          </div>
          <div className="min-h-0 flex-1">{navigator}</div>
        </aside>

        <section className="flex min-h-0 min-w-0 flex-col">
          <div className="flex min-h-14 items-center justify-between gap-3 border-b px-3 lg:hidden" style={{ borderColor: 'var(--color-border-muted)' }}>
            <Link to="/education" className="inline-flex min-h-10 items-center gap-2 text-sm text-muted-foreground"><ChevronLeft className="size-4" />我的学习</Link>
            <div className="flex gap-1">
              <Dialog open={navigatorOpen} onOpenChange={setNavigatorOpen}>
                <DialogTrigger asChild><Button size="icon" variant="ghost" aria-label="打开教材目录"><ListTree className="size-4" /></Button></DialogTrigger>
                <DialogContent className="h-[80vh] overflow-hidden p-0"><DialogHeader className="sr-only"><DialogTitle>教材目录</DialogTitle></DialogHeader>{navigator}</DialogContent>
              </Dialog>
              <Dialog>
                <DialogTrigger asChild><Button size="icon" variant="ghost" aria-label="打开学习笔记"><NotebookPen className="size-4" /></Button></DialogTrigger>
                <DialogContent><DialogHeader><DialogTitle>学习笔记</DialogTitle></DialogHeader>{notebook}</DialogContent>
              </Dialog>
              {followUp && (
                <Dialog>
                  <DialogTrigger asChild><Button size="icon" variant="ghost" aria-label="打开知识点追问"><MessageCircle className="size-4" /></Button></DialogTrigger>
                  <DialogContent><DialogHeader><DialogTitle>知识点追问</DialogTitle></DialogHeader>{followUp}</DialogContent>
                </Dialog>
              )}
            </div>
          </div>
          <div className="min-h-0 flex-1">
            <BookReader
              key={`${selectedKnowledgePoint?.skill_kp_id ?? selectedNode?.id}`}
              title={title}
              view={readerView}
              material={selectedKnowledgePoint ? material.data : undefined}
              source={source.data}
              loading={source.isLoading || material.isLoading}
              readingPositionKey={`student-textbook:${assignmentId}:${selectedKnowledgePoint?.skill_kp_id ?? `node:${selectedNode?.id}`}:${readerView}`}
              sourceHighlightRange={sourceRange}
              onViewChange={(view) => updateSearch((next) => next.set('view', view))}
            />
          </div>
        </section>

        <aside className="hidden min-h-0 overflow-y-auto border-l px-5 py-6 lg:block" style={{ borderColor: 'var(--color-border-muted)' }}>
          {selectedKnowledgePoint && (
            <Button
              className="mb-6 w-full"
              size="sm"
              onClick={() => void learningAssets.progress.mutateAsync({
                assignmentId,
                knowledgePointId: selectedKnowledgePoint.knowledge_point_id,
                status: 'read',
              })}
              disabled={learningAssets.progress.isPending}
            >
              标记已学
            </Button>
          )}
          {notebook}
          {followUp && <div className="mt-8">{followUp}</div>}
        </aside>
      </div>
    </main>
  );
}
