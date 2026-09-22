import { useRef, useState } from 'react';
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  Circle,
  Loader2,
  WandSparkles,
} from 'lucide-react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { useToast } from '@/components/ui/use-toast';
import {
  useBookPipelineMutations,
  useBookPipelineProgress,
  useTextbook,
} from './queries';
import type {
  BookPipelineJob,
  BookPipelineProgressStage,
  BookPipelineProgressStatus,
} from './types';
import './BookProcessingPage.css';

const processingBriefPlaceholder =
  '例如：这是一本法语教材；忽略教师指导页；只提取学生活动页；数学教材中的公式和例题请按原顺序保留。';

const emptyBookPipelineStages: BookPipelineProgressStage[] = [
  {
    name: 'chapter_analysis',
    label: '教材章节解析',
    status: 'queued',
    current: null,
    total: null,
    events: [],
  },
  {
    name: 'content_processing',
    label: '内容智能处理',
    status: 'queued',
    current: null,
    total: null,
    events: [],
  },
  {
    name: 'knowledge_point_generation',
    label: '知识点生成',
    status: 'queued',
    current: null,
    total: null,
    events: [],
  },
  {
    name: 'lesson_preparation',
    label: '课程制作',
    status: 'queued',
    current: null,
    total: null,
    events: [],
  },
];

function messageOf(error: unknown, fallback: string) {
  return error instanceof Error && error.message ? error.message : fallback;
}

function createRequestId() {
  if (typeof globalThis.crypto.randomUUID === 'function') {
    return globalThis.crypto.randomUUID();
  }
  const bytes = new Uint8Array(16);
  globalThis.crypto.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0'));
  return [
    hex.slice(0, 4).join(''),
    hex.slice(4, 6).join(''),
    hex.slice(6, 8).join(''),
    hex.slice(8, 10).join(''),
    hex.slice(10, 16).join(''),
  ].join('-');
}

export default function BookProcessingPage() {
  const { textbookId, versionId } = useParams<{
    textbookId: string;
    versionId: string;
  }>();
  const textbook = useTextbook(textbookId);
  const pipeline = useBookPipelineMutations();
  const [searchParams, setSearchParams] = useSearchParams();
  const { toast } = useToast();
  const [open, setOpen] = useState(false);
  const [processingBrief, setProcessingBrief] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [job, setJob] = useState<BookPipelineJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const submitLock = useRef(false);
  const version = textbook.data?.versions.find(
    (candidate) => candidate.version_id === versionId,
  );
  const pending = submitting || pipeline.create.isPending;
  const jobId = searchParams.get('job') ?? undefined;
  const progress = useBookPipelineProgress(jobId, Boolean(jobId));
  const jobStatus = progress.data?.status ?? job?.status;
  const progressIsActive =
    progress.isPending ||
    jobStatus === 'queued' ||
    jobStatus === 'preparing' ||
    jobStatus === 'running' ||
    jobStatus === 'validating';

  const submit = async () => {
    if (submitLock.current || pending || !versionId) return;
    submitLock.current = true;
    setSubmitting(true);
    setError(null);
    try {
      const created = await pipeline.create.mutateAsync({
        versionId,
        input: {
          processing_brief: processingBrief.trim(),
          request_id: createRequestId(),
          pause_after_chapter_analysis: false,
        },
      });
      setJob(created);
      const nextSearchParams = new URLSearchParams(searchParams);
      nextSearchParams.set('job', created.generation_job_id);
      setSearchParams(nextSearchParams, { replace: true });
      setOpen(false);
    } catch (submitError) {
      const message = messageOf(submitError, '请稍后重试。');
      setError(message);
      toast({
        variant: 'destructive',
        title: '无法开始教材处理',
        description: message,
      });
    } finally {
      submitLock.current = false;
      setSubmitting(false);
    }
  };

  return (
    <main className="book-processing-page" data-testid="book-processing-page">
      <div className="book-processing-shell">
        <header className="book-processing-header">
          <Link
            to={textbookId ? `/textbooks/${textbookId}` : '/textbooks'}
            className="book-processing-back"
          >
            <ArrowLeft className="size-4" aria-hidden="true" />
            返回教材
          </Link>
          <div className="book-processing-heading">
            <div>
              <p className="book-processing-kicker">TEXTBOOK PROCESSING</p>
              <h1>{textbook.data?.title ?? '教材处理'}</h1>
              <p>
                {version ? `版本 v${version.sequence}` : '等待读取教材版本'}
              </p>
            </div>
            <Dialog
              open={open}
              onOpenChange={(nextOpen) => {
                if (!pending) setOpen(nextOpen);
              }}
            >
              <DialogTrigger asChild>
                <Button disabled={pending}>
                  <WandSparkles className="mr-2 size-4" aria-hidden="true" />
                  开始处理
                </Button>
              </DialogTrigger>
              <DialogContent variant="centered" className="max-w-xl">
                <DialogHeader>
                  <DialogTitle>开始教材处理</DialogTitle>
                </DialogHeader>
                <div className="grid gap-4">
                  <label
                    htmlFor="book-processing-brief"
                    className="grid gap-1.5 text-sm font-medium"
                  >
                    补充要求（可选）
                    <Textarea
                      id="book-processing-brief"
                      value={processingBrief}
                      onChange={(event) =>
                        setProcessingBrief(event.target.value)
                      }
                      maxLength={4_000}
                      placeholder={processingBriefPlaceholder}
                      disabled={pending}
                      className="min-h-32"
                    />
                  </label>
                  <p className="text-xs leading-5 text-muted-foreground">
                    可说明教材语言、学科、包含或排除规则及特殊结构，不会改变系统处理契约。
                  </p>
                  {error && (
                    <p role="alert" className="text-sm text-destructive">
                      {error}
                    </p>
                  )}
                  <DialogFooter>
                    <Button onClick={() => void submit()} disabled={pending}>
                      {pending && (
                        <Loader2
                          className="mr-2 size-4 animate-spin"
                          aria-hidden="true"
                        />
                      )}
                      {pending ? '正在创建' : '开始处理'}
                    </Button>
                  </DialogFooter>
                </div>
              </DialogContent>
            </Dialog>
          </div>
        </header>

        {jobId ? (
          <section
            className="book-processing-progress"
            aria-label="教材处理进度"
          >
            <div className="book-processing-progress-head">
              <span
                className={`book-processing-progress-mark ${
                  progressIsActive ? 'is-running' : ''
                }`}
                aria-hidden="true"
              >
                {progressIsActive ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : progress.isError ||
                  jobStatus === 'failed' ||
                  jobStatus === 'cancelled' ? (
                  <AlertCircle className="size-4" />
                ) : (
                  <CheckCircle2 className="size-4" />
                )}
              </span>
              <div className="book-processing-progress-copy">
                <h2>处理任务已创建</h2>
                <p>
                  {job?.reused_existing_job
                    ? '已复用同一教材正在进行的处理任务。'
                    : '任务已进入处理队列。'}
                </p>
                <p className="book-processing-job-id">任务编号 {jobId}</p>
              </div>
            </div>
            {progress.isError && (
              <p className="book-processing-progress-error" role="alert">
                暂时无法读取处理进度。
              </p>
            )}
            <BookProcessingTimeline
              stages={progress.data?.stages ?? emptyBookPipelineStages}
              loading={progress.isPending && !progress.data}
            />
          </section>
        ) : (
          <section className="book-processing-empty">
            <BookOpenProcessMark />
            <h2>准备教材处理</h2>
            <p>开始前可补充教材语言、学科、内容范围和特殊结构要求。</p>
          </section>
        )}
      </div>
    </main>
  );
}

const stageStatusIcons: Record<
  BookPipelineProgressStatus,
  React.ReactNode
> = {
  completed: <CheckCircle2 className="size-4" />,
  running: <Loader2 className="size-4 animate-spin" />,
  failed: <AlertCircle className="size-4" />,
  queued: <Circle className="size-4" />,
  skipped: <Circle className="size-4" />,
};

function stageStatusText(stage: BookPipelineProgressStage) {
  if (stage.status === 'completed') {
    return stage.name === 'knowledge_point_generation' && stage.current != null
      ? `已完成 ${stage.current} 个候选`
      : '已完成';
  }
  if (stage.status === 'running') {
    if (
      stage.name === 'content_processing' &&
      stage.current != null &&
      stage.total != null
    ) {
      return `进行中：Unit ${stage.current} / 共 ${stage.total} 个`;
    }
    return stage.name === 'lesson_preparation' ? '正在制作课程' : '进行中';
  }
  if (stage.status === 'failed') return '处理失败';
  if (stage.status === 'skipped') return '已跳过';
  return stage.name === 'lesson_preparation' ? '等待知识点确认' : '待处理';
}

function pendingContentText(stage: BookPipelineProgressStage) {
  if (
    stage.name !== 'content_processing' ||
    stage.status !== 'running' ||
    stage.current == null ||
    stage.total == null ||
    stage.current >= stage.total
  ) {
    return null;
  }
  const firstPending = stage.current + 1;
  return firstPending === stage.total
    ? `待处理：Unit ${stage.total}`
    : `待处理：Unit ${firstPending} - Unit ${stage.total}`;
}

function BookProcessingTimeline({
  stages,
  loading,
}: {
  stages: BookPipelineProgressStage[];
  loading: boolean;
}) {
  return (
    <ol
      className="book-processing-timeline"
      aria-label="四阶段处理进度"
      aria-live="polite"
    >
      {stages.map((stage, index) => {
        const pending = pendingContentText(stage);
        return (
          <li
            key={stage.name}
            className={`book-processing-stage is-${stage.status}`}
          >
            <span className="book-processing-stage-icon" aria-hidden="true">
              {stageStatusIcons[stage.status]}
            </span>
            <div className="book-processing-stage-body">
              <div className="book-processing-stage-title">
                <span>阶段 {index + 1}</span>
                <h3>{stage.label}</h3>
              </div>
              <p className="book-processing-stage-status">
                {loading ? '读取进度' : stageStatusText(stage)}
              </p>
              {pending && <p className="book-processing-stage-pending">{pending}</p>}
              {stage.events.length > 0 && (
                <ul className="book-processing-stage-events">
                  {stage.events.map((event, eventIndex) => (
                    <li
                      key={`${event.sequence}-${event.label}-${eventIndex}`}
                    >
                      <span>{event.label}</span>
                      {event.detail && <small>{event.detail}</small>}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function BookOpenProcessMark() {
  return (
    <div className="book-processing-mark" aria-hidden="true">
      <WandSparkles className="size-5" />
    </div>
  );
}
