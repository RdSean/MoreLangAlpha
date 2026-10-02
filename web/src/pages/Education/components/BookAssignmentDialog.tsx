import { useEffect, useMemo, useState } from 'react';
import { UserRound } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  useEducationMembers,
  useManagedBookAssignmentMutations,
  useManagedBookAssignments,
} from '../queries';

interface BookAssignmentDialogProps {
  textbookId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function BookAssignmentDialog({
  textbookId,
  open,
  onOpenChange,
}: BookAssignmentDialogProps) {
  const members = useEducationMembers(open);
  const assignments = useManagedBookAssignments(textbookId, open);
  const mutations = useManagedBookAssignmentMutations();
  const [selectedStudentIds, setSelectedStudentIds] = useState<Set<string>>(new Set());
  const [initialized, setInitialized] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(false);

  const students = useMemo(
    () => (members.data ?? []).filter((member) => member.role === 'student'),
    [members.data],
  );
  const assignedStudentIds = useMemo(
    () => new Set((assignments.data ?? []).map((assignment) => assignment.student_user_id)),
    [assignments.data],
  );
  const loading = members.isLoading || assignments.isLoading;
  const loadFailed = members.isError || assignments.isError;

  useEffect(() => {
    if (!open) {
      setInitialized(false);
      setSaveError(false);
      return;
    }
    if (!initialized && !loading && !loadFailed) {
      setSelectedStudentIds(new Set(assignedStudentIds));
      setInitialized(true);
    }
  }, [assignedStudentIds, initialized, loadFailed, loading, open]);

  const addedStudentIds = students
    .map((student) => student.user_id)
    .filter((studentId) => selectedStudentIds.has(studentId) && !assignedStudentIds.has(studentId));
  const removedStudentIds = students
    .map((student) => student.user_id)
    .filter((studentId) => !selectedStudentIds.has(studentId) && assignedStudentIds.has(studentId));
  const changed = addedStudentIds.length > 0 || removedStudentIds.length > 0;

  const save = async () => {
    if (!changed || saving) return;
    setSaving(true);
    setSaveError(false);
    try {
      if (addedStudentIds.length > 0) {
        await mutations.assign.mutateAsync({
          textbookId,
          studentUserIds: addedStudentIds,
        });
      }
      if (removedStudentIds.length > 0) {
        await mutations.revoke.mutateAsync({
          textbookId,
          studentUserIds: removedStudentIds,
        });
      }
      onOpenChange(false);
    } catch {
      setSaveError(true);
    } finally {
      setSaving(false);
    }
  };

  const setOpen = (nextOpen: boolean) => {
    if (!saving) onOpenChange(nextOpen);
  };

  const retryLoad = () => {
    if (members.isError) void members.refetch();
    if (assignments.isError) void assignments.refetch();
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent variant="centered" className="max-w-md" dismissible={!saving}>
        <DialogHeader>
          <DialogTitle>给学生使用</DialogTitle>
          <DialogDescription className="sr-only">管理教材的学生访问权限</DialogDescription>
        </DialogHeader>

        {loading && (
          <p className="py-8 text-center text-sm text-muted-foreground">正在加载学生列表…</p>
        )}

        {!loading && loadFailed && (
          <div className="flex min-h-24 flex-col items-center justify-center gap-3 text-center">
            <p role="alert" className="text-sm text-destructive">无法加载学生授权。</p>
            <Button type="button" size="sm" variant="outline" onClick={retryLoad}>重试</Button>
          </div>
        )}

        {!loading && !loadFailed && students.length === 0 && (
          <p className="py-8 text-center text-sm text-muted-foreground">暂无学生账户</p>
        )}

        {!loading && !loadFailed && students.length > 0 && (
          <div className="divide-y rounded-md border border-border">
            {students.map((student) => (
              <label
                key={student.user_id}
                className="flex min-h-11 cursor-pointer items-center gap-3 px-3 py-2 hover:bg-[var(--color-bg-hover)]"
              >
                <input
                  type="checkbox"
                  className="size-4 shrink-0 accent-[var(--color-accent-primary)]"
                  checked={selectedStudentIds.has(student.user_id)}
                  disabled={saving}
                  onChange={(event) => {
                    setSaveError(false);
                    setSelectedStudentIds((current) => {
                      const next = new Set(current);
                      if (event.target.checked) next.add(student.user_id);
                      else next.delete(student.user_id);
                      return next;
                    });
                  }}
                />
                <span className="flex size-8 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
                  <UserRound className="size-4" aria-hidden="true" />
                </span>
                <span className="min-w-0 truncate text-sm font-medium text-foreground">
                  {student.name}
                </span>
              </label>
            ))}
          </div>
        )}

        {saveError && (
          <div className="flex min-h-11 items-center justify-between gap-3" role="alert">
            <p className="text-sm text-destructive">保存学生授权失败。</p>
            <Button type="button" size="sm" variant="outline" onClick={() => void save()}>
              重试
            </Button>
          </div>
        )}

        <DialogFooter className="gap-2 sm:space-x-0">
          <Button type="button" variant="outline" disabled={saving} onClick={() => setOpen(false)}>
            取消
          </Button>
          <Button
            type="button"
            disabled={loading || loadFailed || !initialized || !changed || saving}
            onClick={() => void save()}
          >
            {saving ? '正在保存' : '保存'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
