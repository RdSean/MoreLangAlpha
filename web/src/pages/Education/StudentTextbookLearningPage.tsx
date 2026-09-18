import { useMemo } from 'react';
import { BookOpen, ChevronLeft, ListTree } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import EducationMarkdown from './components/EducationMarkdown';
import PersonalNotebook from './components/PersonalNotebook';
import StudentLessonFollowUp from './components/StudentLessonFollowUp';
import { useLearningAssetMutations, useStudentKnowledgePointLesson, useStudentTextbookStructure } from './queries';

function Outline({
  assignmentId,
  activeUnitId,
  activeKnowledgePointId,
  structure,
}: {
  assignmentId: string;
  activeUnitId?: string;
  activeKnowledgePointId?: string;
  structure: NonNullable<ReturnType<typeof useStudentTextbookStructure>['data']>;
}) {
  return (
    <nav aria-label="教材知识点目录" className="grid gap-3">
      {structure.units.map((unit) => (
        <section key={unit.unit_id}>
          <Link to={`/education/learn/${assignmentId}/units/${unit.unit_id}`} className="block min-h-10 border-l-2 px-3 py-2 text-sm font-medium" style={{ borderColor: unit.unit_id === activeUnitId ? 'var(--color-accent-primary)' : 'transparent' }}>{unit.position}. {unit.title}</Link>
          <div className="mt-1 grid gap-1">
            {unit.knowledge_points.map((point) => (
              <Link key={point.knowledge_point_id} to={`/education/learn/${assignmentId}/knowledge/${point.knowledge_point_id}`} className="block min-h-9 border-l-2 px-4 py-2 text-sm leading-5" style={{ borderColor: point.knowledge_point_id === activeKnowledgePointId ? 'var(--color-accent-primary)' : 'transparent', color: point.knowledge_point_id === activeKnowledgePointId ? 'var(--color-text-primary)' : 'var(--color-text-secondary)' }}>{point.position}. {point.title}</Link>
            ))}
          </div>
        </section>
      ))}
    </nav>
  );
}

export default function StudentTextbookLearningPage() {
  const { assignmentId, unitId, knowledgePointId } = useParams();
  const structure = useStudentTextbookStructure(assignmentId);
  const lesson = useStudentKnowledgePointLesson(assignmentId, knowledgePointId);
  const learningAssets = useLearningAssetMutations();
  const data = structure.data;
  const activeUnit = useMemo(
    () => data?.units.find((unit) => unit.unit_id === unitId) ?? data?.units.find((unit) => unit.knowledge_points.some((point) => point.knowledge_point_id === knowledgePointId)) ?? data?.units[0],
    [data?.units, knowledgePointId, unitId],
  );

  if (structure.isLoading) return <main className="h-full overflow-y-auto bg-canvas p-8 text-sm text-muted-foreground">正在加载学习内容…</main>;
  if (!data || !activeUnit || !assignmentId) return <main className="h-full overflow-y-auto bg-canvas p-8 text-sm text-muted-foreground">学习材料不存在或尚未发布。</main>;

  return (
    <main className="h-full min-h-0 overflow-y-auto bg-canvas" data-testid="student-textbook-learning">
      <div className="mx-auto grid w-full max-w-[1500px] lg:grid-cols-[270px_minmax(0,1fr)_300px]">
        <aside className="hidden border-r px-4 py-7 lg:block" style={{ borderColor: 'var(--color-border-muted)' }}>
          <Link to="/education" className="inline-flex items-center gap-2 text-sm text-muted-foreground"><ChevronLeft className="size-4" />我的学习</Link>
          <h1 className="title-font mt-5 text-lg font-semibold">{data.textbook_title}</h1>
          <p className="mt-1 font-mono text-xs text-muted-foreground">v{data.version_sequence} · 结构 v{data.structure_sequence}</p>
          <div className="mt-6"><Outline assignmentId={assignmentId} structure={data} activeUnitId={activeUnit.unit_id} activeKnowledgePointId={knowledgePointId} /></div>
        </aside>
        <section className="min-w-0 px-5 py-6 lg:px-10 lg:py-8">
          <div className="mb-5 flex items-center justify-between gap-3 lg:hidden">
            <Link to="/education" className="inline-flex items-center gap-2 text-sm text-muted-foreground"><ChevronLeft className="size-4" />我的学习</Link>
            <Dialog><DialogTrigger asChild><Button size="sm" variant="outline"><ListTree className="mr-2 size-4" />目录</Button></DialogTrigger><DialogContent><DialogHeader><DialogTitle>知识点目录</DialogTitle></DialogHeader><Outline assignmentId={assignmentId} structure={data} activeUnitId={activeUnit.unit_id} activeKnowledgePointId={knowledgePointId} /></DialogContent></Dialog>
          </div>
          {knowledgePointId ? (
            lesson.isLoading ? <p className="text-sm text-muted-foreground">正在加载课程…</p> : lesson.data ? (
              <article className="max-w-[820px]">
                <p className="font-mono text-xs text-muted-foreground">{lesson.data.unit_title}</p>
                <h1 className="title-font mt-2 text-2xl font-semibold">{lesson.data.knowledge_point_title}</h1>
                <div className="mt-7"><EducationMarkdown content={lesson.data.content_markdown} variant="lesson" className="text-base leading-7" /></div>
                <StudentLessonFollowUp assignmentId={assignmentId} knowledgePointId={knowledgePointId} />
              </article>
            ) : <p className="text-sm text-muted-foreground">这个知识点尚未发布课程。</p>
          ) : (
            <div>
              <p className="font-mono text-xs text-muted-foreground">UNIT {activeUnit.position}</p>
              <h1 className="title-font mt-2 text-2xl font-semibold">{activeUnit.title}</h1>
              <p className="mt-3 max-w-3xl text-sm leading-6 text-muted-foreground">{activeUnit.summary || '从下面的知识点开始学习。'}</p>
              <section className="mt-8 border-t pt-5" style={{ borderColor: 'var(--color-border-muted)' }}>
                <div className="flex items-center gap-2"><BookOpen className="size-4" /><h2 className="text-sm font-semibold">知识点</h2></div>
                <div className="mt-4 grid gap-2">
                  {activeUnit.knowledge_points.map((point) => <Link key={point.knowledge_point_id} to={`/education/learn/${assignmentId}/knowledge/${point.knowledge_point_id}`} className="flex min-h-12 items-center justify-between border-b px-2 text-sm" style={{ borderColor: 'var(--color-border-muted)', color: point.has_lesson ? 'var(--color-text-primary)' : 'var(--color-text-tertiary)' }}><span>{point.position}. {point.title}</span><span className="font-mono text-[11px]">{point.has_lesson ? '已发布' : '暂无课程'}</span></Link>)}
                </div>
              </section>
            </div>
          )}
        </section>
        <aside className="hidden border-l px-5 py-7 lg:block" style={{ borderColor: 'var(--color-border-muted)' }}>
          {knowledgePointId && lesson.data && <Button className="mb-6 w-full" size="sm" onClick={() => void learningAssets.progress.mutateAsync({ assignmentId, knowledgePointId, status: 'read' })} disabled={learningAssets.progress.isPending}>标记已学</Button>}
          <PersonalNotebook assignmentId={assignmentId} unitId={activeUnit.unit_id} knowledgePointId={knowledgePointId} />
        </aside>
      </div>
    </main>
  );
}
