import { useMemo, useState } from 'react';
import {
  ArrowLeft,
  BookOpenCheck,
  CheckCircle2,
  ExternalLink,
  FileCog,
  GitBranch,
  ListChecks,
  Play,
  RotateCcw,
  Send,
  WandSparkles,
} from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import TextbookWorkflowStepper, {
  type TextbookWorkflowStep,
} from './components/TextbookWorkflowStepper';
import { getEducationAssetDownloadUrl } from './api';
import {
  useCompletedParseJobs,
  useEducationMembers,
  useLatestTextbookStructure,
  useTextbook,
  useTextbookMutations,
  useStructureMutations,
} from './queries';
import type {
  LegacyTextbookSource,
  TextbookVersion,
  TextbookVersionStatus,
} from './types';

const statusLabels: Record<TextbookVersionStatus, string> = {
  draft: '草稿',
  processing: '准备内容',
  review: '待加工',
  published: '已发布',
  failed: '内容准备失败',
};

const GENERIC_STRUCTURE_SCHEMAS = new Set([
  'langalpha-book-content-tree/v1',
  'langalpha-managed-book-package/v1',
]);

function formatSize(size: number) {
  return size >= 1024 * 1024
    ? `${(size / (1024 * 1024)).toFixed(1)} MB`
    : `${Math.max(1, Math.ceil(size / 1024))} KB`;
}

function formatCompletedAt(value: string | null | undefined) {
  if (!value) return '完成时间未知';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function userMessage(error: unknown, fallback: string) {
  return error instanceof Error && error.message ? error.message : fallback;
}

function LegacySourceOpenButton({ source }: { source: LegacyTextbookSource }) {
  const [opening, setOpening] = useState(false);
  const { toast } = useToast();
  const open = async () => {
    setOpening(true);
    try {
      const url = await getEducationAssetDownloadUrl(source.asset_id);
      window.open(url, '_blank', 'noopener,noreferrer');
    } catch (error) {
      toast({
        variant: 'destructive',
        title: '无法打开来源文件',
        description: userMessage(error, '请稍后重试。'),
      });
    } finally {
      setOpening(false);
    }
  };
  return (
    <Button
      size="sm"
      variant="ghost"
      onClick={() => void open()}
      disabled={opening}
      aria-label={`打开 ${source.original_filename}`}
    >
      <ExternalLink className="mr-2 size-4" aria-hidden="true" />
      {opening ? '正在打开' : '打开'}
    </Button>
  );
}

function StartProcessingDialog({ textbookId }: { textbookId: string }) {
  const [selectedParseJobIds, setSelectedParseJobIds] = useState<string[]>([]);
  const [open, setOpen] = useState(false);
  const parseJobs = useCompletedParseJobs(open);
  const mutations = useTextbookMutations();
  const { toast } = useToast();
  const jobs = parseJobs.data ?? [];
  const toggleParseJob = (jobId: string) =>
    setSelectedParseJobIds((current) =>
      current.includes(jobId)
        ? current.filter((id) => id !== jobId)
        : [...current, jobId],
    );
  const submit = async () => {
    try {
      if (selectedParseJobIds.length === 0) return;
      await mutations.start.mutateAsync({
        textbookId,
        sourceParseJobIds: selectedParseJobIds,
      });
      setSelectedParseJobIds([]);
      setOpen(false);
    } catch (error) {
      toast({
        variant: 'destructive',
        title: '无法准备教材内容',
        description: userMessage(error, '请检查资料并重试。'),
      });
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <BookOpenCheck className="mr-2 size-4" aria-hidden="true" />
          选择教材来源
        </Button>
      </DialogTrigger>
      <DialogContent variant="centered" className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>从图书馆选择来源</DialogTitle>
        </DialogHeader>
        <div className="grid gap-5">
          <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
            仅显示已完成解析的 Markdown 文档，可同时选择一份或多份作为同一份教材内容。
          </p>
          {parseJobs.isLoading ? (
            <p className="text-sm text-muted-foreground">正在加载解析结果…</p>
          ) : parseJobs.isError ? (
            <div
              role="alert"
              className="grid justify-items-start gap-3 border p-4"
              style={{ borderColor: 'var(--color-border-muted)' }}
            >
              <p className="text-sm" style={{ color: 'var(--color-loss)' }}>
                无法加载已完成解析的资料。
              </p>
              <Button size="sm" variant="outline" onClick={() => void parseJobs.refetch()}>
                重试
              </Button>
            </div>
          ) : jobs.length === 0 ? (
            <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
              图书馆暂无已完成解析的文档。
            </p>
          ) : (
            <div
              className="max-h-80 divide-y overflow-y-auto border"
              style={{ borderColor: 'var(--color-border-muted)' }}
            >
              {jobs.map((job) => (
                <label
                  key={job.producer_job_id}
                  className="flex min-h-14 cursor-pointer items-start gap-3 px-3 py-3 text-sm"
                >
                  <input
                    className="mt-1"
                    type="checkbox"
                    aria-label={job.filename}
                    checked={selectedParseJobIds.includes(job.producer_job_id)}
                    onChange={() => toggleParseJob(job.producer_job_id)}
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate" style={{ color: 'var(--color-text-primary)' }}>
                      {job.filename}
                    </span>
                    <span
                      className="mt-1 block font-mono text-[11px] leading-5"
                      style={{ color: 'var(--color-text-tertiary)' }}
                    >
                      {formatCompletedAt(job.parse_completed_at)} · {job.parser_name}
                      {job.parser_version ? ` ${job.parser_version}` : ''} ·{' '}
                      {formatSize(job.size_bytes)} · {job.artifact_count} 个解析产物
                    </span>
                  </span>
                </label>
              ))}
            </div>
          )}
          <DialogFooter>
            <Button
              onClick={() => void submit()}
              disabled={selectedParseJobIds.length === 0 || mutations.start.isPending}
            >
              {mutations.start.isPending ? '正在创建' : '创建教材内容'}
            </Button>
          </DialogFooter>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function AssignDialog({ publicationId }: { publicationId: string }) {
  const [studentUserId, setStudentUserId] = useState('');
  const [open, setOpen] = useState(false);
  const members = useEducationMembers(true).data ?? [];
  const students = members.filter((member) => member.role === 'student');
  const mutations = useTextbookMutations();
  const { toast } = useToast();
  const assign = async () => {
    try {
      await mutations.assign.mutateAsync({ publicationId, studentUserId });
      setOpen(false);
    } catch (error) {
      toast({
        variant: 'destructive',
        title: '无法分配教材',
        description: userMessage(error, '请稍后重试。'),
      });
    }
  };
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" variant="outline">
          <Send className="mr-2 size-4" aria-hidden="true" />
          分配学生
        </Button>
      </DialogTrigger>
      <DialogContent variant="centered" className="max-w-md">
        <DialogHeader>
          <DialogTitle>分配已发布教材</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4">
          <label className="grid gap-1.5 text-sm font-medium">
            学生
            <select
              value={studentUserId}
              onChange={(event) => setStudentUserId(event.target.value)}
              className="h-10 border border-input bg-background px-3 text-sm"
            >
              <option value="">选择学生</option>
              {students.map((student) => (
                <option key={student.user_id} value={student.user_id}>
                  {student.name}
                </option>
              ))}
            </select>
          </label>
          <DialogFooter>
            <Button
              onClick={() => void assign()}
              disabled={!studentUserId || mutations.assign.isPending}
            >
              {mutations.assign.isPending ? '正在分配' : '分配教材'}
            </Button>
          </DialogFooter>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function workflowSteps(
  version: TextbookVersion,
  structureStatus?: string,
  total = 0,
  accepted = 0,
  approved = 0,
): TextbookWorkflowStep[] {
  const contentStatus: TextbookWorkflowStep['status'] =
    version.status === 'review' || version.status === 'published'
      ? 'completed'
      : version.status === 'failed'
        ? 'failed'
        : version.status === 'processing'
          ? 'in_progress'
          : 'pending';
  const structureStep: TextbookWorkflowStep['status'] =
    version.is_published
      ? 'completed'
      : structureStatus === 'review' || structureStatus === 'accepted'
        ? 'completed'
        : structureStatus === 'failed'
          ? 'failed'
          : structureStatus === 'queued' || structureStatus === 'running'
            ? 'in_progress'
            : 'pending';
  const lessonStep: TextbookWorkflowStep['status'] =
    structureStatus === 'accepted'
      ? total > 0 && accepted > 0 && approved === accepted
        ? 'completed'
        : 'in_progress'
      : 'pending';
  const publishStep: TextbookWorkflowStep['status'] =
    version.is_published
      ? 'completed'
      : lessonStep === 'completed'
        ? 'in_progress'
        : 'pending';

  return [
    { id: 'content', label: '内容准备', status: contentStatus },
    { id: 'structure', label: '结构分析', status: structureStep },
    { id: 'lessons', label: '知识点课程', status: lessonStep },
    { id: 'publish', label: '发布', status: publishStep },
  ];
}

function SourceSummary({ version }: { version: TextbookVersion }) {
  if (version.sources.length === 0) {
    return (
      <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
        尚未选择来源。
      </p>
    );
  }
  return (
    <ul
      aria-label="教材来源"
      className="grid divide-y border"
      style={{ borderColor: 'var(--color-border-muted)' }}
    >
      {version.sources.map((source) =>
        source.legacy ? (
          <li
            key={`legacy-${source.asset_id}`}
            className="grid gap-2 px-3 py-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center"
          >
            <div className="min-w-0">
              <p className="break-words text-sm" style={{ color: 'var(--color-text-primary)' }}>
                {source.original_filename}
              </p>
              <p
                className="mt-1 break-words font-mono text-[11px]"
                style={{ color: 'var(--color-text-tertiary)' }}
              >
                {source.content_type} · {formatSize(source.size_bytes)}
              </p>
            </div>
            <LegacySourceOpenButton source={source} />
          </li>
        ) : (
          <li
            key={`${source.producer_job_id}-${source.position}`}
            className="grid gap-2 px-3 py-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center"
          >
            <div className="min-w-0">
              <p className="break-words text-sm" style={{ color: 'var(--color-text-primary)' }}>
                {source.filename}
              </p>
              <p
                className="mt-1 break-words font-mono text-[11px]"
                style={{ color: 'var(--color-text-tertiary)' }}
              >
                {source.parser_name}
                {source.parser_version ? ` ${source.parser_version}` : ''} ·{' '}
                {source.format.toUpperCase()}
              </p>
            </div>
            {source.document_deleted ? (
              <span className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
                原文档已删除
              </span>
            ) : (
              <Link
                to={`/documents/${encodeURIComponent(source.document_id)}`}
                className="inline-flex w-fit items-center gap-2 text-sm"
                style={{ color: 'var(--color-text-secondary)' }}
              >
                <ExternalLink className="size-4" aria-hidden="true" />
                查看文档
              </Link>
            )}
          </li>
        ),
      )}
    </ul>
  );
}

function VersionWorkflow({ textbookId, version }: { textbookId: string; version: TextbookVersion }) {
  const structure = useLatestTextbookStructure(version.version_id, true);
  const teaching = useTextbookMutations();
  const structureMutations = useStructureMutations();
  const { toast } = useToast();
  const summary = structure.data?.lesson_summary;
  const genericStructure = Boolean(
    structure.data
    && GENERIC_STRUCTURE_SCHEMAS.has(structure.data.schema_version),
  );
  const steps = useMemo(
    () =>
      workflowSteps(
        version,
        structure.data?.status,
        summary?.total ?? 0,
        summary?.accepted ?? 0,
        summary?.approved ?? 0,
      ),
    [summary, structure.data?.status, version],
  );
  const runAction = async (
    action: () => Promise<unknown>,
    failureTitle: string,
  ) => {
    try {
      await action();
    } catch (error) {
      toast({
        variant: 'destructive',
        title: failureTitle,
        description: userMessage(error, '请稍后重试。'),
      });
    }
  };
  const publish = async () => {
    if (!structure.data) return;
    try {
      await structureMutations.publish.mutateAsync({
        versionId: version.version_id,
        structureId: structure.data.structure_id,
      });
      toast({ title: '教材已发布' });
    } catch (error) {
      toast({
        variant: 'destructive',
        title: '无法发布教材',
        description: userMessage(error, '请确认全部知识点课程已通过。'),
      });
    }
  };

  return (
    <section
      className="border"
      style={{ borderColor: 'var(--color-border-muted)' }}
      aria-label={`教材版本 v${version.sequence}`}
    >
      <div
        className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3"
        style={{ borderColor: 'var(--color-border-muted)' }}
      >
        <div>
          <h2 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>
            v{version.sequence}
          </h2>
          <p className="mt-1 font-mono text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
            {version.extractor_name ?? '等待内容准备'}
            {version.extractor_version ? `/${version.extractor_version}` : ''}
          </p>
        </div>
        <span
          className="border px-2 py-1 font-mono text-[11px]"
          style={{
            borderColor: 'var(--color-border-muted)',
            color: 'var(--color-text-secondary)',
          }}
        >
          {statusLabels[version.status]}
        </span>
      </div>

      <div className="grid gap-5 p-4">
        <TextbookWorkflowStepper steps={steps} />
        <div
          className="flex flex-wrap items-center justify-between gap-3 border-y py-4"
          style={{ borderColor: 'var(--color-border-muted)' }}
        >
          <div>
            <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>
              {steps.find((step) => step.status === 'in_progress' || step.status === 'failed')?.label ??
                '教材加工已完成'}
            </h3>
            <p className="mt-1 text-sm" style={{ color: 'var(--color-text-secondary)' }}>
              {structure.isLoading
                ? '正在读取结构与课程进度…'
                : summary
                  ? `知识点 ${summary.accepted}/${summary.total} 已接受，课程 ${summary.approved}/${summary.total} 已通过。`
                  : '结构尚未生成。'}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {version.processing_job_status === 'queued' && version.processing_job_id && (
              <Button
                size="sm"
                onClick={() =>
                  void runAction(
                    () => teaching.run.mutateAsync(version.processing_job_id!),
                    '无法准备教材内容',
                  )
                }
                disabled={teaching.run.isPending}
              >
                <Play className="mr-2 size-4" aria-hidden="true" />
                执行内容准备
              </Button>
            )}
            {version.status === 'failed' &&
              version.processing_job_status === 'failed' &&
              version.processing_job_id && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() =>
                    void runAction(
                      () => teaching.retry.mutateAsync(version.processing_job_id!),
                      '无法重试内容准备',
                    )
                  }
                  disabled={teaching.retry.isPending}
                >
                  <RotateCcw className="mr-2 size-4" aria-hidden="true" />
                  重试内容准备
                </Button>
              )}
            {version.status === 'review' && (
              <Link
                to={`/textbooks/${textbookId}/versions/${version.version_id}/processing`}
                className="inline-flex h-9 items-center rounded-md border border-input bg-background px-3 text-sm font-medium hover:bg-[var(--color-bg-hover)]"
              >
                <WandSparkles className="mr-2 size-4" aria-hidden="true" />
                开始处理
              </Link>
            )}
            {structure.data && !genericStructure && (
              <Link
                to={`/textbooks/${textbookId}/versions/${version.version_id}/structure`}
                className="inline-flex h-9 items-center rounded-md border border-input bg-background px-3 text-sm font-medium hover:bg-[var(--color-bg-hover)]"
              >
                <GitBranch className="mr-2 size-4" aria-hidden="true" />
                {structure.data?.status === 'accepted'
                  ? '查看知识点课程'
                  : structure.data
                    ? '审阅结构与知识点'
                    : '开始结构分析'}
              </Link>
            )}
            {genericStructure && (
              <Link
                to={`/textbooks/${textbookId}/versions/${version.version_id}/candidates`}
                className="inline-flex h-9 items-center rounded-md border border-input bg-background px-3 text-sm font-medium hover:bg-[var(--color-bg-hover)]"
              >
                <ListChecks className="mr-2 size-4" aria-hidden="true" />
                确认知识点候选
              </Link>
            )}
            {steps.find((step) => step.id === 'publish')?.status === 'in_progress' && (
              <Button
                size="sm"
                onClick={() => void publish()}
                disabled={structureMutations.publish.isPending}
              >
                <CheckCircle2 className="mr-2 size-4" aria-hidden="true" />
                {structureMutations.publish.isPending ? '正在发布' : '发布教材'}
              </Button>
            )}
            {version.publication_id && <AssignDialog publicationId={version.publication_id} />}
          </div>
        </div>
        {version.processing_error && (
          <p
            role="alert"
            className="border-l-2 pl-3 text-sm"
            style={{ borderColor: 'var(--color-loss)', color: 'var(--color-loss)' }}
          >
            {version.processing_error}
          </p>
        )}
        <SourceSummary version={version} />
      </div>
    </section>
  );
}

export default function TextbookDetailPage() {
  const { textbookId } = useParams();
  const textbook = useTextbook(textbookId);
  const data = textbook.data;
  const versions = useMemo(() => data?.versions ?? [], [data?.versions]);

  if (textbook.isLoading) {
    return (
      <main className="h-full overflow-y-auto bg-canvas">
        <p className="p-8 text-sm text-muted-foreground">正在加载教材…</p>
      </main>
    );
  }
  if (!data) {
    return (
      <main className="h-full overflow-y-auto bg-canvas">
        <p className="p-8 text-sm text-muted-foreground">教材不存在或无权访问。</p>
      </main>
    );
  }

  return (
    <main
      className="h-full min-h-0 overflow-y-auto bg-canvas"
      data-testid="textbook-detail-page"
    >
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
        <header className="border-b pb-5" style={{ borderColor: 'var(--color-border-muted)' }}>
          <Link
            to="/textbooks"
            className="inline-flex items-center gap-2 text-sm"
            style={{ color: 'var(--color-text-secondary)' }}
          >
            <ArrowLeft className="size-4" aria-hidden="true" />
            教材加工
          </Link>
          <div className="mt-4 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="font-mono text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
                TEXTBOOK WORKFLOW
              </p>
              <h1 className="title-font mt-2 text-2xl font-semibold" style={{ color: 'var(--color-text-primary)' }}>
                {data.title}
              </h1>
              <p className="mt-1 text-sm" style={{ color: 'var(--color-text-secondary)' }}>
                从课程加工的视角准备内容、提取结构、生成知识点课程并发布给学生。
              </p>
            </div>
            {versions.length > 0 && <StartProcessingDialog textbookId={data.textbook_id} />}
          </div>
        </header>

        {versions.length === 0 ? (
          <section
            className="border p-6"
            style={{ borderColor: 'var(--color-border-muted)' }}
          >
            <FileCog className="size-5" style={{ color: 'var(--color-text-tertiary)' }} />
            <h2 className="mt-4 text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>
              第一步：准备教材内容
            </h2>
            <p className="mt-2 max-w-xl text-sm" style={{ color: 'var(--color-text-secondary)' }}>
              从图书馆选择一份或多份已完成解析的 Markdown，建立这个教材的冻结内容版本。
            </p>
            <div className="mt-4">
              <StartProcessingDialog textbookId={data.textbook_id} />
            </div>
          </section>
        ) : (
          <section aria-label="教材版本" className="grid gap-5">
            {versions.map((version) => (
              <VersionWorkflow
                key={version.version_id}
                textbookId={data.textbook_id}
                version={version}
              />
            ))}
          </section>
        )}
      </div>
    </main>
  );
}
