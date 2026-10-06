import { useRef, useState, type ReactNode } from 'react';
import { FileText, RefreshCw, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
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
  readingPositionKey?: string;
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
  readingPositionKey,
  sourceHighlightRange,
  onGenerate,
  onOpenMaterialLink,
}: BookReaderProps) {
  const [formOpen, setFormOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const hasMaterial = Boolean(material?.material_available && material.markdown);
  const canGenerate = Boolean(material && onGenerate);
  useScrollMemory(scrollRef, readingPositionKey ?? `book-reader:${title}:${view}`, {
    persist: true,
    ready: !loading && (view === 'material' && hasMaterial || Boolean(source)),
  });

  return (
    <article className="book-reader flex h-full min-h-0 flex-col bg-background" aria-label={`阅读 ${title}`}>
      <header className="book-reader-header border-b px-4 py-2 sm:px-6">
        <div className="flex min-h-9 items-center justify-between gap-3">
          <div className="min-w-0">
            <h1 className="break-words text-base font-semibold text-foreground">{title}</h1>
            {view === 'source' && source && (
              <p className="mt-1 text-xs text-muted-foreground">
                第 {sourceHighlightRange?.start ?? source.start_line}–{sourceHighlightRange?.end ?? source.end_line} 行，共 {source.total_lines} 行
              </p>
            )}
          </div>
          {canGenerate && (
            <Button
              type="button"
              variant="outline"
              className="size-8 shrink-0 p-0"
              onClick={() => setFormOpen(true)}
              disabled={generationPending}
              aria-label={hasMaterial ? '重新生成讲义' : '生成讲义'}
              title={hasMaterial ? '重新生成讲义' : '生成讲义'}
            >
              {hasMaterial
                ? <RefreshCw className="size-4" aria-hidden="true" />
                : <Sparkles className="size-4" aria-hidden="true" />}
            </Button>
          )}
        </div>
      </header>

      {formOpen && onGenerate && (
        <BookGenerationForm
          existingMaterial={hasMaterial}
          pending={generationPending}
          onCancel={() => setFormOpen(false)}
          onSubmit={async (values) => {
            await onGenerate(values);
            setFormOpen(false);
          }}
        />
      )}

      <div
        ref={scrollRef}
        data-testid="book-reader-scroll"
        className={cn('book-reader-scroll min-h-0 flex-1 overflow-y-auto', view !== 'original' && 'book-reader-prose')}
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
            <div className="mb-5 flex items-center gap-2 text-xs text-muted-foreground">
              <FileText className="size-4" aria-hidden="true" />
              原书内容
            </div>
            <EducationMarkdown
              content={source.markdown}
              sourceLineOffset={source.start_line - 1}
              highlightSourceRange={sourceHighlightRange ?? {
                start: source.start_line,
                end: source.end_line,
              }}
            />
          </div>
        ) : (
          <p className="py-10 text-center text-sm text-muted-foreground">当前内容暂不可读</p>
        )}
      </div>
    </article>
  );
}
