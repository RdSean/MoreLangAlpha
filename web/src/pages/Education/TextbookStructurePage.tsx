import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { AlertTriangle, BookOpenCheck, Check, CheckCircle2, ChevronDown, ChevronRight, ChevronsDownUp, ChevronsUpDown, CircleHelp, Clock3, FileText, GitMerge, ListTree, Loader2, PanelLeftClose, PanelLeftOpen, Plus, RefreshCcw, Save, Scissors, Trash2, WandSparkles } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { useToast } from '@/components/ui/use-toast';
import { cn } from '@/lib/utils';
import EducationMarkdown from './components/EducationMarkdown';
import ProcessingProfileDialog, { type ProcessingProfileValue } from './components/ProcessingProfileDialog';
import TextbookWorkflowStepper, { type TextbookWorkflowStep } from './components/TextbookWorkflowStepper';
import { useKnowledgePointLessonByPoint, useKnowledgePointSourcePreview, useLatestTextbookStructure, useStructureGenerationJob, useStructureGenerationProgress, useStructureMutations } from './queries';
import type { KnowledgePointSourcePreview, StructureGenerationJob, TextbookKnowledgePoint, TextbookStructureUnit } from './types';
import './TextbookStructurePage.css';

function messageOf(error: unknown, fallback: string) {
  return error instanceof Error && error.message ? error.message : fallback;
}

const structureWarningLabels: Record<string, string> = {
  knowledge_point_source_refs_missing: '部分知识点没有来源引用，已保留内容供人工确认。',
  source_quote_ambiguous_first_match_used: '部分引用在原文中出现多次，已采用首个匹配位置。',
  source_quote_unresolved: '部分引用暂时无法定位到解析 Markdown，原文摘录已保留。',
  unit_slug_deduplicated: '部分 Unit 标识重复，已自动生成唯一标识。',
  unit_source_refs_missing: '部分 Unit 没有来源引用，已保留内容供人工确认。',
  unit_type_promoted: '部分 Unit 类型无法识别，已按教学单元处理。',
};

function structureWarningLabel(warning: string) {
  return structureWarningLabels[warning] ?? `已自动处理：${warning.replaceAll('_', ' ')}`;
}

function sourceRefRange(ref: { start?: number | null; end?: number | null }) {
  return ref.start != null && ref.end != null
    ? `[${ref.start}:${ref.end}]`
    : '未定位偏移';
}

function ActionTip({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex" title={label}>
          {children}
        </span>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-[240px] leading-5">
        {label}
      </TooltipContent>
    </Tooltip>
  );
}

function HoverScrollText({ text, className = '' }: { text: string; className?: string }) {
  const containerRef = useRef<HTMLSpanElement>(null);
  const textRef = useRef<HTMLSpanElement>(null);
  const [distance, setDistance] = useState(0);
  const [hovered, setHovered] = useState(false);

  useLayoutEffect(() => {
    const measure = () => {
      const container = containerRef.current;
      const content = textRef.current;
      if (!container || !content) return;
      setDistance(Math.max(0, content.scrollWidth - container.clientWidth));
    };
    measure();
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(measure);
    if (containerRef.current) observer.observe(containerRef.current);
    if (textRef.current) observer.observe(textRef.current);
    return () => observer.disconnect();
  }, [text]);

  return (
    <span
      ref={containerRef}
      className={`block min-w-0 max-w-full overflow-hidden ${className}`}
      title={text}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <span
        ref={textRef}
        className="block w-max whitespace-nowrap"
        style={{
          transform: hovered && distance > 0 ? `translateX(-${distance}px)` : 'translateX(0)',
          transition: `transform ${Math.max(350, Math.min(1400, distance * 4))}ms linear`,
        }}
      >
        {text}
      </span>
    </span>
  );
}

function cloneUnits(units: TextbookStructureUnit[]): TextbookStructureUnit[] {
  return units.map((unit) => ({
    ...unit,
    source_refs: [...unit.source_refs],
    knowledge_points: unit.knowledge_points.map((point) => ({
      ...point,
      source_refs: [...point.source_refs],
    })),
  }));
}

type StructureTimelineStatus = 'queued' | 'preparing' | 'running' | 'validating' | 'completed' | 'failed' | 'cancelled';

const timelineStages: Array<{ id: string; label: string }> = [
  { id: 'queued', label: '任务已排队' },
  { id: 'preparing', label: '准备解析输入' },
  { id: 'running', label: '分析教材结构' },
  { id: 'validating', label: '校验并归档结果' },
  { id: 'done', label: '进入人工审阅' },
];

function timelineStageIndex(status: StructureTimelineStatus | undefined) {
  switch (status) {
    case 'queued': return 0;
    case 'preparing': return 1;
    case 'running': return 2;
    case 'validating': return 3;
    case 'completed': return 4;
    default: return -1;
  }
}

function formatElapsed(from: string | null | undefined, to: string | null | undefined) {
  if (!from) return undefined;
  const start = new Date(from).getTime();
  const end = to ? new Date(to).getTime() : Date.now();
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) return undefined;
  const totalSeconds = Math.floor((end - start) / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return minutes > 0 ? `${minutes} 分 ${seconds} 秒` : `${seconds} 秒`;
}

function StructureGenerationTimeline({ job }: { job: StructureGenerationJob }) {
  const activeIndex = timelineStageIndex(job.status);
  const failed = job.status === 'failed' || job.status === 'cancelled';
  const elapsed = formatElapsed(job.started_at ?? job.created_at, job.updated_at);
  return (
    <div className="textbook-timeline" data-testid="structure-generation-timeline">
      {timelineStages.map((stage, index) => {
        const done = !failed && activeIndex > index;
        const active = !failed && activeIndex === index;
        const stageFailed = failed && index === Math.max(activeIndex, 0);
        return (
          <div
            key={stage.id}
            className={cn(
              'textbook-timeline-row',
              done && 'is-done',
              active && 'is-active',
              stageFailed && 'is-failed',
            )}
          >
            <span className="textbook-timeline-dot">
              {done
                ? <Check className="size-3" />
                : active
                  ? <Loader2 className="size-3 animate-spin" />
                  : stageFailed
                    ? <AlertTriangle className="size-3" />
                    : <span className="size-1.5 rounded-full bg-current" />}
            </span>
            <span className="min-w-0 truncate">{stage.label}</span>
            {active && <span className="textbook-timeline-time">进行中</span>}
          </div>
        );
      })}
      <p className="mt-2 font-mono text-[11px] text-muted-foreground">
        状态 {job.status} · 第 {job.attempt_count} 次尝试
        {elapsed ? ` · 已耗时 ${elapsed}` : ''}
      </p>
      {job.heartbeat_at && (
        <p className="font-mono text-[11px] text-muted-foreground">
          最近心跳 {new Date(job.heartbeat_at).toLocaleTimeString()}
        </p>
      )}
      {job.error_message && (
        <p className="mt-1 text-xs" style={{ color: 'var(--color-loss)' }}>{job.error_message}</p>
      )}
    </div>
  );
}

const progressStatusIcon: Record<string, ReactNode> = {
  completed: <Check className="size-3" />,
  failed: <AlertTriangle className="size-3" />,
  running: <Loader2 className="size-3 animate-spin" />,
  skipped: <span className="size-1.5 rounded-full bg-current opacity-60" />,
};

function StructureActivityPanel({
  jobId,
  job,
}: {
  jobId: string | undefined;
  job: StructureGenerationJob;
}) {
  const progress = useStructureGenerationProgress(jobId, Boolean(jobId));
  const running = ['queued', 'preparing', 'running', 'validating'].includes(job.status);
  const [expanded, setExpanded] = useState(true);
  const [showAll, setShowAll] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const events = progress.data?.events ?? [];
  const visibleEvents = !showAll && events.length > 12 ? events.slice(-8) : events;
  const hiddenCount = events.length - visibleEvents.length;

  useEffect(() => {
    setExpanded(running);
  }, [running]);

  useEffect(() => {
    const node = listRef.current;
    if (!node || !running) return;
    node.scrollTop = node.scrollHeight;
  }, [running, events.length]);

  return (
    <div className="textbook-activity-panel" data-testid="structure-activity-panel">
      <div className="textbook-activity-header">
        <div className="min-w-0">
          <p className="text-sm font-medium">处理活动</p>
          <p className="text-xs text-muted-foreground">
            {running
              ? '正在同步服务端处理事件，可关闭页面，任务会继续。'
              : events.length > 0
                ? `已完成 ${events.length} 个可读处理步骤。`
                : '暂无可读处理事件。'}
          </p>
        </div>
        <button
          type="button"
          className="textbook-activity-toggle"
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? '收起' : '展开'}
          <ChevronDown className={cn('size-3.5 transition-transform', expanded && 'rotate-180')} />
        </button>
      </div>
      {expanded && (
        <>
          <div className="textbook-activity-list" ref={listRef} data-testid="structure-activity-list">
            {progress.isPending ? (
              <p className="textbook-activity-empty">
                <Loader2 className="mr-2 inline size-3 animate-spin" />
                正在读取处理活动…
              </p>
            ) : progress.isError ? (
              <p className="textbook-activity-empty">暂时无法读取处理活动。</p>
            ) : events.length === 0 ? (
              <p className="textbook-activity-empty">
                {running ? '任务已启动，等待首个处理事件…' : '没有记录到可读处理事件。'}
              </p>
            ) : (
              <>
                {hiddenCount > 0 && (
                  <button
                    type="button"
                    className="textbook-activity-more"
                    onClick={() => setShowAll(true)}
                  >
                    还有 {hiddenCount} 条较早记录，展开查看
                  </button>
                )}
                {visibleEvents.map((event) => (
                  <div
                    key={`${event.sequence}-${event.label}`}
                    className={cn(
                      'textbook-activity-row',
                      event.status === 'running' && 'is-running',
                      event.status === 'failed' && 'is-failed',
                    )}
                  >
                    <span className="textbook-activity-dot">
                      {progressStatusIcon[event.status] ?? <span className="size-1.5 rounded-full bg-current" />}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate" title={event.label}>
                        {event.label}
                        {event.count > 1 && (
                          <span className="ml-1.5 font-mono text-[11px] text-muted-foreground">×{event.count}</span>
                        )}
                      </p>
                      {event.detail && (
                        <p className="truncate font-mono text-[11px] text-muted-foreground" title={event.detail}>
                          {event.detail}
                        </p>
                      )}
                    </div>
                    {event.timestamp && (
                      <span className="textbook-timeline-time shrink-0">
                        {new Date(event.timestamp).toLocaleTimeString()}
                      </span>
                    )}
                  </div>
                ))}
              </>
            )}
          </div>
          {progress.data?.truncated && (
            <p className="mt-2 text-[11px] text-muted-foreground">只展示最近的处理记录。</p>
          )}
        </>
      )}
    </div>
  );
}

function KnowledgePointSourcePreviewPanel({
  preview,
  isLoading,
  isError,
}: {
  preview: KnowledgePointSourcePreview | undefined;
  isLoading: boolean;
  isError: boolean;
}) {
  if (isLoading) {
    return (
      <div className="flex min-h-[320px] items-center justify-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" />
        正在读取原文依据…
      </div>
    );
  }
  if (isError) {
    return (
      <p className="px-5 py-8 text-sm" style={{ color: 'var(--color-loss)' }}>
        暂时无法读取原文依据，请稍后重试。
      </p>
    );
  }
  if (!preview || preview.snippets.length === 0) {
    return (
      <div className="flex min-h-[320px] items-center justify-center px-6 py-12">
        <div className="max-w-md text-center">
          <div className="mx-auto flex size-12 items-center justify-center rounded-full" style={{ backgroundColor: 'var(--color-bg-subtle)', color: 'var(--color-accent-primary)' }}>
            <FileText className="size-5" />
          </div>
          <h2 className="title-font mt-4 text-lg font-semibold">暂无原文依据</h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            这个知识点没有可定位的原文摘录。可以先生成课程，或回到 Unit 列表补充来源引用。
          </p>
        </div>
      </div>
    );
  }
  return (
    <div className="mx-auto grid max-w-[920px] gap-4 px-5 py-6 lg:px-10">
      {preview.snippets.map((snippet, index) => (
        <article key={`${snippet.source_id}-${index}`} className="textbook-source-snippet">
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
            <span className="truncate font-medium text-foreground">
              {snippet.source_title || snippet.source_id}
            </span>
            <span className="font-mono">
              {snippet.start != null && snippet.end != null
                ? `Markdown [${snippet.start}:${snippet.end}]`
                : '未定位偏移'}
            </span>
          </div>
          {snippet.quote && (
            <p className="textbook-source-quote mt-3 text-sm leading-6">{snippet.quote}</p>
          )}
          <div className="textbook-source-markdown">
            {snippet.truncated_before && (
              <p className="mb-1 text-xs text-muted-foreground">…前文已省略…</p>
            )}
            <EducationMarkdown content={snippet.markdown} variant="compact" className="text-sm leading-6" />
            {snippet.truncated_after && (
              <p className="mt-1 text-xs text-muted-foreground">…后文已省略…</p>
            )}
          </div>
        </article>
      ))}
    </div>
  );
}

function KnowledgePointWorkspace({
  textbookId,
  versionId,
  unit,
  point,
  structureStatus,
  onDelete,
  onSave,
  onAccept,
  isSaving,
  isAccepting,
}: {
  textbookId: string | undefined;
  versionId: string | undefined;
  unit: TextbookStructureUnit;
  point: TextbookKnowledgePoint;
  structureStatus: string;
  onDelete: (() => void) | undefined;
  onSave: () => void;
  onAccept: () => void;
  isSaving: boolean;
  isAccepting: boolean;
}) {
  const [jobId, setJobId] = useState<string>();
  const [autoGrading, setAutoGrading] = useState(false);
  const [activeTab, setActiveTab] = useState<'lesson' | 'source'>('lesson');
  const [tabTouched, setTabTouched] = useState(false);
  const lesson = useKnowledgePointLessonByPoint(point.knowledge_point_id, true);
  const sourcePreview = useKnowledgePointSourcePreview(point.knowledge_point_id, true);
  const generation = useStructureGenerationJob(jobId, Boolean(jobId));
  const mutations = useStructureMutations();
  const { toast } = useToast();

  useEffect(() => {
    if (generation.data?.status !== 'completed') return;
    void lesson.refetch();
  }, [generation.data?.status, lesson]);

  const generate = async () => {
    try {
      const job = await mutations.generateLesson.mutateAsync({
        knowledgePointId: point.knowledge_point_id,
        autoGrading,
      });
      setJobId(job.generation_job_id);
    } catch (error) {
      toast({
        variant: 'destructive',
        title: '无法生成课程',
        description: messageOf(error, '请稍后重试。'),
      });
    }
  };

  const generating = generation.data?.status === 'queued'
    || generation.data?.status === 'preparing'
    || generation.data?.status === 'running'
    || generation.data?.status === 'validating';

  useEffect(() => {
    setTabTouched(false);
    setActiveTab('lesson');
    setJobId(undefined);
  }, [point.knowledge_point_id]);

  useEffect(() => {
    if (tabTouched || lesson.isLoading) return;
    setActiveTab(lesson.data ? 'lesson' : 'source');
  }, [lesson.data, lesson.isLoading, tabTouched]);

  const selectTab = (tab: 'lesson' | 'source') => {
    setTabTouched(true);
    setActiveTab(tab);
  };

  return (
    <section className="min-h-0 min-w-0 overflow-y-auto">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b px-5 py-5 lg:px-8" style={{ borderColor: 'var(--color-border-muted)' }}>
        <div className="min-w-0">
          <p className="font-mono text-[11px] text-muted-foreground">
            Unit {unit.position} · {unit.title}
          </p>
          <h1 className="title-font mt-2 text-2xl font-semibold">{point.title}</h1>
          <p className="mt-1 text-sm text-muted-foreground">{point.summary || '暂无知识点说明'}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {lesson.data && (
            <span className="inline-flex h-8 items-center gap-1.5 rounded-md border px-2.5 text-xs" style={{ borderColor: lesson.data.status === 'approved' ? 'var(--color-success)' : 'var(--color-border-muted)', color: lesson.data.status === 'approved' ? 'var(--color-success)' : 'var(--color-text-secondary)' }}>
              {lesson.data.status === 'approved' ? <CheckCircle2 className="size-3.5" /> : <Clock3 className="size-3.5" />}
              {lesson.data.status === 'approved' ? '课程已通过' : '课程待审阅'}
            </span>
          )}
          <Link
            to={`/textbooks/${textbookId}/versions/${versionId}/knowledge/${point.knowledge_point_id}`}
            className="inline-flex h-8 items-center gap-1.5 rounded-md border px-2.5 text-xs hover:bg-[var(--color-bg-hover)]"
            style={{ borderColor: 'var(--color-border-muted)' }}
          >
            <FileText className="size-3.5" />
            打开完整审阅页
          </Link>
          {structureStatus === 'review' && onDelete && (
            <ActionTip label="删除知识点：只删除当前草稿中的这一项；保存或接受结构后才会写入数据库。删除后顺序号会自动重排。">
              <Button
                type="button"
                variant="outline"
                size="sm"
                aria-label={`删除知识点 ${point.title}`}
                onClick={onDelete}
              >
                <Trash2 className="mr-2 size-3.5" />
              删除
            </Button>
            </ActionTip>
          )}
          {structureStatus === 'review' && (
            <>
              <ActionTip label="保存整个教材结构：会把本次修改的全部 Unit 和知识点一起写入，不是只保存当前 Unit。">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={onSave}
                  disabled={isSaving || isAccepting}
                >
                  <Save className="mr-2 size-3.5" />
                  {isSaving ? '正在保存' : '保存结构'}
                </Button>
              </ActionTip>
              <ActionTip label="接受整个教材结构：会一次性确认全部 Unit 和知识点，接受后结构不能再编辑，只能逐知识点生成课程。">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={onAccept}
                  disabled={isSaving || isAccepting}
                >
                  <CheckCircle2 className="mr-2 size-3.5" />
                  {isAccepting ? '正在接受' : '接受结构'}
                </Button>
              </ActionTip>
            </>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-b px-5 py-3 lg:px-8" style={{ borderColor: 'var(--color-border-muted)' }}>
        <div className="textbook-structure-tabs" role="tablist" aria-label="知识点内容视图">
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'lesson'}
            className={cn('textbook-structure-tab', activeTab === 'lesson' && 'is-active')}
            onClick={() => selectTab('lesson')}
          >
            课程
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'source'}
            className={cn('textbook-structure-tab', activeTab === 'source' && 'is-active')}
            onClick={() => selectTab('source')}
          >
            原文依据
          </button>
        </div>
        {point.source_refs.length > 0 && (
          <span className="font-mono text-[11px] text-muted-foreground">
            {point.source_refs.length} 条来源引用
          </span>
        )}
      </div>

      {activeTab === 'source' ? (
        <KnowledgePointSourcePreviewPanel
          preview={sourcePreview.data}
          isLoading={sourcePreview.isLoading}
          isError={sourcePreview.isError}
        />
      ) : lesson.isLoading ? (
        <div className="flex min-h-[520px] items-center justify-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" />
          正在读取课程 Markdown…
        </div>
      ) : lesson.data ? (
        <article className="mx-auto max-w-[920px] px-5 py-8 lg:px-10">
          <EducationMarkdown content={lesson.data.content_markdown} variant="lesson" className="text-base leading-7" />
        </article>
      ) : (
        <div className="flex min-h-[560px] items-center justify-center px-6 py-12">
          <div className="max-w-md text-center">
            <div className="mx-auto flex size-14 items-center justify-center rounded-full" style={{ backgroundColor: 'var(--color-bg-subtle)', color: 'var(--color-accent-primary)' }}>
              <BookOpenCheck className="size-6" />
            </div>
            <span className="mt-4 inline-flex rounded border px-2 py-1 font-mono text-[10px] uppercase tracking-wide text-muted-foreground" style={{ borderColor: 'var(--color-border-muted)' }}>
              {structureStatus === 'accepted' ? 'ready' : 'structure review'}
            </span>
            <h2 className="title-font mt-3 text-xl font-semibold">
              {structureStatus === 'accepted' ? '准备就绪' : '还没有课程 Markdown'}
            </h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              {structureStatus === 'accepted'
                ? '这个知识点还没有课程 Markdown。点击下方按钮，让 book-to-skill 基于已确认的来源片段生成完整课程。'
                : '结构还在审阅中。可以先查看“原文依据”，确认拆分和合并是否合理，再决定是否接受结构。'}
            </p>
            {structureStatus === 'accepted' ? (
              <>
                <label className="mt-5 inline-flex items-center gap-2 text-sm text-muted-foreground">
                  <input type="checkbox" checked={autoGrading} onChange={(event) => setAutoGrading(event.target.checked)} />
                  同时生成自动判题练习
                </label>
                <div className="mt-5">
                  <Button onClick={() => void generate()} disabled={generating || mutations.generateLesson.isPending}>
                    {generating ? <Loader2 className="mr-2 size-4 animate-spin" /> : <WandSparkles className="mr-2 size-4" />}
                    {generating ? '正在生成课程' : '生成课程'}
                  </Button>
                </div>
              </>
            ) : (
              <Button className="mt-5" variant="outline" onClick={() => selectTab('source')}>
                <FileText className="mr-2 size-4" />
                查看原文依据
              </Button>
            )}
            {generation.data?.status === 'failed' && (
              <p className="mt-4 text-sm" style={{ color: 'var(--color-loss)' }}>
                {generation.data.error_message ?? '课程生成失败，请重试。'}
              </p>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

export default function TextbookStructurePage() {
  const { textbookId, versionId } = useParams();
  const [jobId, setJobId] = useState<string>();
  const [profileOpen, setProfileOpen] = useState(false);
  const [units, setUnits] = useState<TextbookStructureUnit[]>([]);
  const [selectedUnitId, setSelectedUnitId] = useState<string>();
  const [selectedPointId, setSelectedPointId] = useState<string>();
  const [expandedUnitIds, setExpandedUnitIds] = useState<Set<string>>(new Set());
  const [treeCollapsed, setTreeCollapsed] = useState(false);
  const [structureSubmitting, setStructureSubmitting] = useState(false);
  const structure = useLatestTextbookStructure(versionId, true);
  const activeJobId = jobId ?? structure.data?.latest_generation_job_id ?? undefined;
  const generation = useStructureGenerationJob(activeJobId, Boolean(activeJobId));
  const mutations = useStructureMutations();
  const { toast } = useToast();

  const activeJob = (() => {
    if (generation.data && ['queued', 'preparing', 'running', 'validating'].includes(generation.data.status)) {
      return generation.data;
    }
    const summary = structure.data?.latest_generation_job;
    if (summary && ['queued', 'preparing', 'running', 'validating'].includes(summary.status)) {
      return summary as StructureGenerationJob;
    }
    return undefined;
  })();

  useEffect(() => {
    if (!structure.data) return;
    setUnits(cloneUnits(structure.data.units));
    const initialUnit = structure.data.units.find((unit) => unit.knowledge_points.length > 0)
      ?? structure.data.units[0];
    setSelectedUnitId((current) => current ?? initialUnit?.unit_id);
    setSelectedPointId((current) => current ?? initialUnit?.knowledge_points[0]?.knowledge_point_id);
    setExpandedUnitIds((current) => current.size > 0 || !initialUnit
      ? current
      : new Set([initialUnit.unit_id]));
    // The structure identity/status are the stable reload keys; using the whole
    // query object here would refetch-sync on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [structure.data?.status, structure.data?.structure_id]);

  useEffect(() => {
    if (generation.data?.status !== 'completed') return;
    void structure.refetch();
  }, [generation.data?.status, structure]);

  const selectedUnit = useMemo(
    () => units.find((unit) => unit.unit_id === selectedUnitId) ?? units[0],
    [selectedUnitId, units],
  );
  const selectedPoint = useMemo(
    () => units
      .flatMap((unit) => unit.knowledge_points)
      .find((point) => point.knowledge_point_id === selectedPointId),
    [selectedPointId, units],
  );

  const toggleUnit = (unitId: string) => {
    setExpandedUnitIds((current) => {
      const next = new Set(current);
      if (next.has(unitId)) next.delete(unitId);
      else next.add(unitId);
      return next;
    });
  };

  const selectUnit = (unitId: string) => {
    setSelectedUnitId(unitId);
    setSelectedPointId(undefined);
  };

  const selectPoint = (unitId: string, pointId: string) => {
    setSelectedUnitId(unitId);
    setSelectedPointId(pointId);
  };

  const setAllUnitsExpanded = (expanded: boolean) => {
    setExpandedUnitIds(expanded
      ? new Set(units.map((unit) => unit.unit_id))
      : new Set());
  };

  const updateUnit = (patch: Partial<TextbookStructureUnit>) => {
    setUnits((current) => current.map((unit) => unit.unit_id === selectedUnit?.unit_id ? { ...unit, ...patch } : unit));
  };

  const updateKnowledgePoint = (knowledgePointId: string, patch: Partial<TextbookKnowledgePoint>) => {
    setUnits((current) => current.map((unit) => unit.unit_id === selectedUnit?.unit_id ? {
      ...unit,
      knowledge_points: unit.knowledge_points.map((point) => point.knowledge_point_id === knowledgePointId ? { ...point, ...patch } : point),
    } : unit));
  };

  const addKnowledgePoint = () => {
    if (!selectedUnit) return;
    const position = Math.max(0, ...selectedUnit.knowledge_points.map((point) => point.position)) + 1;
    const sourceRefs = selectedUnit.source_refs.length ? selectedUnit.source_refs : [{ source_id: 'source', start: 0, end: 1 }];
    const point: TextbookKnowledgePoint = {
      knowledge_point_id: crypto.randomUUID(),
      position,
      slug: `knowledge-point-${position}`,
      title: '新知识点',
      summary: '',
      source_refs: sourceRefs,
      confidence: 1,
      status: 'review',
    };
    updateUnit({ knowledge_points: [...selectedUnit.knowledge_points, point] });
  };

  const deleteKnowledgePoint = (knowledgePointId: string) => {
    if (!selectedUnit) return;
    const remaining = selectedUnit.knowledge_points
      .filter((point) => point.knowledge_point_id !== knowledgePointId)
      .map((point, position) => ({ ...point, position: position + 1 }));
    updateUnit({ knowledge_points: remaining });
  };

  const splitKnowledgePoint = (knowledgePoint: TextbookKnowledgePoint) => {
    if (!selectedUnit) return;
    const index = selectedUnit.knowledge_points.findIndex((point) => point.knowledge_point_id === knowledgePoint.knowledge_point_id);
    const split = {
      ...knowledgePoint,
      knowledge_point_id: crypto.randomUUID(),
      position: knowledgePoint.position + 1,
      slug: `${knowledgePoint.slug}-split`,
      title: `${knowledgePoint.title}（拆分）`,
      source_refs: [...knowledgePoint.source_refs],
      status: 'review' as const,
    };
    const knowledge_points = [...selectedUnit.knowledge_points];
    knowledge_points.splice(index + 1, 0, split);
    updateUnit({ knowledge_points: knowledge_points.map((point, position) => ({ ...point, position: position + 1 })) });
  };

  const mergeKnowledgePointWithPrevious = (knowledgePoint: TextbookKnowledgePoint) => {
    if (!selectedUnit) return;
    const index = selectedUnit.knowledge_points.findIndex((point) => point.knowledge_point_id === knowledgePoint.knowledge_point_id);
    if (index <= 0) return;
    const previous = selectedUnit.knowledge_points[index - 1];
    const merged = {
      ...previous,
      title: `${previous.title} / ${knowledgePoint.title}`,
      source_refs: [...previous.source_refs, ...knowledgePoint.source_refs],
    };
    const knowledge_points = selectedUnit.knowledge_points
      .filter((point) => ![previous.knowledge_point_id, knowledgePoint.knowledge_point_id].includes(point.knowledge_point_id));
    knowledge_points.splice(index - 1, 0, merged);
    updateUnit({ knowledge_points: knowledge_points.map((point, position) => ({ ...point, position: position + 1 })) });
  };

  const deleteUnit = (unitId: string) => {
    const target = units.find((unit) => unit.unit_id === unitId);
    if (!target) return;
    if (!window.confirm(`删除「${target.title}」及其 ${target.knowledge_points.length} 个知识点？保存或接受结构后才会写入数据库。`)) return;
    const remaining = units
      .filter((unit) => unit.unit_id !== unitId)
      .map((unit, position) => ({ ...unit, position: position + 1 }));
    setUnits(remaining);
    const next = remaining[0];
    setSelectedUnitId(next?.unit_id);
    setSelectedPointId(undefined);
  };

  const createStructure = async (profile: ProcessingProfileValue) => {
    if (!versionId) return;
    if (structureSubmitting || activeJob) return;
    setStructureSubmitting(true);
    try {
      const job = await mutations.create.mutateAsync({ versionId, profile: profile as unknown as Record<string, unknown> });
      setProfileOpen(false);
      setJobId(job.generation_job_id);
    } catch (error) {
      toast({ variant: 'destructive', title: '无法生成教材结构', description: messageOf(error, '请稍后重试。') });
    } finally {
      setStructureSubmitting(false);
    }
  };

  const resumeStructure = async (generationJobIdOverride?: string) => {
    const generationJobId = generationJobIdOverride ?? structure.data?.latest_generation_job_id;
    if (!generationJobId || structureSubmitting || activeJob) return;
    setStructureSubmitting(true);
    try {
      const job = await mutations.resumeStructure.mutateAsync(generationJobId);
      setJobId(job.generation_job_id);
      await structure.refetch();
    } catch (error) {
      toast({ variant: 'destructive', title: '无法继续结构分析', description: messageOf(error, '请稍后重试。') });
    } finally {
      setStructureSubmitting(false);
    }
  };

  const generateBookAssets = async () => {
    if (!structure.data) return;
    try {
      const job = await mutations.generateBookAssets.mutateAsync(structure.data.structure_id);
      setJobId(job.generation_job_id);
      toast({ title: '知识包生成任务已启动' });
      await structure.refetch();
    } catch (error) {
      toast({ variant: 'destructive', title: '无法生成教材知识包', description: messageOf(error, '请稍后重试。') });
    }
  };

  const saveStructure = async () => {
    if (!structure.data) return;
    try {
      await mutations.save.mutateAsync({ structureId: structure.data.structure_id, units });
      toast({ title: '结构修改已保存' });
    } catch (error) {
      toast({ variant: 'destructive', title: '无法保存结构', description: messageOf(error, '请检查知识点后重试。') });
    }
  };

  const acceptStructure = async () => {
    if (!structure.data) return;
    try {
      await mutations.save.mutateAsync({ structureId: structure.data.structure_id, units });
      await mutations.accept.mutateAsync(structure.data.structure_id);
    } catch (error) {
      toast({ variant: 'destructive', title: '无法接受结构', description: messageOf(error, '至少保留一个知识点。') });
    }
  };

  if (structure.isLoading) {
    return <main className="h-full overflow-y-auto bg-canvas p-8 text-sm text-muted-foreground">正在加载教材结构…</main>;
  }

  if (!structure.data && !jobId) {
    return <main className="h-full overflow-y-auto bg-canvas" data-testid="textbook-structure-page"><div className="mx-auto max-w-3xl px-6 py-12"><Link to={`/textbooks/${textbookId}`} className="text-sm text-muted-foreground">返回教材</Link><h1 className="title-font mt-6 text-2xl font-semibold">生成教材结构</h1><p className="mt-3 text-sm leading-6 text-muted-foreground">先从 Markdown 中识别 Unit、知识点和来源定位。非教学单元可以没有知识点，生成后再由你审阅。</p><Button className="mt-6" onClick={() => setProfileOpen(true)} disabled={structureSubmitting || mutations.create.isPending}><WandSparkles className="mr-2 size-4" />{structureSubmitting || mutations.create.isPending ? '正在创建任务' : '开始结构分析'}</Button><ProcessingProfileDialog open={profileOpen} onOpenChange={setProfileOpen} onConfirm={createStructure} /></div></main>;
  }

  if (!structure.data && generation.data) {
    return <main className="h-full overflow-y-auto bg-canvas" data-testid="textbook-structure-page"><div className="mx-auto max-w-3xl px-6 py-12"><h1 className="title-font text-2xl font-semibold">正在分析教材结构</h1><p className="mt-3 text-sm leading-6 text-muted-foreground">任务已提交，下面会显示当前进度；可以关闭页面，处理会继续在后台进行。</p><div className="mt-6 grid gap-4 rounded-lg border p-4" style={{ borderColor: 'var(--color-border-muted)' }}><StructureGenerationTimeline job={generation.data} /><StructureActivityPanel jobId={generation.data.generation_job_id} job={generation.data} /></div>{generation.data.status === 'failed' && <Button className="mt-6" onClick={() => void resumeStructure(generation.data.generation_job_id)} disabled={structureSubmitting || mutations.resumeStructure.isPending}><RefreshCcw className="mr-2 size-4" />{structureSubmitting || mutations.resumeStructure.isPending ? '正在继续' : '重新运行结构分析'}</Button>}</div></main>;
  }

  const data = structure.data;
  if (!data) return null;
  const readOnly = data.status === 'accepted';
  const lessonSummary = data.lesson_summary ?? { total: 0, accepted: 0, generated: 0, approved: 0 };
  const warningCounts = new Map<string, number>();
  for (const warning of data.validation_warnings ?? []) {
    warningCounts.set(warning, (warningCounts.get(warning) ?? 0) + 1);
  }
  const steps: TextbookWorkflowStep[] = [
    { id: 'content', label: '内容准备', status: 'completed' },
    {
      id: 'structure',
      label: '结构分析',
      status:
        data.status === 'failed'
          ? 'failed'
          : data.status === 'queued' || data.status === 'running'
            ? 'in_progress'
            : 'completed',
    },
    {
      id: 'lessons',
      label: '知识点课程',
      status:
        data.status === 'accepted'
          ? lessonSummary.accepted > 0 &&
            lessonSummary.approved === lessonSummary.accepted
            ? 'completed'
            : 'in_progress'
          : 'pending',
    },
    { id: 'publish', label: '发布', status: 'pending' },
  ];
  if (activeJob && (data.status === 'queued' || data.status === 'running')) {
    return (
      <main className="h-full overflow-y-auto bg-canvas" data-testid="textbook-structure-page">
        <div className="mx-auto w-full max-w-3xl px-6 py-12">
          <Link to={`/textbooks/${textbookId}`} className="text-sm text-muted-foreground">返回教材</Link>
          <div className="mt-6">
            <TextbookWorkflowStepper steps={steps} />
          </div>
          <h1 className="title-font mt-8 text-2xl font-semibold">正在分析教材结构</h1>
          <p className="mt-3 text-sm leading-6 text-muted-foreground">任务已提交，下面会显示当前进度；可以关闭页面，处理会继续在后台进行。</p>
          <div className="mt-6 grid gap-4 rounded-lg border p-4 lg:grid-cols-[minmax(260px,340px)_minmax(0,1fr)]" style={{ borderColor: 'var(--color-border-muted)' }}>
            <div className="min-w-0">
              <StructureGenerationTimeline job={activeJob} />
            </div>
            <StructureActivityPanel jobId={activeJob.generation_job_id} job={activeJob} />
          </div>
        </div>
      </main>
    );
  }
  if (!selectedUnit) {
    return (
      <main className="h-full overflow-y-auto bg-canvas" data-testid="textbook-structure-page">
        <div className="mx-auto w-full max-w-3xl px-6 py-12">
          <Link to={`/textbooks/${textbookId}`} className="text-sm text-muted-foreground">返回教材</Link>
          <div className="mt-6">
            <TextbookWorkflowStepper steps={steps} />
          </div>
          <h1 className="title-font mt-8 text-2xl font-semibold">结构暂无可审阅内容</h1>
          <p className="mt-3 text-sm leading-6 text-muted-foreground">
            {data.status === 'failed'
              ? '结构分析没有生成可审阅的 Unit，请重新运行结构分析。'
              : '结构分析尚未产生 Unit。'}
          </p>
            {data.status === 'failed' && data.latest_generation_job_id && (
            <Button className="mt-6" onClick={() => void resumeStructure()} disabled={structureSubmitting || mutations.resumeStructure.isPending}>
              <RefreshCcw className="mr-2 size-4" />
              {structureSubmitting || mutations.resumeStructure.isPending ? '正在继续' : '重新运行结构分析'}
            </Button>
          )}
        </div>
      </main>
    );
  }

  return (
    <TooltipProvider delayDuration={150}>
    <main className="flex h-full min-h-0 flex-col overflow-hidden bg-canvas" data-testid="textbook-structure-page">
      <div
        className="mx-auto w-full max-w-[1720px] shrink-0 border-b px-4 py-5 sm:px-8"
        style={{ borderColor: 'var(--color-border-muted)' }}
      >
        <Link to={`/textbooks/${textbookId}`} className="text-sm text-muted-foreground">返回教材</Link>
        <div className="mt-5">
          <TextbookWorkflowStepper steps={steps} />
        </div>
        {activeJob && (
          <div className="mt-4 grid gap-4 rounded-lg border p-4 lg:grid-cols-[minmax(260px,360px)_minmax(0,1fr)]" style={{ borderColor: 'var(--color-border-muted)' }} data-testid="structure-active-job">
            <div className="min-w-0">
              <p className="text-sm font-medium">教材结构处理进度</p>
              <p className="mb-3 text-xs text-muted-foreground">可以关闭页面，处理会继续在后台进行。</p>
              <StructureGenerationTimeline job={activeJob} />
            </div>
            <StructureActivityPanel jobId={activeJob.generation_job_id} job={activeJob} />
          </div>
        )}
      </div>
      {warningCounts.size > 0 && (
        <div
          className="shrink-0 border-b px-4 py-3 sm:px-8"
          data-testid="structure-warning-summary"
          style={{ borderColor: 'var(--color-border-muted)', background: 'var(--color-warning-soft)' }}
        >
          <div className="mx-auto flex w-full max-w-[1720px] items-start gap-3">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" style={{ color: 'var(--color-warning, #f59e0b)' }} />
            <div className="min-w-0">
              <p className="text-sm font-medium">结构已生成，但有 {warningCounts.size} 类需要留意的问题</p>
              <ul className="mt-2 grid gap-1 text-xs leading-5 text-muted-foreground">
                {[...warningCounts.entries()].map(([warning, count]) => (
                  <li key={warning}>
                    {structureWarningLabel(warning)}
                    {count > 1 ? `（${count} 处）` : ''}
                    <span className="ml-2 font-mono text-[10px] opacity-70">{warning}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}
      <div className={cn(
        'mx-auto grid min-h-0 w-full max-w-[1720px] flex-1 overflow-hidden',
        treeCollapsed
          ? 'lg:grid-cols-[56px_minmax(0,1fr)]'
          : 'lg:grid-cols-[360px_minmax(0,1fr)]',
      )}>
        <aside
          className={cn(
            'flex h-full min-h-0 min-w-0 flex-col overflow-hidden border-b lg:border-b-0 lg:border-r',
            treeCollapsed ? 'px-2 py-3' : '',
          )}
          style={{ borderColor: 'var(--color-border-muted)' }}
        >
          {treeCollapsed ? (
            <div className="flex h-full min-h-0 flex-col items-center">
              <button
                type="button"
                className="inline-flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-[var(--color-bg-hover)]"
                aria-label="展开知识点栏"
                title="展开知识点栏"
                onClick={() => setTreeCollapsed(false)}
              >
                <PanelLeftOpen className="size-4" />
              </button>
              <ListTree className="mt-3 size-4 text-muted-foreground" aria-hidden="true" />
            </div>
          ) : (
            <>
              <div className="shrink-0 border-b px-3 py-3" style={{ borderColor: 'var(--color-border-muted)' }}>
                <div className="flex min-w-0 items-center gap-2">
                  <ListTree className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                  <h1 className="title-font min-w-0 flex-1 truncate text-lg font-semibold">知识点</h1>
                  <ActionTip label="全部展开">
                    <button
                      type="button"
                      className="inline-flex size-7 items-center justify-center rounded-md text-muted-foreground hover:bg-[var(--color-bg-hover)]"
                      aria-label="全部展开"
                      onClick={() => setAllUnitsExpanded(true)}
                    >
                      <ChevronsUpDown className="size-3.5" />
                    </button>
                  </ActionTip>
                  <ActionTip label="全部收起">
                    <button
                      type="button"
                      className="inline-flex size-7 items-center justify-center rounded-md text-muted-foreground hover:bg-[var(--color-bg-hover)]"
                      aria-label="全部收起"
                      onClick={() => setAllUnitsExpanded(false)}
                    >
                      <ChevronsDownUp className="size-3.5" />
                    </button>
                  </ActionTip>
                  <ActionTip label="收起知识点栏">
                    <button
                      type="button"
                      className="inline-flex size-7 items-center justify-center rounded-md text-muted-foreground hover:bg-[var(--color-bg-hover)]"
                      aria-label="收起知识点栏"
                      onClick={() => setTreeCollapsed(true)}
                    >
                      <PanelLeftClose className="size-3.5" />
                    </button>
                  </ActionTip>
                </div>
                <p className="mt-2 font-mono text-xs text-muted-foreground">v{data.sequence} · {data.status}</p>
              </div>
              <nav className="min-h-0 min-w-0 flex-1 overflow-x-hidden overflow-y-auto px-3 py-2" aria-label="教材知识点树">
            {units.map((unit) => {
              const expanded = expandedUnitIds.has(unit.unit_id);
              const unitSelected = !selectedPoint && unit.unit_id === selectedUnit.unit_id;
              return (
                <div key={unit.unit_id} className="min-w-0 max-w-full overflow-hidden">
                  <div
                    className={cn('textbook-structure-tree-unit-row', unitSelected && 'is-active')}
                  >
                    <button
                      type="button"
                      className="inline-flex w-7 shrink-0 items-center justify-center text-muted-foreground hover:bg-[var(--color-bg-hover)]"
                      aria-label={`${expanded ? '收起' : '展开'} ${unit.title}`}
                      onClick={() => toggleUnit(unit.unit_id)}
                    >
                      {expanded ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
                    </button>
                    <button
                      type="button"
                      title={unit.title}
                      aria-label={`选择 ${unit.title}`}
                      onClick={() => {
                        selectUnit(unit.unit_id);
                        toggleUnit(unit.unit_id);
                      }}
                      className="textbook-structure-tree-unit min-w-0 flex-1"
                    >
                      <HoverScrollText
                        text={`${unit.position}. ${unit.title} (${unit.knowledge_points.length})`}
                        className="w-full font-medium"
                      />
                    </button>
                  </div>
                  {expanded && (
                    <div className="textbook-structure-tree-children ml-4 mt-0.5 grid gap-0.5 pl-1.5">
                      {unit.knowledge_points.length === 0 ? (
                        <p className="px-2 py-1.5 text-xs text-muted-foreground">无知识点</p>
                      ) : unit.knowledge_points.map((point) => {
                        const active = point.knowledge_point_id === selectedPointId;
                        const lessonStateClass = point.lesson_status === 'approved'
                          ? 'is-approved'
                          : point.lesson_revision_id
                            ? 'is-pending'
                            : active
                              ? 'is-current'
                              : null;
                        return (
                          <button
                            key={point.knowledge_point_id}
                            type="button"
                            title={point.title}
                            aria-label={`选择知识点 ${point.title}`}
                            onClick={() => selectPoint(unit.unit_id, point.knowledge_point_id)}
                            className={cn(
                              'textbook-structure-tree-point text-xs',
                              active && 'is-active',
                              lessonStateClass,
                            )}
                          >
                            <span className="w-4 shrink-0 text-right font-mono text-[10px] text-muted-foreground">{point.position}</span>
                            <HoverScrollText text={point.title} className="min-w-0 flex-1" />
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
              </nav>
              <div className="shrink-0 border-t p-2" style={{ borderColor: 'var(--color-border-muted)' }}>
                <div className="textbook-structure-view-switch">
                  <button type="button" className="is-active">
                    知识点学习
                  </button>
                  <button type="button" disabled title="后续开放">
                    个性化总结
                  </button>
                </div>
              </div>
            </>
          )}
        </aside>
        {selectedPoint ? (
          <KnowledgePointWorkspace
            textbookId={textbookId}
            versionId={versionId}
            unit={selectedUnit}
            point={selectedPoint}
            structureStatus={data.status}
            onDelete={() => {
              deleteKnowledgePoint(selectedPoint.knowledge_point_id);
              setSelectedPointId(undefined);
            }}
            onSave={() => void saveStructure()}
            onAccept={() => void acceptStructure()}
            isSaving={mutations.save.isPending}
            isAccepting={mutations.accept.isPending}
          />
        ) : (
        <div className="grid h-full min-h-0 min-w-0 overflow-hidden lg:grid-cols-[minmax(0,1fr)_300px]">
        <section className="h-full min-h-0 min-w-0 overflow-y-auto px-4 py-6 lg:px-8">
          <div className="flex flex-wrap items-end justify-between gap-4 border-b pb-5" style={{ borderColor: 'var(--color-border-muted)' }}>
            <label className="grid min-w-[320px] flex-1 gap-1.5">
              <span className="font-mono text-[11px] uppercase tracking-wide text-muted-foreground">当前 Unit</span>
              <input
                value={selectedUnit.title}
                disabled={readOnly}
                onChange={(event) => updateUnit({ title: event.target.value })}
                className="title-font min-h-11 w-full border bg-background px-3 text-xl font-semibold"
                aria-label="单元标题"
              />
            </label>
            <ActionTip label="添加知识点：在当前 Unit 末尾新增一个待审阅知识点。">
              <Button variant="outline" size="sm" onClick={addKnowledgePoint} disabled={readOnly}>
                <Plus className="mr-2 size-4" />添加知识点
              </Button>
            </ActionTip>
            <ActionTip label="删除当前 Unit：删除这个 Unit 及其全部知识点。删除只改动当前草稿，必须再点“保存结构”或“接受结构”才会写入数据库，否则刷新后会恢复。剩余 Unit 会重新编号。">
              <Button variant="outline" size="sm" onClick={() => deleteUnit(selectedUnit.unit_id)} disabled={readOnly}>
                <Trash2 className="mr-2 size-4" />删除 Unit
              </Button>
            </ActionTip>
          </div>
          <label className="mt-5 grid gap-1.5 text-sm">
            <span className="font-medium">单元说明</span>
            <textarea
              value={selectedUnit.summary}
              disabled={readOnly}
              onChange={(event) => updateUnit({ summary: event.target.value })}
              className="min-h-24 border bg-background p-3"
            />
          </label>
          <div className="mt-6 flex items-center justify-between gap-4">
            <div className="flex min-w-0 items-center gap-1.5">
              <h2 className="text-sm font-semibold">知识点</h2>
              <ActionTip label="知识点标题可直接编辑。右侧书本图标会打开该知识点的课程审阅页；课程尚未生成时页面为空。结构页只保存来源引用，不在这里生成独立 Markdown。">
                <span className="inline-flex size-5 items-center justify-center rounded-full text-muted-foreground" aria-label="知识点操作说明">
                  <CircleHelp className="size-3.5" />
                </span>
              </ActionTip>
            </div>
            <span className="shrink-0 font-mono text-xs text-muted-foreground">confidence {selectedUnit.confidence.toFixed(2)}</span>
          </div>
          <div className="mt-3 border-y" style={{ borderColor: 'var(--color-border-muted)' }}>
            {selectedUnit.knowledge_points.map((point) => {
              const sourceLabel = point.source_refs
                .map((ref) => `${ref.source_id} ${sourceRefRange(ref)}`)
                .join(' · ');
              return (
                <div key={point.knowledge_point_id} className="border-b px-3 py-4 last:border-b-0" style={{ borderColor: 'var(--color-border-muted)' }}>
                  <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-start">
                    <div className="flex min-w-0 flex-1 items-start gap-3">
                      <span className="mt-2 flex size-6 shrink-0 items-center justify-center rounded-full border font-mono text-[11px] text-muted-foreground" style={{ borderColor: 'var(--color-border-muted)' }}>
                        {point.position}
                      </span>
                      <label className="grid min-w-0 flex-1 gap-1.5">
                        <span className="sr-only">知识点标题</span>
                        <input
                          value={point.title}
                          disabled={readOnly}
                          onChange={(event) => updateKnowledgePoint(point.knowledge_point_id, { title: event.target.value })}
                          className="min-h-10 w-full border bg-background px-3 text-sm font-medium"
                        />
                        <span className="break-words font-mono text-[11px] text-muted-foreground" title={sourceLabel}>
                          {sourceLabel}
                        </span>
                      </label>
                    </div>
                    <div className="flex shrink-0 items-center gap-0.5 self-start rounded-md border bg-background p-0.5 sm:mt-5" style={{ borderColor: 'var(--color-border-muted)' }} aria-label={`知识点操作 ${point.title}`}>
                      <ActionTip label="查看课程：打开这个知识点的课程审阅页，不会修改当前结构。">
                        <Link
                          to={`/textbooks/${textbookId}/versions/${versionId}/knowledge/${point.knowledge_point_id}`}
                          className="inline-flex h-8 w-8 items-center justify-center rounded hover:bg-[var(--color-bg-hover)]"
                          aria-label={`查看课程 ${point.title}`}
                        >
                          <BookOpenCheck className="size-4" />
                        </Link>
                      </ActionTip>
                      <ActionTip label="拆分知识点：保留当前内容，并在下方创建一个副本，适合把过大的知识点拆成两个。">
                        <Button type="button" size="icon" variant="ghost" className="size-8" aria-label={`拆分 ${point.title}`} disabled={readOnly} onClick={() => splitKnowledgePoint(point)}>
                          <Scissors className="size-4" />
                        </Button>
                      </ActionTip>
                      <ActionTip label="与上一个合并：把当前知识点并入上一个知识点，适合删除重复或过细的拆分。">
                        <Button
                          type="button"
                          size="icon"
                          variant="ghost"
                          className="size-8"
                          aria-label={`合并 ${point.title}`}
                          disabled={readOnly || selectedUnit.knowledge_points[0]?.knowledge_point_id === point.knowledge_point_id}
                          onClick={() => mergeKnowledgePointWithPrevious(point)}
                        >
                          <GitMerge className="size-4" />
                        </Button>
                      </ActionTip>
                      <ActionTip label="删除知识点：只删除当前草稿中的这一项；保存或接受结构后才会写入数据库。">
                        <Button type="button" size="icon" variant="ghost" className="size-8" aria-label={`删除 ${point.title}`} disabled={readOnly} onClick={() => deleteKnowledgePoint(point.knowledge_point_id)}>
                          <Trash2 className="size-4" />
                        </Button>
                      </ActionTip>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
        <aside className="h-full min-h-0 overflow-y-auto border-t px-4 py-6 lg:border-t-0 lg:border-l" style={{ borderColor: 'var(--color-border-muted)' }}>
          <p className="font-mono text-xs text-muted-foreground">当前 Unit 来源定位</p>
          <div className="mt-3 grid gap-3">{selectedUnit.source_refs.map((ref) => <div key={`${ref.source_id}-${ref.start}-${ref.end}`} className="border-l-2 pl-3 text-xs leading-5" style={{ borderColor: 'var(--color-border-muted)' }}><p className="font-mono">{ref.source_id} {sourceRefRange(ref)}</p>{ref.quote && <p className="mt-1 text-muted-foreground">{ref.quote}</p>}</div>)}</div>
          {data.status === 'review' && (
            <div className="mt-8 grid gap-2">
              <p className="font-mono text-xs text-muted-foreground">整个教材结构（全部 Unit）</p>
              <ActionTip label="保存整个教材结构：会把本次修改的全部 Unit 和知识点一起写入，不是只保存当前 Unit。">
                <Button onClick={() => void saveStructure()} disabled={mutations.save.isPending}><Save className="mr-2 size-4" />保存结构</Button>
              </ActionTip>
              <ActionTip label="接受整个教材结构：会一次性确认全部 Unit 和知识点，接受后结构不能再编辑，只能逐知识点生成课程。">
                <Button variant="outline" onClick={() => void acceptStructure()} disabled={mutations.accept.isPending}><CheckCircle2 className="mr-2 size-4" />接受结构</Button>
              </ActionTip>
            </div>
          )}
          {data.status === 'accepted' && <p className="mt-8 border-l-2 pl-3 text-sm" style={{ borderColor: 'var(--color-success)', color: 'var(--color-text-secondary)' }}>结构已接受，可以逐知识点生成课程。</p>}
          {data.status === 'accepted' && (
            <ActionTip label="生成整本知识包：会基于当前已接受结构的全部 Unit 和知识点生成章节知识包，不是只处理当前选中的 Unit。">
              <Button className="mt-8 w-full" variant="outline" onClick={() => void generateBookAssets()} disabled={mutations.generateBookAssets.isPending}>
                <WandSparkles className="mr-2 size-4" />
                {mutations.generateBookAssets.isPending ? '正在启动' : data.book_asset_prefix ? '重新生成知识包' : '生成教材知识包'}
              </Button>
            </ActionTip>
          )}
        </aside>
        </div>
        )}
      </div>
    </main>
    </TooltipProvider>
  );
}
