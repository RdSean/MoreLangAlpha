import { useRef, useState } from 'react';
import { ArrowLeft, CheckCircle2, Loader2, WandSparkles } from 'lucide-react';
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
import { Textarea } from '@/components/ui/textarea';
import { useToast } from '@/components/ui/use-toast';
import { useBookPipelineMutations, useTextbook } from './queries';
import type { BookPipelineJob } from './types';
import './BookProcessingPage.css';

const processingBriefPlaceholder =
  '例如：这是一本法语教材；忽略教师指导页；只提取学生活动页；数学教材中的公式和例题请按原顺序保留。';

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

        {job ? (
          <section
            className="book-processing-status"
            aria-label="教材处理任务"
          >
            <CheckCircle2 className="size-5" aria-hidden="true" />
            <div>
              <h2>处理任务已创建</h2>
              <p>
                {job.reused_existing_job
                  ? '已复用同一教材正在进行的处理任务。'
                  : '任务已进入处理队列。'}
              </p>
              <p className="book-processing-job-id">
                任务编号 {job.generation_job_id}
              </p>
            </div>
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

function BookOpenProcessMark() {
  return (
    <div className="book-processing-mark" aria-hidden="true">
      <WandSparkles className="size-5" />
    </div>
  );
}
