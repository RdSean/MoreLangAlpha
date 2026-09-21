import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { AlertTriangle, BookOpenCheck, CheckCircle2, ChevronDown, ChevronRight, Circle, CircleHelp, Clock3, FileText, GitMerge, Loader2, Plus, RefreshCcw, Save, Scissors, Trash2, WandSparkles } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { useToast } from '@/components/ui/use-toast';
import EducationMarkdown from './components/EducationMarkdown';
import ProcessingProfileDialog, { type ProcessingProfileValue } from './components/ProcessingProfileDialog';
import TextbookWorkflowStepper, { type TextbookWorkflowStep } from './components/TextbookWorkflowStepper';
import { useKnowledgePointLessonByPoint, useLatestTextbookStructure, useStructureGenerationJob, useStructureMutations } from './queries';
import type { TextbookKnowledgePoint, TextbookStructureUnit } from './types';

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

function KnowledgePointWorkspace({
  textbookId,
  versionId,
  unit,
  point,
  structureStatus,
}: {
  textbookId: string | undefined;
  versionId: string | undefined;
  unit: TextbookStructureUnit;
  point: TextbookKnowledgePoint;
  structureStatus: string;
}) {
  const [jobId, setJobId] = useState<string>();
  const [autoGrading, setAutoGrading] = useState(false);
  const lesson = useKnowledgePointLessonByPoint(point.knowledge_point_id, true);
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

  return (
    <section className="min-w-0">
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
        </div>
      </div>

      {lesson.isLoading ? (
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
              {structureStatus === 'accepted' ? '准备就绪' : '先接受教材结构'}
            </h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              {structureStatus === 'accepted'
                ? '这个知识点还没有课程 Markdown。点击下方按钮，让 book-to-skill 基于已确认的来源片段生成完整课程。'
                : '结构仍处于审阅状态。先返回当前 Unit 编辑并接受结构，再为知识点生成课程。'}
            </p>
            {structureStatus === 'accepted' && (
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
  const structure = useLatestTextbookStructure(versionId, true);
  const generation = useStructureGenerationJob(jobId, Boolean(jobId));
  const mutations = useStructureMutations();
  const { toast } = useToast();

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
    setExpandedUnitIds((current) => current.has(unitId)
      ? current
      : new Set([...current, unitId]));
  };

  const selectPoint = (unitId: string, pointId: string) => {
    setSelectedUnitId(unitId);
    setSelectedPointId(pointId);
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
    updateUnit({ knowledge_points: selectedUnit.knowledge_points.filter((point) => point.knowledge_point_id !== knowledgePointId) });
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

  const createStructure = async (profile: ProcessingProfileValue) => {
    if (!versionId) return;
    try {
      const job = await mutations.create.mutateAsync({ versionId, profile: profile as unknown as Record<string, unknown> });
      setProfileOpen(false);
      setJobId(job.generation_job_id);
    } catch (error) {
      toast({ variant: 'destructive', title: '无法生成教材结构', description: messageOf(error, '请稍后重试。') });
    }
  };

  const resumeStructure = async () => {
    const generationJobId = structure.data?.latest_generation_job_id;
    if (!generationJobId) return;
    try {
      const job = await mutations.resumeStructure.mutateAsync(generationJobId);
      setJobId(job.generation_job_id);
      await structure.refetch();
    } catch (error) {
      toast({ variant: 'destructive', title: '无法继续结构分析', description: messageOf(error, '请稍后重试。') });
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
    return <main className="h-full overflow-y-auto bg-canvas" data-testid="textbook-structure-page"><div className="mx-auto max-w-3xl px-6 py-12"><Link to={`/textbooks/${textbookId}`} className="text-sm text-muted-foreground">返回教材</Link><h1 className="title-font mt-6 text-2xl font-semibold">生成教材结构</h1><p className="mt-3 text-sm leading-6 text-muted-foreground">先从 Markdown 中识别 Unit、知识点和来源定位。非教学单元可以没有知识点，生成后再由你审阅。</p><Button className="mt-6" onClick={() => setProfileOpen(true)} disabled={mutations.create.isPending}><WandSparkles className="mr-2 size-4" />{mutations.create.isPending ? '正在创建任务' : '开始结构分析'}</Button><ProcessingProfileDialog open={profileOpen} onOpenChange={setProfileOpen} onConfirm={createStructure} /></div></main>;
  }

  if (!structure.data && generation.data) {
    return <main className="h-full overflow-y-auto bg-canvas" data-testid="textbook-structure-page"><div className="mx-auto max-w-3xl px-6 py-12"><h1 className="title-font text-2xl font-semibold">正在分析教材结构</h1><p className="mt-3 text-sm text-muted-foreground">任务状态：{generation.data.status}，尝试 {generation.data.attempt_count} 次。</p>{generation.data.error_message && <p className="mt-3 text-sm" style={{ color: 'var(--color-loss)' }}>{generation.data.error_message}</p>}</div></main>;
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
            <Button className="mt-6" onClick={() => void resumeStructure()} disabled={mutations.resumeStructure.isPending}>
              <RefreshCcw className="mr-2 size-4" />
              {mutations.resumeStructure.isPending ? '正在继续' : '重新运行结构分析'}
            </Button>
          )}
        </div>
      </main>
    );
  }

  return (
    <TooltipProvider delayDuration={150}>
    <main className="h-full min-h-0 overflow-y-auto bg-canvas" data-testid="textbook-structure-page">
      <div
        className="mx-auto w-full max-w-[1720px] border-b px-4 py-5 sm:px-8"
        style={{ borderColor: 'var(--color-border-muted)' }}
      >
        <Link to={`/textbooks/${textbookId}`} className="text-sm text-muted-foreground">返回教材</Link>
        <div className="mt-5">
          <TextbookWorkflowStepper steps={steps} />
        </div>
      </div>
      {warningCounts.size > 0 && (
        <div
          className="border-b px-4 py-3 sm:px-8"
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
      <div className="mx-auto grid w-full max-w-[1720px] lg:grid-cols-[360px_minmax(0,1fr)]">
        <aside className="border-b px-4 py-6 lg:min-h-[calc(100dvh-80px)] lg:border-b-0 lg:border-r" style={{ borderColor: 'var(--color-border-muted)' }}>
          <h1 className="title-font text-lg font-semibold">知识点</h1>
          <p className="mt-1 font-mono text-xs text-muted-foreground">v{data.sequence} · {data.status}</p>
          <nav className="mt-5 grid gap-1" aria-label="教材知识点树">
            {units.map((unit) => {
              const expanded = expandedUnitIds.has(unit.unit_id);
              const unitSelected = !selectedPoint && unit.unit_id === selectedUnit.unit_id;
              return (
                <div key={unit.unit_id}>
                  <div
                    className="flex min-w-0 items-stretch rounded-md border"
                    style={{
                      borderColor: unitSelected ? 'var(--color-accent-primary)' : 'transparent',
                      backgroundColor: unitSelected ? 'var(--color-bg-subtle)' : undefined,
                    }}
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
                      onClick={() => selectUnit(unit.unit_id)}
                      className="flex min-h-11 min-w-0 flex-1 flex-col justify-center overflow-hidden px-2 py-2 text-left text-sm hover:bg-[var(--color-bg-hover)]"
                      style={{ color: 'var(--color-text-primary)' }}
                    >
                      <span className="block w-full truncate whitespace-nowrap font-medium">{unit.position}. {unit.title}</span>
                      <span className="mt-0.5 block truncate whitespace-nowrap font-mono text-[10px] text-muted-foreground">
                        {unit.unit_type} · {unit.knowledge_points.length} 个知识点
                      </span>
                    </button>
                  </div>
                  {expanded && (
                    <div className="ml-7 mt-0.5 grid gap-0.5 border-l pl-2" style={{ borderColor: 'var(--color-border-muted)' }}>
                      {unit.knowledge_points.length === 0 ? (
                        <p className="px-2 py-1.5 text-xs text-muted-foreground">无知识点</p>
                      ) : unit.knowledge_points.map((point) => {
                        const active = point.knowledge_point_id === selectedPointId;
                        return (
                          <button
                            key={point.knowledge_point_id}
                            type="button"
                            title={point.title}
                            aria-label={`选择知识点 ${point.title}`}
                            onClick={() => selectPoint(unit.unit_id, point.knowledge_point_id)}
                            className="flex min-h-9 w-full min-w-0 items-center gap-2 rounded px-2 py-1.5 text-left text-xs transition-colors hover:bg-[var(--color-bg-hover)]"
                            style={{
                              color: active ? 'var(--color-text-primary)' : 'var(--color-text-secondary)',
                              backgroundColor: active ? 'var(--color-bg-subtle)' : undefined,
                            }}
                          >
                            <span className="w-4 shrink-0 text-right font-mono text-[10px] text-muted-foreground">{point.position}</span>
                            <span className="min-w-0 flex-1 truncate">{point.title}</span>
                            {point.lesson_status === 'approved' ? (
                              <CheckCircle2 className="size-3.5 shrink-0" aria-label="课程已通过" style={{ color: 'var(--color-success)' }} />
                            ) : point.lesson_revision_id ? (
                              <Clock3 className="size-3.5 shrink-0" aria-label="课程待审阅" style={{ color: 'var(--color-warning)' }} />
                            ) : (
                              <Circle className="size-3 shrink-0" aria-label="课程未生成" style={{ color: 'var(--color-text-tertiary)' }} />
                            )}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </nav>
        </aside>
        {selectedPoint ? (
          <KnowledgePointWorkspace
            textbookId={textbookId}
            versionId={versionId}
            unit={selectedUnit}
            point={selectedPoint}
            structureStatus={data.status}
          />
        ) : (
        <div className="grid min-w-0 lg:grid-cols-[minmax(0,1fr)_300px]">
        <section className="min-w-0 px-4 py-6 lg:px-8">
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
        <aside className="border-t px-4 py-6 lg:min-h-[calc(100dvh-80px)] lg:border-t-0 lg:border-l" style={{ borderColor: 'var(--color-border-muted)' }}>
          <p className="font-mono text-xs text-muted-foreground">来源定位</p>
          <div className="mt-3 grid gap-3">{selectedUnit.source_refs.map((ref) => <div key={`${ref.source_id}-${ref.start}-${ref.end}`} className="border-l-2 pl-3 text-xs leading-5" style={{ borderColor: 'var(--color-border-muted)' }}><p className="font-mono">{ref.source_id} {sourceRefRange(ref)}</p>{ref.quote && <p className="mt-1 text-muted-foreground">{ref.quote}</p>}</div>)}</div>
          {data.status === 'review' && <div className="mt-8 grid gap-2"><Button onClick={() => void saveStructure()} disabled={mutations.save.isPending}><Save className="mr-2 size-4" />保存结构</Button><Button variant="outline" onClick={() => void acceptStructure()} disabled={mutations.accept.isPending}><CheckCircle2 className="mr-2 size-4" />接受结构</Button></div>}
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
