import { useEffect, useMemo, useState } from 'react';
import { isAxiosError } from 'axios';
import {
  ArrowLeft,
  Menu,
  PanelLeftOpen,
  RotateCcw,
  StopCircle,
} from 'lucide-react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { BookActivityPanel } from './components/BookActivityPanel';
import { BookNavigator } from './components/BookNavigator';
import { BookLessonReader as BookReader } from './components/BookLessonReader';
import { BookOriginalReader } from './components/BookOriginalReader';
import { firstJsonPage } from './components/bookOriginalLocation';
import { BookProcessingView } from './components/BookProcessingView';
import { projectBookTiming } from './components/bookTimingProjection';
import { useBookElapsedTime } from './components/useBookElapsedTime';
import { useBookLiveActivity } from './components/useBookLiveActivity';
import { isTerminalBookJobStatus, projectBookActivity } from './components/bookActivityProjection';
import { bookSourceInfo } from './components/bookProcessingText';
import {
  BookGenerationForm,
  type BookGenerationValues,
} from './components/BookGenerationForm';
import {
  useBookActivity,
  useManagedBookMutations,
  useManagedBookSourceSlice,
  useManagedBookStructure,
  useManagedKnowledgePointMaterial,
  useTextbookWorkbench,
  useBookReadingState,
} from './queries';
import type { BookStructureNode, KnowledgePointProjection } from './types';
import './TextbookWorkbenchPage.css';

function findNode(
  nodes: readonly BookStructureNode[],
  nodeId: string,
): BookStructureNode | undefined {
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

const SOURCE_CONTEXT_LINES = 12;

export default function TextbookWorkbenchPage() {
  const { t } = useTranslation();
  const { textbookId } = useParams<{ textbookId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const [navigatorOpen, setNavigatorOpen] = useState(false);
  const [navigatorCollapsed, setNavigatorCollapsed] = useState(false);
  const [batchMode, setBatchMode] = useState(false);
  const [batchFormOpen, setBatchFormOpen] = useState(false);
  const [batchSelection, setBatchSelection] = useState<Set<string>>(new Set());
  const workbench = useTextbookWorkbench(textbookId);
  const readingState = useBookReadingState(textbookId);
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
  const selectedNode =
    selectedNodeId && structure.data
      ? findNode(structure.data.structure.nodes, selectedNodeId)
      : undefined;
  const requestedView = searchParams.get('view');

  const sourceRange = selectedKnowledgePoint
    ? {
        start: selectedKnowledgePoint.start_line,
        end: selectedKnowledgePoint.end_line,
      }
    : selectedNode
      ? {
          start: selectedNode.anchor.start_line,
          end: selectedNode.anchor.end_line,
        }
      : undefined;
  const sourceRequestRange =
    sourceRange && structure.data
      ? {
          start: Math.max(1, sourceRange.start - SOURCE_CONTEXT_LINES),
          end: Math.min(
            structure.data.structure.source.total_lines,
            sourceRange.end + SOURCE_CONTEXT_LINES,
          ),
        }
      : undefined;
  const source = useManagedBookSourceSlice(
    textbookId,
    sourceRequestRange?.start,
    sourceRequestRange?.end,
    Boolean(sourceRequestRange) && requestedView !== 'original',
  );
  const material = useManagedKnowledgePointMaterial(
    textbookId,
    selectedKnowledgePoint?.knowledge_point_id,
    Boolean(selectedKnowledgePoint),
  );

  const showProcessing =
    searchParams.get('panel') === 'processing' ||
    (workbench.data?.structure_status !== 'ready' &&
      searchParams.get('panel') !== 'reading');
  const activityJobId =
    searchParams.get('activity') ??
    workbench.data?.current_job?.job_id ??
    (showProcessing ? workbench.data?.recent_job?.job_id : undefined);
  const activity = useBookActivity(
    activityJobId,
    textbookId,
    Boolean(activityJobId),
  );
  const visibleActivityJob =
    activity.data?.job_id === activityJobId &&
    activity.data?.textbook_id === textbookId
      ? activity.data
      : undefined;
  const activityOwnershipMismatch = Boolean(
    activityJobId && activity.data && !visibleActivityJob,
  );
  const activityAccessLost =
    activity.accessLost ||
    (isAxiosError(activity.error) &&
      [401, 403, 404].includes(activity.error.response?.status ?? 0));
  const unavailableActivityMessage = activityAccessLost
    ? isAxiosError(activity.error)
      ? '处理任务不存在或已不可访问'
      : '处理活动已不可访问，计时已停止'
    : activity.isError && !visibleActivityJob
      ? '处理活动暂不可用'
      : null;
  const currentJob = workbench.data?.current_job;
  useEffect(() => {
    if (
      !workbench.data ||
      workbench.data.structure_status === 'ready' ||
      searchParams.has('panel')
    )
      return;
    const next = new URLSearchParams(searchParams);
    next.set('panel', 'processing');
    setSearchParams(next, { replace: true });
  }, [workbench.data, searchParams, setSearchParams]);
  const processingActive = Boolean(currentJob && !isTerminalBookJobStatus(visibleActivityJob?.job_id === currentJob.job_id ? visibleActivityJob.status : currentJob.status));
  const showActivityPanel =
    Boolean(searchParams.get('activity')) && !showProcessing;
  const cancellationInTimeline =
    processingActive &&
    visibleActivityJob?.job_id === currentJob?.job_id &&
    !activityOwnershipMismatch &&
    !unavailableActivityMessage &&
    (showProcessing || showActivityPanel);
  const connected =
    activity.connectionState === 'connected' &&
    !activity.streamTerminal &&
    !activityAccessLost;
  const elapsedNow = useBookElapsedTime(visibleActivityJob, connected);
  const activityProjection = useMemo(
    () =>
      visibleActivityJob
        ? projectBookActivity(visibleActivityJob, activity.events)
        : undefined,
    [visibleActivityJob, activity.events],
  );
  const liveActivity = useBookLiveActivity(
    visibleActivityJob,
    activityProjection?.currentItem,
    activity.events,
    connected &&
      (showProcessing || showActivityPanel) &&
      visibleActivityJob?.activity_status !== 'unavailable',
    activity.liveAfterSeq,
  );
  const timing = projectBookTiming(visibleActivityJob, elapsedNow);
  const readableKnowledgePoints = useMemo(() => {
    const ready = new Set(
      structure.data?.knowledge_points
        .filter((point) => point.material_available)
        .map((point) => point.skill_kp_id),
    );
    for (const item of visibleActivityJob?.items ?? []) {
      if (item.kind !== 'material' || item.status !== 'succeeded') continue;
      const point = structure.data?.knowledge_points.find(
        (point) => point.knowledge_point_id === item.knowledge_point_id,
      );
      if (point) ready.add(point.skill_kp_id);
    }
    if (
      material.data &&
      material.data.textbook_id === textbookId &&
      material.data.material_available
    )
      ready.add(material.data.skill_kp_id);
    return ready;
  }, [structure.data, visibleActivityJob, material.data, textbookId]);
  const readerView: 'material' | 'source' | 'original' = requestedView === 'original'
    ? 'original'
    : selectedNode
    ? 'source'
    : requestedView === 'material' &&
        selectedSkillKpId &&
        readableKnowledgePoints.has(selectedSkillKpId)
      ? 'material'
      : 'source';

  useEffect(() => {
    if (!structure.data) return;
    const validKp = selectedSkillKpId
      ? structure.data.knowledge_points.find(
          (entry) => entry.skill_kp_id === selectedSkillKpId,
        )
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
        next.set(
          'view',
          readableKnowledgePoints.has(firstKnowledgePoint.skill_kp_id)
            ? 'material'
            : 'source',
        );
        changed = true;
      } else if (firstNode) {
        next.set('node', firstNode.id);
        next.delete('kp');
        next.set('view', 'source');
        changed = true;
      }
    } else if (validNode && requestedView !== 'source' && requestedView !== 'original') {
      next.set('view', 'source');
      changed = true;
    } else if (
      validKp &&
      requestedView !== 'source' &&
      requestedView !== 'original' &&
      requestedView !== 'material'
    ) {
      next.set(
        'view',
        readableKnowledgePoints.has(validKp.skill_kp_id)
          ? 'material'
          : 'source',
      );
      changed = true;
    } else if (
      validKp &&
      requestedView === 'material' &&
      !readableKnowledgePoints.has(validKp.skill_kp_id)
    ) {
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
    readableKnowledgePoints,
  ]);
  const recoverableJob =
    workbench.data?.recent_job &&
    ['failed', 'partially_succeeded', 'cancelled'].includes(
      workbench.data.recent_job.status,
    )
      ? workbench.data.recent_job
      : undefined;

  const selectionTitle = selectedKnowledgePoint?.title ?? selectedNode?.title;
  const jsonPage = firstJsonPage(selectedNode ? [selectedNode] : selectedKnowledgePoint && structure.data ? selectedKnowledgePoint.node_skill_ids.flatMap((id) => {
    const node = findNode(structure.data!.structure.nodes, id);
    return node ? [node] : [];
  }) : []);
  const pageParam = Number(searchParams.get('pdfPage'));
  const restoredPdfPage = Number.isSafeInteger(pageParam) && pageParam > 0 ? pageParam : undefined;
  const navParam = searchParams.get('nav');
  const navigatorView = navParam === 'source' || navParam === 'text' || navParam === 'knowledge' ? navParam : selectedNode ? requestedView === 'original' ? 'source' : 'text' : 'knowledge';
  const selectedTargets = useMemo(
    () =>
      structure.data?.knowledge_points.filter((entry) =>
        batchSelection.has(entry.knowledge_point_id),
      ) ?? [],
    [batchSelection, structure.data?.knowledge_points],
  );
  const existingSelectedCount = selectedTargets.filter(
    (entry) => entry.material_available,
  ).length;

  const updateSearch = (
    update: (next: URLSearchParams) => void,
    replace = false,
  ) => {
    const next = new URLSearchParams(searchParams);
    update(next);
    setSearchParams(next, { replace });
  };

  const selectKnowledgePoint = (skillKpId: string) => {
    const target = structure.data?.knowledge_points.find(
      (entry) => entry.skill_kp_id === skillKpId,
    );
    if (!target) return;
    updateSearch((next) => {
      next.set('kp', skillKpId);
      next.set('nav', 'knowledge');
      next.delete('pdfPage');
      next.delete('node');
      next.set(
        'view',
        readableKnowledgePoints.has(skillKpId) ? 'material' : 'source',
      );
      next.delete('panel');
      if (visibleActivityJob && isTerminalBookJobStatus(visibleActivityJob.status))
        next.delete('activity');
    });
    setNavigatorOpen(false);
  };

  const selectNode = (nodeId: string, view: 'source' | 'original' = 'source') => {
    updateSearch((next) => {
      next.set('node', nodeId);
      next.delete('kp');
      next.set('view', view);
      next.set('nav', view === 'original' ? 'source' : 'text');
      next.delete('pdfPage');
      next.delete('panel');
    });
    setNavigatorOpen(false);
  };

  const openMaterialLink = (path: string) => {
    const normalizedPath = path.replace(/^\.\//, '').split(/[?#]/, 1)[0];
    const target = structure.data?.knowledge_points.find(
      (entry) =>
        entry.content_file === normalizedPath ||
        `materials/${entry.knowledge_point_id}.md` === normalizedPath,
    );
    if (target) selectKnowledgePoint(target.skill_kp_id);
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
    updateSearch((next) => {
      next.set('activity', job.job_id);
      next.set('panel', 'processing');
    });
  };

  const cancelCurrentJob = async () => {
    if (!currentJob) return;
    await mutations.cancelJob.mutateAsync(currentJob.job_id);
  };

  const retryUnfinished = async () => {
    if (!recoverableJob) return;
    const job = await mutations.retryJob.mutateAsync(recoverableJob.job_id);
    updateSearch((next) => {
      next.set('activity', job.job_id);
      next.set('panel', 'processing');
    });
  };

  if (workbench.isLoading || structure.isLoading) {
    return (
      <main className="grid h-full place-items-center bg-background">
        <p className="text-sm text-muted-foreground">正在加载教材工作台…</p>
      </main>
    );
  }
  if (workbench.isError || !workbench.data) {
    return (
      <main className="grid h-full place-items-center bg-background">
        <p className="text-sm text-destructive">无法打开教材工作台</p>
      </main>
    );
  }

  const statusText =
    workbench.data.structure_status === 'ready'
      ? `结构已就绪 · 讲义 ${workbench.data.materials.ready}/${workbench.data.materials.total}`
      : workbench.data.structure_status === 'failed'
        ? '结构分析失败'
        : workbench.data.source_status === 'pending'
          ? '等待准备教材来源'
          : workbench.data.source_status === 'preparing'
            ? '正在准备教材来源'
            : workbench.data.source_status === 'failed'
              ? '教材来源准备失败'
              : workbench.data.source_status === 'cancelled'
                ? '教材来源准备已取消'
                : '正在分析教材结构';

  const bookHeader = (
      <header className="textbook-workbench-header">
        <div className="flex min-w-0 items-center gap-2">
          <Link
            to="/textbooks"
            className="inline-flex size-8 shrink-0 items-center justify-center rounded-md hover:bg-[var(--color-bg-hover)]"
            aria-label="返回教材列表"
          >
            <ArrowLeft className="size-4" aria-hidden="true" />
          </Link>
          <button
            type="button"
            className="textbook-workbench-menu"
            onClick={() => setNavigatorOpen(true)}
            aria-label="打开教材目录"
          >
            <Menu className="size-4" aria-hidden="true" />
          </button>
          <div className="min-w-0">
            <p
              className="truncate text-xs font-semibold text-foreground"
              title={workbench.data.title}
            >
              {workbench.data.title}
            </p>
            <p className="truncate text-xs text-muted-foreground">
              {showProcessing ? bookSourceInfo(workbench.data.source ?? (workbench.data.selected_source ? { ...workbench.data.selected_source, frozen_at: null } : null)) || statusText : statusText}
            </p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1 sm:gap-2">
          {processingActive && !cancellationInTimeline && (
            <Button
              variant="outline"
              className="min-h-11 px-3"
              disabled={mutations.cancelJob.isPending}
              onClick={() => void cancelCurrentJob()}
            >
              <StopCircle className="size-4 sm:mr-2" aria-hidden="true" />
              <span>{t('bookProcessing.cancelRequest')}</span>
            </Button>
          )}
          {!currentJob && recoverableJob && (
            <Button
              variant="outline"
              className="min-h-11 px-3"
              disabled={mutations.retryJob.isPending}
              onClick={() => void retryUnfinished()}
            >
              <RotateCcw className="size-4 sm:mr-2" aria-hidden="true" />
              <span>重试未完成项</span>
            </Button>
          )}
        </div>
      </header>
  );
  return (
    <main className={cn('textbook-workbench', showProcessing && 'is-processing', navigatorCollapsed && 'is-nav-collapsed')} data-testid="textbook-workbench">
      <div className="textbook-mobile-header">
        <Button size="icon" variant="ghost" aria-label="打开教材目录" onClick={() => setNavigatorOpen(true)}><Menu className="size-4" /></Button>
        <span className="min-w-0 truncate text-xs font-medium">{workbench.data.title}</span>
      </div>
      {!structure.data && bookHeader}
      <div
        className={cn(
          'textbook-workbench-grid',
          showActivityPanel &&
            visibleActivityJob &&
            !activityAccessLost &&
            'has-activity',
          (!structure.data || navigatorCollapsed) && 'without-nav',
        )}
      >
        {structure.data && navigatorCollapsed && <button type="button" className="textbook-nav-restore" title="展开教材目录" aria-label="展开教材目录" onClick={() => setNavigatorCollapsed(false)}><PanelLeftOpen className="size-4" aria-hidden="true" /></button>}
        {structure.data && (
          <div
            className={cn('textbook-workbench-nav', navigatorOpen && 'is-open')}
          >
            {bookHeader}
            <div className="min-h-0 flex-1">
            <BookNavigator
              structure={structure.data}
              learningStates={readingState.data}
              selectedKnowledgePointSkillId={
                selectedKnowledgePoint?.skill_kp_id
              }
              selectedNodeId={selectedNode?.id}
              onSelectKnowledgePoint={selectKnowledgePoint}
              onSelectNode={selectNode}
              onSelectOriginalNode={(nodeId) => selectNode(nodeId, 'original')}
              activeView={navigatorView}
              onCollapse={() => { setNavigatorCollapsed(true); setNavigatorOpen(false); }}
              onNavigationChange={(view) => {
                if (view === 'knowledge') {
                  const target = selectedKnowledgePoint ?? structure.data?.knowledge_points[0];
                  if (target) { selectKnowledgePoint(target.skill_kp_id); return; }
                }
                updateSearch((next) => {
                  next.set('nav', view);
                  next.set('view', view === 'source' ? 'original' : 'source');
                  next.delete('panel');
                });
              }}
              batchMode={batchMode}
              batchDisabled={Boolean(currentJob)}
              onBatchModeChange={(enabled) => {
                setBatchMode(enabled);
                if (!enabled) {
                  setBatchFormOpen(false);
                  setBatchSelection(new Set());
                }
              }}
              selectedKnowledgePointIds={batchSelection}
              onBatchSelectionChange={setBatchSelection}
            />
            </div>
            {navigatorOpen && (
              <button
                type="button"
                className="textbook-workbench-nav-backdrop"
                onClick={() => setNavigatorOpen(false)}
                aria-label="关闭教材目录"
              />
            )}
          </div>
        )}

        <section className="flex min-h-0 min-w-0 flex-col">
          {activityOwnershipMismatch ||
          ((showProcessing || showActivityPanel) &&
            unavailableActivityMessage) ? (
            <div className="grid h-full place-content-center gap-4 p-6 text-center">
              <p className="text-sm text-destructive" role="alert">
                {activityOwnershipMismatch
                  ? '该处理任务不属于当前教材'
                  : unavailableActivityMessage}
              </p>
              <Button
                variant="outline"
                className="min-h-11"
                onClick={() =>
                  updateSearch((next) => {
                    next.delete('activity');
                    if (workbench.data.structure_status === 'ready')
                      next.delete('panel');
                    else
                      next.set(
                        'panel',
                        activityOwnershipMismatch ? 'processing' : 'reading',
                      );
                  }, true)
                }
              >
                返回当前教材
              </Button>
            </div>
          ) : showProcessing ? (
            visibleActivityJob ? (
              <BookProcessingView
                key={visibleActivityJob.job_id}
                job={visibleActivityJob}
                bookTitle={workbench.data.title}
                source={workbench.data.source ?? (workbench.data.selected_source ? { ...workbench.data.selected_source, frozen_at: null } : null)}
                events={activity.events}
                connected={connected}
                reconnecting={activity.connectionState === 'reconnecting'}
                liveAfterSeq={activity.liveAfterSeq}
                timing={timing}
                liveActivity={liveActivity}
                projection={activityProjection}
                sourceStatus={workbench.data.source_status}
                knowledgePoints={structure.data?.knowledge_points}
                onCancel={processingActive && currentJob?.job_id === visibleActivityJob.job_id ? () => void cancelCurrentJob() : undefined}
                cancelPending={mutations.cancelJob.isPending}
                onReturnToReading={() =>
                  updateSearch((next) => {
                    if (isTerminalBookJobStatus(visibleActivityJob.status))
                      next.delete('activity');
                    if (workbench.data.structure_status === 'ready')
                      next.delete('panel');
                    else next.set('panel', 'reading');
                  })
                }
                onOpenMaterial={selectKnowledgePoint}
              />
            ) : (
              <div
                className="grid h-full place-items-center p-6 text-center text-sm text-muted-foreground"
                role="status"
              >
                {activity.isError ? '处理活动暂不可用，请刷新重试' : statusText}
              </div>
            )
          ) : (
            <>
              {batchFormOpen && selectedTargets.length > 0 && (
                <BookGenerationForm
                  targetCount={selectedTargets.length}
                  existingCount={existingSelectedCount}
                  pending={mutations.createJob.isPending}
                  onCancel={() => setBatchFormOpen(false)}
                  onSubmit={async (values) => {
                    const targets = values.replaceExisting
                      ? selectedTargets
                      : selectedTargets.filter(
                          (entry) => !entry.material_available,
                        );
                    await startGeneration(targets, values);
                    setBatchFormOpen(false);
                    setBatchMode(false);
                    setBatchSelection(new Set());
                  }}
                />
              )}
              <div className="min-h-0 flex-1">
                {structure.data && selectionTitle ? (
                  <BookReader
                    key={`${selectedKnowledgePoint?.skill_kp_id ?? selectedNode?.id}`}
                    title={selectionTitle}
                    textbookId={textbookId}
                    view={readerView}
                    material={
                      selectedKnowledgePoint ? material.data : undefined
                    }
                    source={source.data}
                    originalAvailable
                    originalContent={textbookId && readerView === 'original' ? <BookOriginalReader key={`${textbookId}:${selectedKnowledgePoint?.skill_kp_id ?? selectedNode?.id}`} textbookId={textbookId} startLine={sourceRange?.start} jsonPage={jsonPage} restoredPage={restoredPdfPage} onPageChange={(page) => updateSearch((next) => next.set('pdfPage', String(page)), true)} /> : undefined}
                    loading={source.isLoading || material.isLoading}
                    generationPending={mutations.createJob.isPending}
                    readingPositionKey={`textbook:${textbookId}:${selectedKnowledgePoint?.skill_kp_id ?? `node:${selectedNode?.id}`}:${readerView}`}
                    sourceHighlightRange={sourceRange}
                    onViewChange={(view) =>
                      updateSearch((next) => {
                        next.set('view', view);
                        next.set('nav', view === 'original' ? 'source' : view === 'source' ? 'text' : 'knowledge');
                      })
                    }
                    onOpenMaterialLink={openMaterialLink}
                    onGenerate={
                      selectedKnowledgePoint && !currentJob
                        ? (values) =>
                            startGeneration([selectedKnowledgePoint], values)
                        : undefined
                    }
                  />
                ) : workbench.data.structure_status === 'ready' ? (
                  <div className="grid h-full place-items-center p-6 text-center text-sm text-muted-foreground">
                    未提取到知识点，可从原书目录阅读教材。
                  </div>
                ) : (
                  <div className="grid h-full place-items-center p-6 text-center text-sm text-muted-foreground">
                    {statusText}
                  </div>
                )}
              </div>
            </>
          )}
        </section>

        {visibleActivityJob && showActivityPanel && !activityAccessLost && (
          <div className="textbook-workbench-activity">
            <BookActivityPanel
              job={visibleActivityJob}
              events={activity.events}
              connected={connected}
              liveAfterSeq={activity.liveAfterSeq}
              reconnecting={activity.connectionState === 'reconnecting'}
              onClose={() =>
                updateSearch((next) => next.delete('activity'), true)
              }
              timing={timing}
              sourceStatus={workbench.data.source_status}
              onCancel={processingActive && currentJob?.job_id === visibleActivityJob.job_id ? () => void cancelCurrentJob() : undefined}
              cancelPending={mutations.cancelJob.isPending}
              liveActivity={liveActivity}
              projection={activityProjection}
              onOpenProcessing={() =>
                updateSearch((next) => next.set('panel', 'processing'))
              }
            />
          </div>
        )}
      </div>

      {batchMode &&
        !batchFormOpen &&
        !currentJob &&
        selectedTargets.length > 0 && (
          <div
            className="textbook-workbench-batch"
            role="region"
            aria-label="批量生成"
          >
            <span className="text-sm">
              已选择 {selectedTargets.length} 个知识点
            </span>
            <Button
              className="min-h-11"
              onClick={() => {
                setBatchFormOpen(true);
                setNavigatorOpen(false);
              }}
            >
              生成所选讲义
            </Button>
          </div>
        )}
    </main>
  );
}
