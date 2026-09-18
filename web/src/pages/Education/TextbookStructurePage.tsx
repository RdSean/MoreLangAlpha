import { useEffect, useMemo, useState } from 'react';
import { BookOpenCheck, CheckCircle2, GitMerge, Plus, Save, Scissors, Trash2, WandSparkles } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { useToast } from '@/components/ui/use-toast';
import { useLatestTextbookStructure, useStructureGenerationJob, useStructureMutations } from './queries';
import type { TextbookKnowledgePoint, TextbookStructureUnit } from './types';

function messageOf(error: unknown, fallback: string) {
  return error instanceof Error && error.message ? error.message : fallback;
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

export default function TextbookStructurePage() {
  const { textbookId, versionId } = useParams();
  const [jobId, setJobId] = useState<string>();
  const [units, setUnits] = useState<TextbookStructureUnit[]>([]);
  const [selectedUnitId, setSelectedUnitId] = useState<string>();
  const structure = useLatestTextbookStructure(versionId, true);
  const generation = useStructureGenerationJob(jobId, Boolean(jobId));
  const mutations = useStructureMutations();
  const { toast } = useToast();

  useEffect(() => {
    if (!structure.data) return;
    setUnits(cloneUnits(structure.data.units));
    setSelectedUnitId((current) => current ?? structure.data?.units[0]?.unit_id);
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

  const createStructure = async () => {
    if (!versionId) return;
    try {
      const job = await mutations.create.mutateAsync(versionId);
      setJobId(job.generation_job_id);
    } catch (error) {
      toast({ variant: 'destructive', title: '无法生成教材结构', description: messageOf(error, '请稍后重试。') });
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
    return <main className="h-full overflow-y-auto bg-canvas" data-testid="textbook-structure-page"><div className="mx-auto max-w-3xl px-6 py-12"><Link to={`/education/textbooks/${textbookId}`} className="text-sm text-muted-foreground">返回教材</Link><h1 className="title-font mt-6 text-2xl font-semibold">生成教材结构</h1><p className="mt-3 text-sm leading-6 text-muted-foreground">先从 Markdown 中识别 Unit、知识点和来源定位。非教学单元可以没有知识点，生成后再由你审阅。</p><Button className="mt-6" onClick={() => void createStructure()} disabled={mutations.create.isPending}><WandSparkles className="mr-2 size-4" />{mutations.create.isPending ? '正在创建任务' : '开始结构分析'}</Button></div></main>;
  }

  if (!structure.data && generation.data) {
    return <main className="h-full overflow-y-auto bg-canvas" data-testid="textbook-structure-page"><div className="mx-auto max-w-3xl px-6 py-12"><h1 className="title-font text-2xl font-semibold">正在分析教材结构</h1><p className="mt-3 text-sm text-muted-foreground">任务状态：{generation.data.status}，尝试 {generation.data.attempt_count} 次。</p>{generation.data.error_message && <p className="mt-3 text-sm" style={{ color: 'var(--color-loss)' }}>{generation.data.error_message}</p>}</div></main>;
  }

  const data = structure.data;
  if (!data || !selectedUnit) return null;
  const readOnly = data.status === 'accepted';

  return (
    <main className="h-full min-h-0 overflow-y-auto bg-canvas" data-testid="textbook-structure-page">
      <div className="mx-auto grid w-full max-w-[1500px] lg:grid-cols-[280px_minmax(0,1fr)_280px]">
        <aside className="border-b px-4 py-6 lg:min-h-[calc(100dvh-80px)] lg:border-b-0 lg:border-r" style={{ borderColor: 'var(--color-border-muted)' }}>
          <Link to={`/education/textbooks/${textbookId}`} className="text-sm text-muted-foreground">返回教材</Link>
          <h1 className="title-font mt-5 text-lg font-semibold">教材结构</h1>
          <p className="mt-1 font-mono text-xs text-muted-foreground">v{data.sequence} · {data.status}</p>
          <nav className="mt-5 grid gap-1" aria-label="结构单元">
            {units.map((unit) => <button key={unit.unit_id} type="button" onClick={() => setSelectedUnitId(unit.unit_id)} className="min-h-11 border-l-2 px-3 text-left text-sm" style={{ borderColor: unit.unit_id === selectedUnit.unit_id ? 'var(--color-accent-primary)' : 'transparent', color: 'var(--color-text-primary)' }}><span className="block truncate">{unit.position}. {unit.title}</span><span className="mt-1 block font-mono text-[11px] text-muted-foreground">{unit.unit_type} · {unit.knowledge_points.length} 个知识点</span></button>)}
          </nav>
        </aside>
        <section className="min-w-0 px-4 py-6 lg:px-8">
          <div className="flex flex-wrap items-start justify-between gap-4 border-b pb-5" style={{ borderColor: 'var(--color-border-muted)' }}>
            <label className="grid min-w-0 flex-1 gap-1.5"><span className="sr-only">单元标题</span><input value={selectedUnit.title} disabled={readOnly} onChange={(event) => updateUnit({ title: event.target.value })} className="title-font min-h-11 w-full border bg-background px-3 text-xl font-semibold" /></label>
            <Button variant="outline" size="sm" onClick={addKnowledgePoint} disabled={readOnly}><Plus className="mr-2 size-4" />添加知识点</Button>
          </div>
          <label className="mt-5 grid gap-1.5 text-sm"><span className="font-medium">单元说明</span><textarea value={selectedUnit.summary} disabled={readOnly} onChange={(event) => updateUnit({ summary: event.target.value })} className="min-h-24 border bg-background p-3" /></label>
          <div className="mt-6 flex items-center justify-between"><h2 className="text-sm font-semibold">知识点</h2><span className="font-mono text-xs text-muted-foreground">confidence {selectedUnit.confidence.toFixed(2)}</span></div>
          <div className="mt-3 border-y" style={{ borderColor: 'var(--color-border-muted)' }}>
            {selectedUnit.knowledge_points.map((point) => <div key={point.knowledge_point_id} className="grid gap-3 border-b px-3 py-4 last:border-b-0 sm:grid-cols-[minmax(0,1fr)_auto]" style={{ borderColor: 'var(--color-border-muted)' }}>
              <label className="grid gap-1.5"><span className="sr-only">知识点标题</span><input value={point.title} disabled={readOnly} onChange={(event) => updateKnowledgePoint(point.knowledge_point_id, { title: event.target.value })} className="min-h-10 border bg-background px-3 text-sm font-medium" /><span className="font-mono text-[11px] text-muted-foreground">{point.source_refs.map((ref) => `${ref.source_id} [${ref.start}:${ref.end}]`).join(' · ')}</span></label>
              <div className="flex items-center gap-1"><Link to={`/education/textbooks/${textbookId}/versions/${versionId}/knowledge/${point.knowledge_point_id}`} className="inline-flex h-10 w-10 items-center justify-center rounded-md hover:bg-[var(--color-bg-hover)]" aria-label={`查看课程 ${point.title}`}><BookOpenCheck className="size-4" /></Link><Button type="button" size="icon" variant="ghost" aria-label={`拆分 ${point.title}`} disabled={readOnly} onClick={() => splitKnowledgePoint(point)}><Scissors className="size-4" /></Button><Button type="button" size="icon" variant="ghost" aria-label={`合并 ${point.title}`} disabled={readOnly || selectedUnit.knowledge_points[0]?.knowledge_point_id === point.knowledge_point_id} onClick={() => mergeKnowledgePointWithPrevious(point)}><GitMerge className="size-4" /></Button><Button type="button" size="icon" variant="ghost" aria-label={`删除 ${point.title}`} disabled={readOnly} onClick={() => deleteKnowledgePoint(point.knowledge_point_id)}><Trash2 className="size-4" /></Button></div>
            </div>)}
          </div>
        </section>
        <aside className="border-t px-4 py-6 lg:min-h-[calc(100dvh-80px)] lg:border-t-0 lg:border-l" style={{ borderColor: 'var(--color-border-muted)' }}>
          <p className="font-mono text-xs text-muted-foreground">来源定位</p>
          <div className="mt-3 grid gap-3">{selectedUnit.source_refs.map((ref) => <div key={`${ref.source_id}-${ref.start}-${ref.end}`} className="border-l-2 pl-3 text-xs leading-5" style={{ borderColor: 'var(--color-border-muted)' }}><p className="font-mono">{ref.source_id} [{ref.start}:{ref.end}]</p>{ref.quote && <p className="mt-1 text-muted-foreground">{ref.quote}</p>}</div>)}</div>
          {data.status === 'review' && <div className="mt-8 grid gap-2"><Button onClick={() => void saveStructure()} disabled={mutations.save.isPending}><Save className="mr-2 size-4" />保存结构</Button><Button variant="outline" onClick={() => void acceptStructure()} disabled={mutations.accept.isPending}><CheckCircle2 className="mr-2 size-4" />接受结构</Button></div>}
          {data.status === 'accepted' && <p className="mt-8 border-l-2 pl-3 text-sm" style={{ borderColor: 'var(--color-success)', color: 'var(--color-text-secondary)' }}>结构已接受，可以逐知识点生成课程。</p>}
        </aside>
      </div>
    </main>
  );
}
