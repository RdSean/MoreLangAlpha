import { useEffect, useState } from 'react';
import { ChevronLeft, ListTree, NotebookPen, PanelLeftOpen } from 'lucide-react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { BookNavigator } from './components/BookNavigator';
import { BookLessonReader as BookReader } from './components/BookLessonReader';
import PersonalNotebook from './components/PersonalNotebook';
import {
  useLearningAssetMutations,
  useManagedBookSourceSlice,
  useStudentKnowledgePointMaterial,
  useStudentTextbookStructure,
  useBookReadingState,
} from './queries';
import type { BookStructureNode } from './types';
import './TextbookWorkbenchPage.css';

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
  const [navigatorCollapsed, setNavigatorCollapsed] = useState(false);
  const structure = useStudentTextbookStructure(assignmentId);
  const learningAssets = useLearningAssetMutations();
  const data = structure.data;
  const readingState = useBookReadingState(data?.textbook_id);
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
  const material = useStudentKnowledgePointMaterial(
    assignmentId,
    selectedKnowledgePoint?.knowledge_point_id,
  );
  const learningView = Boolean(selectedKnowledgePoint) && !selectedNode;
  const emptyLearningView = learningView && !material.data?.material_available;
  const source = useManagedBookSourceSlice(
    data?.textbook_id,
    sourceRequestRange?.start,
    sourceRequestRange?.end,
    Boolean(sourceRequestRange) && !emptyLearningView,
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
  const missionNumber = selectedKnowledgePoint?.position ?? (selectedNode ? 0 : 1);
  const missionCode = `MISSION ${String(missionNumber).padStart(2, '0')}`;
  const notebook = (
    <PersonalNotebook
      assignmentId={assignmentId}
      skillNodeId={selectedKnowledgePoint?.unit_skill_node_id ?? selectedNode?.id}
      knowledgePointId={selectedKnowledgePoint?.knowledge_point_id}
    />
  );
  const navigator = (onCollapse?: () => void) => (
    <BookNavigator
      structure={data}
      learningStates={readingState.data}
      selectedKnowledgePointSkillId={selectedKnowledgePoint?.skill_kp_id}
      selectedNodeId={selectedNode?.id}
      onSelectKnowledgePoint={selectKnowledgePoint}
      onSelectNode={selectNode}
      onCollapse={onCollapse}
    />
  );

  return (
    <main className="student-learning-shell h-full min-h-0 overflow-hidden bg-canvas" data-testid="student-textbook-learning">
      <div className={`grid h-full min-h-0 w-full ${navigatorCollapsed ? 'grid-cols-1' : 'lg:grid-cols-[280px_minmax(0,1fr)]'}`}>
        <aside hidden={navigatorCollapsed} className={`${navigatorCollapsed ? '!hidden' : 'hidden lg:flex'} min-h-0 border-r lg:flex-col`} style={{ borderColor: 'var(--color-border-muted)' }}>
          <div className="student-learning-rail-header flex h-[52px] shrink-0 items-center gap-2 border-b px-3" style={{ borderColor: 'var(--color-border-muted)' }}>
            <Link to="/education/learn" aria-label="返回我的教材" className="inline-flex size-11 shrink-0 items-center justify-center text-muted-foreground"><ChevronLeft className="size-4" /></Link>
            <div className="min-w-0">
              <span className="mission-label">TEXTBOOK / {data.textbook_id.slice(0, 6).toUpperCase()}</span>
              <h2 className="min-w-0 truncate text-xs font-semibold" title={data.textbook_title}>{data.textbook_title}</h2>
            </div>
          </div>
          <div className="min-h-0 flex-1">{navigator(() => setNavigatorCollapsed(true))}</div>
        </aside>

        <section className="flex min-h-0 min-w-0 flex-col">
          <div className="student-learning-toolbar flex min-h-11 shrink-0 items-center justify-end gap-3 border-b px-3" style={{ borderColor: 'var(--color-border-muted)' }}>
            {navigatorCollapsed && <Button size="icon" variant="ghost" className="mr-auto hidden min-h-11 min-w-11 lg:inline-flex" aria-label="展开教材目录" title="展开教材目录" onClick={() => setNavigatorCollapsed(false)}><PanelLeftOpen className="size-4" /></Button>}
            <Link to="/education/learn" className="mr-auto inline-flex min-h-11 shrink-0 whitespace-nowrap items-center gap-2 text-xs text-muted-foreground lg:hidden"><ChevronLeft className="size-4" />我的教材</Link>
            <div className="student-learning-mission" aria-label={`${missionCode} ${title}`}>
              <span className="mission-badge" aria-hidden="true">{missionNumber || '—'}</span>
              <span className="mission-label">{missionCode} / {readerView === 'material' ? 'LESSON' : 'SOURCE'}</span>
            </div>
            <div className="student-learning-actions flex shrink-0 gap-1">
              <Dialog open={navigatorOpen} onOpenChange={setNavigatorOpen}>
                <DialogTrigger asChild><Button size="icon" variant="ghost" className="min-h-11 min-w-11 lg:hidden" aria-label="打开教材目录"><ListTree className="size-4" /></Button></DialogTrigger>
                <DialogContent className="h-[80vh] overflow-hidden p-0"><DialogHeader className="sr-only"><DialogTitle>教材目录</DialogTitle></DialogHeader>{navigator()}</DialogContent>
              </Dialog>
              <Dialog>
                <DialogTrigger asChild><Button size="icon" variant="ghost" className="min-h-11 min-w-11" aria-label="打开学习笔记"><NotebookPen className="size-4" /></Button></DialogTrigger>
                <DialogContent><DialogHeader><DialogTitle>学习笔记</DialogTitle></DialogHeader>{notebook}</DialogContent>
              </Dialog>
              {selectedKnowledgePoint && <Button variant="ghost" size="sm" className="min-h-11 whitespace-nowrap" disabled={learningAssets.progress.isPending} onClick={() => void learningAssets.progress.mutateAsync({ assignmentId, knowledgePointId: selectedKnowledgePoint.knowledge_point_id, status: 'read' })}>标记已学</Button>}
            </div>
          </div>
          <div className="min-h-0 flex-1">
            <BookReader
              key={`${selectedKnowledgePoint?.skill_kp_id ?? selectedNode?.id}`}
              title={title}
              textbookId={data.textbook_id}
              assignmentId={assignmentId}
              view={readerView}
              learningView={learningView}
              material={selectedKnowledgePoint ? material.data : undefined}
              source={source.data}
              loading={(!emptyLearningView && source.isLoading) || material.isLoading}
              readingPositionKey={`student-textbook:${assignmentId}:${selectedKnowledgePoint?.skill_kp_id ?? `node:${selectedNode?.id}`}:${readerView}`}
              sourceRange={sourceRange}
              onViewChange={(view) => updateSearch((next) => next.set('view', view))}
            />
          </div>
        </section>

      </div>
    </main>
  );
}
