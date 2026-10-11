import { ArrowRight, BookMarked, BookOpen } from 'lucide-react';
import { Link, Navigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { useLearningAssignments } from './queries';

export default function StudentTextbooksPage() {
  const { member } = useAuth();
  const assignments = useLearningAssignments(member?.role === 'student');
  if (member?.role === 'parent') return <Navigate to="/textbooks" replace />;

  return <main className="h-full overflow-y-auto bg-canvas px-4 py-6 pb-24 sm:px-6 md:pb-8" data-testid="student-textbooks-page">
    <header className="mb-6 flex items-center gap-3 border-b pb-4">
      <BookMarked className="size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
      <h1 className="text-xl font-semibold">我的教材</h1>
    </header>
    {assignments.isLoading ? <p role="status" className="py-8 text-sm text-muted-foreground">正在加载教材…</p>
      : assignments.isError ? <div className="py-8"><p role="alert" className="text-sm">教材加载失败，请重试。</p><Button variant="outline" className="mt-3 min-h-11" onClick={() => void assignments.refetch()}>重试</Button></div>
        : !assignments.data?.length ? <p className="py-8 text-sm text-muted-foreground">暂未分配教材。</p>
          : <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{assignments.data.map(assignment => {
            const total = assignment.knowledge_point_count;
            const completed = assignment.completed_knowledge_point_count;
            return <Link key={assignment.assignment_id} to={`/education/learn/${assignment.assignment_id}`} className="group flex min-w-0 flex-col gap-5 rounded-lg border bg-card p-5 transition-colors hover:bg-[var(--color-bg-hover)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring" aria-label={`继续学习 ${assignment.textbook_title}`}>
              <div className="flex min-w-0 items-start gap-3"><BookOpen className="mt-0.5 size-6 shrink-0 text-muted-foreground" aria-hidden="true" /><h2 className="min-w-0 break-words text-base font-semibold">{assignment.textbook_title}</h2></div>
              <div className="mt-auto">
                <p className="mb-2 text-xs tabular-nums text-muted-foreground">{completed}/{total} 个知识点已学习</p>
                <div className="h-1.5 w-full overflow-hidden bg-[var(--color-bg-subtle)]" role="progressbar" aria-valuenow={Math.min(completed, total)} aria-valuemin={0} aria-valuemax={Math.max(1, total)} aria-label={`${assignment.textbook_title}学习进度`}>
                  <div className="h-full bg-[var(--color-accent-primary)]" style={{ width: `${total ? Math.min(100, completed / total * 100) : 0}%` }} />
                </div>
                <span className="mt-4 flex min-h-11 items-center justify-between text-sm">继续学习<ArrowRight className="size-4" aria-hidden="true" /></span>
              </div>
            </Link>;
          })}</div>}
  </main>;
}
