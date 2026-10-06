import { useRef, useState, type ReactNode } from 'react';
import { FileText, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { cn } from '@/lib/utils';
import { useScrollMemory } from '@/lib/scrollMemory';
import type { BookSourceSlice, KnowledgePointMaterial } from '../types';
import EducationMarkdown from './EducationMarkdown';
import {
  BookGenerationForm,
  type BookGenerationValues,
} from './BookGenerationForm';

interface BookReaderProps {
  title: string;
  view: 'material' | 'source' | 'original';
  originalContent?: ReactNode;
  originalAvailable?: boolean;
  material?: KnowledgePointMaterial;
  source?: BookSourceSlice;
  loading?: boolean;
  generationPending?: boolean;
  canManageMaterials?: boolean;
  readingPositionKey?: string;
  continuous?: boolean;
  sourceHighlightRange?: { start: number; end: number };
  onViewChange: (view: 'material' | 'source' | 'original') => void;
  onGenerate?: (values: BookGenerationValues) => void | Promise<void>;
  onOpenMaterialLink?: (path: string) => void;
}

export function BookReader({
  title,
  view,
  material,
  source,
  originalContent,
  loading = false,
  generationPending = false,
  canManageMaterials = false,
  readingPositionKey,
  continuous = false,
  sourceHighlightRange,
  onGenerate,
  onOpenMaterialLink,
}: BookReaderProps) {
  const [formOpen, setFormOpen] = useState(false);
  const [confirmation, setConfirmation] = useState<BookGenerationValues | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [generationError, setGenerationError] = useState<string | null>(null);
  const submissionRef = useRef(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const hasMaterial = Boolean(material?.material_available && material.markdown);
  const canGenerate = Boolean(canManageMaterials && material && onGenerate);
  const pending = generationPending || submitting;
  const submitGeneration = async (values: BookGenerationValues) => {
    if (!canGenerate || !onGenerate || pending || submissionRef.current) return;
    submissionRef.current = true;
    setSubmitting(true);
    setGenerationError(null);
    try {
      await onGenerate(values);
      setConfirmation(null);
      setFormOpen(false);
    } catch {
      setGenerationError('提交失败，请重试。现有讲义仍然保留。');
    } finally {
      submissionRef.current = false;
      setSubmitting(false);
    }
  };
  useScrollMemory(scrollRef, readingPositionKey ?? `book-reader:${title}:${view}`, {
    persist: true,
    ready: !continuous && !loading && (view === 'material' && hasMaterial || Boolean(source)),
  });

  return (
    <article className={cn('book-reader flex min-h-0 flex-col bg-background', continuous ? 'book-reader-continuous' : 'h-full')} aria-label={`阅读 ${title}`}>
      <header className="book-reader-header border-b px-4 py-2 sm:px-6">
        <div className="flex min-h-9 items-center justify-between gap-3">
          <div className="min-w-0">
            <h1 className="education-heading-h1" title={title}>{title}</h1>
          </div>
          {canGenerate && (
            <Button
              type="button"
              className="h-8 shrink-0 gap-1.5 px-2.5 text-xs"
              onClick={() => setFormOpen(true)}
              disabled={pending}
              aria-label={hasMaterial ? '重新生成讲义' : '生成讲义'}
              title={hasMaterial ? '重新生成讲义' : '生成讲义'}
            >
              <Sparkles className="size-4" aria-hidden="true" />
              {hasMaterial ? '重新生成讲义' : '生成讲义'}
            </Button>
          )}
        </div>
      </header>

      {formOpen && canGenerate && (
        <BookGenerationForm
          existingMaterial={hasMaterial}
          pending={pending}
          onCancel={() => setFormOpen(false)}
          onSubmit={(values) => {
            setGenerationError(null);
            if (hasMaterial && values.replaceExisting) setConfirmation(values);
            else return submitGeneration(values);
          }}
        />
      )}
      {generationError && !confirmation && <p role="alert" className="px-4 py-2 text-sm text-destructive">{generationError}</p>}
      <Dialog open={canGenerate && Boolean(confirmation)} onOpenChange={(open) => {
        if (!open && !pending) setConfirmation(null);
      }}>
        <DialogContent className="sm:max-w-md" dismissible={!pending}>
          <DialogHeader>
            <DialogTitle>确认重新生成讲义？</DialogTitle>
            <DialogDescription>新讲义生成成功后将替换当前讲义。生成失败时仍保留现有讲义。</DialogDescription>
          </DialogHeader>
          {generationError && <p role="alert" className="text-sm text-destructive">{generationError}</p>}
          <DialogFooter className="gap-2">
            <Button variant="outline" disabled={pending} onClick={() => setConfirmation(null)}>保留现有讲义</Button>
            <Button disabled={pending} onClick={() => {
              if (confirmation) void submitGeneration(confirmation);
            }}>{pending ? '正在提交' : '确认重新生成'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <div
        ref={scrollRef}
        data-testid="book-reader-scroll"
        className={cn('book-reader-scroll min-h-0', !continuous && 'flex-1 overflow-y-auto', view !== 'original' && 'book-reader-prose')}
      >
        {view === 'original' ? originalContent : loading ? (
          <p className="text-sm text-muted-foreground">正在加载正文…</p>
        ) : view === 'material' && hasMaterial ? (
          <EducationMarkdown
            content={material?.markdown ?? ''}
            onOpenFile={onOpenMaterialLink}
          />
        ) : source ? (
          <div>
            <div className="mb-5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <FileText className="size-4" aria-hidden="true" />
              原书内容
              {view === 'source' && (
                <span>第 {sourceHighlightRange?.start ?? source.start_line}–{sourceHighlightRange?.end ?? source.end_line} 行，共 {source.total_lines} 行</span>
              )}
            </div>
            <EducationMarkdown
              content={source.markdown}
              sourceLineOffset={source.start_line - 1}
              highlightSourceRange={sourceHighlightRange}
            />
          </div>
        ) : (
          <p className="py-10 text-center text-sm text-muted-foreground">当前内容暂不可读</p>
        )}
      </div>
    </article>
  );
}
