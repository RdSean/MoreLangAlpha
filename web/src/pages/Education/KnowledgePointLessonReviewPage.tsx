import { useEffect, useState } from 'react';
import { CheckCircle2, Download, Pencil, RefreshCcw, Save, Send, WandSparkles } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { useToast } from '@/components/ui/use-toast';
import EducationMarkdown from './components/EducationMarkdown';
import { useKnowledgePointLessonByPoint, useStructureGenerationJob, useStructureMutations } from './queries';

function messageOf(error: unknown, fallback: string) {
  return error instanceof Error && error.message ? error.message : fallback;
}

export default function KnowledgePointLessonReviewPage() {
  const { textbookId, versionId, knowledgePointId } = useParams();
  const [jobId, setJobId] = useState<string>();
  const [autoGrading, setAutoGrading] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');
  const lesson = useKnowledgePointLessonByPoint(knowledgePointId, true);
  const generation = useStructureGenerationJob(jobId, Boolean(jobId));
  const mutations = useStructureMutations();
  const { toast } = useToast();

  useEffect(() => {
    if (!lesson.data) return;
    setDraft(lesson.data.content_markdown);
  }, [lesson.data]);

  useEffect(() => {
    if (generation.data?.status !== 'completed') return;
    void lesson.refetch();
  }, [generation.data?.status, lesson]);

  const generate = async () => {
    if (!knowledgePointId) return;
    try {
      const job = await mutations.generateLesson.mutateAsync({ knowledgePointId, autoGrading });
      setJobId(job.generation_job_id);
      setEditing(false);
    } catch (error) {
      toast({ variant: 'destructive', title: '无法生成课程', description: messageOf(error, '请稍后重试。') });
    }
  };

  const saveRevision = async () => {
    if (!lesson.data) return;
    try {
      await mutations.saveLessonRevision.mutateAsync({ lessonId: lesson.data.lesson_id, contentMarkdown: draft });
      setEditing(false);
      await lesson.refetch();
    } catch (error) {
      toast({ variant: 'destructive', title: '无法保存课程修订', description: messageOf(error, '请检查 Markdown 后重试。') });
    }
  };

  const approve = async () => {
    if (!lesson.data?.latest_revision_id) return;
    try {
      await mutations.approveLesson.mutateAsync({ lessonId: lesson.data.lesson_id, revisionId: lesson.data.latest_revision_id });
      await lesson.refetch();
    } catch (error) {
      toast({ variant: 'destructive', title: '无法通过课程', description: messageOf(error, '请重新生成或修订课程。') });
    }
  };

  const publish = async () => {
    if (!lesson.data || !versionId) return;
    try {
      await mutations.publish.mutateAsync({ versionId, structureId: lesson.data.structure_id });
      toast({ title: '教材结构版本已发布' });
    } catch (error) {
      toast({ variant: 'destructive', title: '无法发布教材', description: messageOf(error, '请确认所有知识点课程都已通过。') });
    }
  };

  if (lesson.isLoading) {
    return <main className="h-full overflow-y-auto bg-canvas p-8 text-sm text-muted-foreground">正在加载知识点课程…</main>;
  }

  if (!lesson.data) {
    return (
      <main className="h-full overflow-y-auto bg-canvas" data-testid="knowledge-point-lesson-review">
        <div className="mx-auto max-w-3xl px-6 py-12">
          <Link to={`/textbooks/${textbookId}/versions/${versionId}/structure`} className="text-sm text-muted-foreground">返回结构审阅</Link>
          <h1 className="title-font mt-6 text-2xl font-semibold">生成知识点课程</h1>
          <p className="mt-3 text-sm leading-6 text-muted-foreground">课程将以 `lesson.md` 生成，只有需要自动判题时才额外生成结构化练习。</p>
          <label className="mt-5 flex items-center gap-3 text-sm"><input type="checkbox" checked={autoGrading} onChange={(event) => setAutoGrading(event.target.checked)} />自动判题</label>
          <Button className="mt-6" onClick={() => void generate()} disabled={mutations.generateLesson.isPending || generation.data?.status === 'running' || generation.data?.status === 'preparing'}>
            <WandSparkles className="mr-2 size-4" />{generation.data?.status === 'running' || generation.data?.status === 'preparing' ? '正在生成课程' : '生成课程'}
          </Button>
          {generation.data?.status === 'failed' && <p className="mt-4 text-sm" style={{ color: 'var(--color-loss)' }}>{generation.data.error_message ?? '课程生成失败，请重试。'}</p>}
        </div>
      </main>
    );
  }

  return (
    <main className="h-full min-h-0 overflow-y-auto bg-canvas" data-testid="knowledge-point-lesson-review">
      <div className="mx-auto grid w-full max-w-[1400px] lg:grid-cols-[minmax(0,1fr)_320px]">
        <section className="min-w-0 px-5 py-7 lg:px-10">
          <div className="flex flex-wrap items-start justify-between gap-4 border-b pb-5" style={{ borderColor: 'var(--color-border-muted)' }}>
            <div>
              <Link to={`/textbooks/${textbookId}/versions/${versionId}/structure`} className="text-sm text-muted-foreground">返回结构审阅</Link>
              <p className="mt-4 font-mono text-xs text-muted-foreground">KNOWLEDGE POINT LESSON</p>
              <h1 className="title-font mt-2 text-2xl font-semibold">{lesson.data.knowledge_point_title}</h1>
              <p className="mt-1 text-sm text-muted-foreground">{lesson.data.unit_title} · {lesson.data.status}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" onClick={() => void generate()} disabled={mutations.generateLesson.isPending}><RefreshCcw className="mr-2 size-4" />重新生成</Button>
              <Button size="sm" variant="outline" onClick={() => setEditing((value) => !value)}><Pencil className="mr-2 size-4" />{editing ? '取消编辑' : '编辑 Markdown'}</Button>
              {lesson.data.status !== 'approved' && <Button size="sm" onClick={() => void approve()} disabled={mutations.approveLesson.isPending}><CheckCircle2 className="mr-2 size-4" />通过当前版本</Button>}
            </div>
          </div>
          {editing ? (
            <div className="py-6"><textarea aria-label="课程 Markdown" value={draft} onChange={(event) => setDraft(event.target.value)} className="min-h-[520px] w-full resize-y border bg-background p-4 font-mono text-sm leading-6" /><div className="mt-3 flex justify-end"><Button onClick={() => void saveRevision()} disabled={mutations.saveLessonRevision.isPending}><Save className="mr-2 size-4" />保存为新 revision</Button></div></div>
          ) : (
            <article className="max-w-[820px] py-7"><EducationMarkdown content={lesson.data.content_markdown} variant="lesson" className="text-base leading-7" /></article>
          )}
        </section>
        <aside className="border-t px-5 py-7 lg:min-h-[calc(100dvh-80px)] lg:border-l lg:border-t-0" style={{ borderColor: 'var(--color-border-muted)' }}>
          <h2 className="text-sm font-semibold">Revision 历史</h2>
          <div className="mt-4 grid gap-3">{lesson.data.revisions.map((revision) => <div key={revision.revision_id} className="border-l-2 pl-3 text-sm" style={{ borderColor: revision.revision_id === lesson.data?.latest_revision_id ? 'var(--color-accent-primary)' : 'var(--color-border-muted)' }}><p className="font-medium">v{revision.revision}</p><p className="mt-1 font-mono text-[11px] text-muted-foreground">{revision.size_bytes} bytes · {revision.content_sha256.slice(0, 12)}</p></div>)}</div>
          <div className="mt-8 grid gap-2">
            <Button onClick={() => void publish()} disabled={mutations.publish.isPending}><Send className="mr-2 size-4" />发布结构教材</Button>
            <Link to={`/textbooks/${textbookId}`} className="inline-flex min-h-9 items-center justify-center text-sm text-muted-foreground"><Download className="mr-2 size-4" />返回教材详情</Link>
          </div>
        </aside>
      </div>
    </main>
  );
}
