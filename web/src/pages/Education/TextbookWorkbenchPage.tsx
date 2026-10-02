import { useEffect, useMemo, useState } from 'react';
import { Activity, ArrowLeft, Menu, Users } from 'lucide-react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { BookActivityPanel } from './components/BookActivityPanel';
import { BookNavigator } from './components/BookNavigator';
import { BookReader } from './components/BookReader';
import type { BookGenerationValues } from './components/BookGenerationForm';
import {
  useBookActivity,
  useManagedBookMutations,
  useManagedBookSourceSlice,
  useManagedBookStructure,
  useManagedKnowledgePointMaterial,
  useTextbookWorkbench,
} from './queries';
import type { BookStructureNode, KnowledgePointProjection } from './types';
import './TextbookWorkbenchPage.css';

function findNode(nodes: readonly BookStructureNode[], nodeId: string): BookStructureNode | undefined {
  for (const node of nodes) {
    if (node.id === nodeId) return node;
    const child = findNode(node.children ?? [], nodeId);
    if (child) return child;
  }
  return undefined;
}

function requestId() {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `book-job-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export default function TextbookWorkbenchPage() {
  const { textbookId } = useParams<{ textbookId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const [navigatorOpen, setNavigatorOpen] = useState(false);
  const [batchMode, setBatchMode] = useState(false);
  const [batchSelection, setBatchSelection] = useState<Set<string>>(new Set());
  const workbench = useTextbookWorkbench(textbookId);
  const structure = useManagedBookStructure(
    textbookId,
    workbench.data?.structure_status === 'ready',
  );
  const mutations = useManagedBookMutations();

  const selectedSkillKpId = searchParams.get('kp') ?? undefined;
  const selectedNodeId = searchParams.get('node') ?? undefined;
  const selectedKnowledgePoint = structure.data?.knowledge_points.find(
    (entry) => entry.skill_kp_id === selectedSkillKpId,
  );
  const selectedNode = selectedNodeId && structure.data
    ? findNode(structure.data.structure.nodes, selectedNodeId)
    : undefined;
  const requestedView = searchParams.get('view');
  const readerView: 'material' | 'source' = selectedNode
    ? 'source'
    : requestedView === 'material' && selectedKnowledgePoint?.material_available
      ? 'material'
      : 'source';

  useEffect(() => {
    if (!structure.data) return;
    const validKp = selectedSkillKpId
      ? structure.data.knowledge_points.find((entry) => entry.skill_kp_id === selectedSkillKpId)
      : undefined;
    const validNode = selectedNodeId
      ? findNode(structure.data.structure.nodes, selectedNodeId)
      : undefined;
    const next = new URLSearchParams(searchParams);
    let changed = false;
    if (!validKp && !validNode) {
      const firstKnowledgePoint = structure.data.knowledge_points[0];
      const firstNode = structure.data.structure.nodes[0];
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
    requestedView,
    searchParams,
    selectedNodeId,
    selectedSkillKpId,
    setSearchParams,
    structure.data,
  ]);

  const sourceRange = selectedKnowledgePoint
    ? { start: selectedKnowledgePoint.start_line, end: selectedKnowledgePoint.end_line }
    : selectedNode
      ? { start: selectedNode.anchor.start_line, end: selectedNode.anchor.end_line }
      : undefined;
  const source = useManagedBookSourceSlice(
    textbookId,
    sourceRange?.start,
    sourceRange?.end,
    Boolean(sourceRange),
  );
  const material = useManagedKnowledgePointMaterial(
    textbookId,
    selectedKnowledgePoint?.knowledge_point_id,
    Boolean(selectedKnowledgePoint),
  );

  const activityJobId = searchParams.get('activity') ?? undefined;
  const activity = useBookActivity(activityJobId, textbookId, Boolean(activityJobId));
  const visibleActivityJob = activity.data?.job_id === activityJobId ? activity.data : undefined;
  const activeJob = workbench.data?.current_job ?? workbench.data?.recent_job;

  const selectionTitle = selectedKnowledgePoint?.title ?? selectedNode?.title;
  const selectedDatabaseIds = useMemo(
    () => [...batchSelection],
    [batchSelection],
  );

  const updateSearch = (update: (next: URLSearchParams) => void, replace = false) => {
    const next = new URLSearchParams(searchParams);
    update(next);
    setSearchParams(next, { replace });
  };

  const selectKnowledgePoint = (skillKpId: string) => {
    const target = structure.data?.knowledge_points.find((entry) => entry.skill_kp_id === skillKpId);
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

  const startGeneration = async (
    targets: readonly KnowledgePointProjection[],
    values: BookGenerationValues,
  ) => {
    if (!textbookId || targets.length === 0) return;
    const job = await mutations.createJob.mutateAsync({
      textbookId,
      input: {
        kind: 'materials',
        knowledge_point_ids: targets.map((entry) => entry.knowledge_point_id),
        depth: values.depth,
        requirements: values.requirements,
        replace_existing: values.replaceExisting,
        include_supplementary: values.includeSupplementary,
        idempotency_key: requestId(),
      },
    });
    updateSearch((next) => next.set('activity', job.job_id));
  };

  if (workbench.isLoading || structure.isLoading) {
    return <main className="grid h-full place-items-center bg-background"><p className="text-sm text-muted-foreground">正在加载教材工作台…</p></main>;
  }
  if (workbench.isError || !workbench.data) {
    return <main className="grid h-full place-items-center bg-background"><p className="text-sm text-destructive">无法打开教材工作台</p></main>;
  }

  const statusText = workbench.data.structure_status === 'ready'
    ? `结构已就绪 · 讲义 ${workbench.data.materials.ready}/${workbench.data.materials.total}`
    : workbench.data.structure_status === 'failed'
      ? '结构分析失败'
      : '正在分析教材结构';

  return (
    <main className="textbook-workbench" data-testid="textbook-workbench">
      <header className="textbook-workbench-header">
        <div className="flex min-w-0 items-center gap-2">
          <Link to="/textbooks" className="inline-flex size-11 shrink-0 items-center justify-center rounded-md hover:bg-[var(--color-bg-hover)]" aria-label="返回教材列表">
            <ArrowLeft className="size-4" aria-hidden="true" />
          </Link>
          <button type="button" className="textbook-workbench-menu" onClick={() => setNavigatorOpen(true)} aria-label="打开教材目录">
            <Menu className="size-4" aria-hidden="true" />
          </button>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-foreground sm:text-base">{workbench.data.title}</p>
            <p className="truncate text-xs text-muted-foreground">{statusText}</p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1 sm:gap-2">
          <Button variant="ghost" className="min-h-11 px-3" disabled={!activeJob} onClick={() => activeJob && updateSearch((next) => next.set('activity', activeJob.job_id))}>
            <Activity className="size-4 sm:mr-2" aria-hidden="true" />
            <span className="hidden sm:inline">活动</span>
          </Button>
          <Button variant="outline" className="min-h-11 px-3">
            <Users className="size-4 sm:mr-2" aria-hidden="true" />
            <span className="hidden sm:inline">给学生使用</span>
          </Button>
        </div>
      </header>

      <div className={visibleActivityJob ? 'textbook-workbench-grid has-activity' : 'textbook-workbench-grid'}>
        {structure.data && (
          <div className={cn('textbook-workbench-nav', navigatorOpen && 'is-open')}>
            <BookNavigator
              structure={structure.data}
              selectedKnowledgePointSkillId={selectedKnowledgePoint?.skill_kp_id}
              selectedNodeId={selectedNode?.id}
              onSelectKnowledgePoint={selectKnowledgePoint}
              onSelectNode={selectNode}
              batchMode={batchMode}
              onBatchModeChange={setBatchMode}
              selectedKnowledgePointIds={batchSelection}
              onBatchSelectionChange={setBatchSelection}
            />
            {navigatorOpen && <button type="button" className="textbook-workbench-nav-backdrop" onClick={() => setNavigatorOpen(false)} aria-label="关闭教材目录" />}
          </div>
        )}

        <section className="min-h-0 min-w-0">
          {structure.data && selectionTitle ? (
            <BookReader
              key={`${selectedKnowledgePoint?.skill_kp_id ?? selectedNode?.id}`}
              title={selectionTitle}
              view={readerView}
              material={selectedKnowledgePoint ? material.data : undefined}
              source={source.data}
              loading={source.isLoading || material.isLoading}
              generationPending={mutations.createJob.isPending}
              onViewChange={(view) => updateSearch((next) => next.set('view', view))}
              onGenerate={selectedKnowledgePoint
                ? (values) => startGeneration([selectedKnowledgePoint], values)
                : undefined}
            />
          ) : workbench.data.structure_status === 'ready' ? (
            <div className="grid h-full place-items-center p-6 text-center text-sm text-muted-foreground">未提取到知识点，可从原书目录阅读教材。</div>
          ) : (
            <div className="grid h-full place-items-center p-6 text-center text-sm text-muted-foreground">{statusText}</div>
          )}
        </section>

        {visibleActivityJob && (
          <div className="textbook-workbench-activity">
            <BookActivityPanel
              job={visibleActivityJob}
              events={activity.events}
              reconnecting={activity.connectionState === 'reconnecting'}
              onClose={() => updateSearch((next) => next.delete('activity'), true)}
            />
          </div>
        )}
      </div>

      {batchMode && selectedDatabaseIds.length > 0 && (
        <div className="textbook-workbench-batch" role="region" aria-label="批量生成">
          <span className="text-sm">已选择 {selectedDatabaseIds.length} 个知识点</span>
          <Button
            className="min-h-11"
            onClick={() => {
              const targets = structure.data?.knowledge_points.filter((entry) => batchSelection.has(entry.knowledge_point_id)) ?? [];
              void startGeneration(targets, {
                depth: 'lesson',
                requirements: null,
                replaceExisting: false,
                includeSupplementary: false,
              });
            }}
          >
            生成所选讲义
          </Button>
        </div>
      )}
    </main>
  );
}
