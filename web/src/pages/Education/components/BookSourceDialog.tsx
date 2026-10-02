import { useEffect, useMemo, useRef, useState } from 'react';
import { BookOpenCheck, LoaderCircle, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { useManagedBookMutations, useManagedBookSourceCandidates } from '../queries';
import type { BookSourceCandidate, CreateManagedTextbookResponse } from '../types';

interface BookSourceDialogProps {
  open: boolean;
  defaultDocumentId?: string;
  onOpenChange: (open: boolean) => void;
  onCreated: (result: CreateManagedTextbookResponse) => void;
}

function defaultTitle(filename: string): string {
  return filename.replace(/\.[^.]+$/, '').trim() || filename;
}

function sourceKey(source: BookSourceCandidate): string {
  return `${source.parse_job_id}:${source.primary_artifact_id}`;
}

function createRequestId(): string {
  return typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `book-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function BookSourceDialog({
  open,
  defaultDocumentId,
  onOpenChange,
  onCreated,
}: BookSourceDialogProps) {
  const sources = useManagedBookSourceCandidates(open);
  const mutations = useManagedBookMutations();
  const requestId = useRef(createRequestId());
  const [selectedKey, setSelectedKey] = useState('');
  const [title, setTitle] = useState('');
  const [submitError, setSubmitError] = useState(false);
  const candidates = useMemo(() => (sources.data ?? [])
    .filter((source) => !defaultDocumentId || source.document_id === defaultDocumentId)
    .sort((left, right) => Date.parse(right.completed_at) - Date.parse(left.completed_at)), [defaultDocumentId, sources.data]);
  const selected = candidates.find((candidate) => sourceKey(candidate) === selectedKey);

  useEffect(() => {
    if (!open) return;
    const next = candidates[0];
    setSelectedKey(next ? sourceKey(next) : '');
    setTitle(next ? defaultTitle(next.filename) : '');
    setSubmitError(false);
    requestId.current = createRequestId();
  }, [candidates, open]);

  const select = (candidate: BookSourceCandidate) => {
    setSelectedKey(sourceKey(candidate));
    setTitle(defaultTitle(candidate.filename));
    setSubmitError(false);
    requestId.current = createRequestId();
  };

  const submit = async () => {
    if (!selected || !title.trim()) return;
    setSubmitError(false);
    try {
      const result = await mutations.createTextbook.mutateAsync({
        parse_job_id: selected.parse_job_id,
        primary_artifact_id: selected.primary_artifact_id,
        title: title.trim(),
        idempotency_key: requestId.current,
      });
      onCreated(result);
    } catch {
      setSubmitError(true);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent variant="centered" className="max-h-[min(720px,90vh)] max-w-xl overflow-hidden">
        <DialogHeader>
          <DialogTitle>选择教材来源</DialogTitle>
        </DialogHeader>

        {sources.isLoading ? (
          <div className="flex min-h-36 items-center justify-center gap-2 text-sm text-muted-foreground" role="status">
            <LoaderCircle className="size-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
            正在读取可用解析结果…
          </div>
        ) : sources.isError ? (
          <div className="grid min-h-36 place-content-center gap-3 text-center text-sm" role="alert">
            <p className="text-muted-foreground">无法读取教材来源。</p>
            <Button type="button" variant="outline" size="sm" onClick={() => void sources.refetch()}>
              <RefreshCw className="mr-2 size-4" aria-hidden="true" />
              重试
            </Button>
          </div>
        ) : candidates.length === 0 ? (
          <div className="grid min-h-36 place-content-center gap-2 text-center text-sm text-muted-foreground">
            <BookOpenCheck className="mx-auto size-5" aria-hidden="true" />
            <p>没有可用的 Markdown 解析结果。</p>
          </div>
        ) : (
          <form
            className="min-h-0"
            onSubmit={(event) => {
              event.preventDefault();
              void submit();
            }}
          >
            <fieldset>
              <legend className="text-xs font-medium text-muted-foreground">解析结果</legend>
              <div className="mt-2 max-h-64 space-y-2 overflow-y-auto pr-1">
                {candidates.map((candidate) => {
                  const key = sourceKey(candidate);
                  const checked = key === selectedKey;
                  return (
                    <label key={key} className={`flex cursor-pointer gap-3 rounded-md border p-3 ${checked ? 'border-primary bg-primary/5' : 'border-border'}`}>
                      <input
                        type="radio"
                        name="book-source"
                        value={key}
                        checked={checked}
                        onChange={() => select(candidate)}
                        className="mt-1 size-4"
                      />
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-medium text-foreground">{candidate.filename}</span>
                        <span className="mt-1 block text-xs text-muted-foreground">
                          {new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(candidate.completed_at))}
                          {' · '}{candidate.parser_name}
                        </span>
                      </span>
                    </label>
                  );
                })}
              </div>
            </fieldset>

            <label className="mt-4 block text-sm font-medium text-foreground" htmlFor="textbook-source-title">教材名称</label>
            <Input
              id="textbook-source-title"
              className="mt-2"
              value={title}
              maxLength={240}
              required
              onChange={(event) => setTitle(event.target.value)}
            />
            {submitError && <p className="mt-2 text-sm text-destructive" role="alert">添加教材失败，请重试。</p>}

            <DialogFooter className="mt-5">
              <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>取消</Button>
              <Button type="submit" disabled={!selected || !title.trim() || mutations.createTextbook.isPending}>
                {mutations.createTextbook.isPending && <LoaderCircle className="mr-2 size-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />}
                添加并分析
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
