import { useId, useState } from 'react';
import { LoaderCircle, Sparkles, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { BookMaterialDepth } from '../types';

export interface BookGenerationValues {
  depth: BookMaterialDepth;
  requirements: string | null;
  replaceExisting: boolean;
  includeSupplementary: boolean;
}

interface BookGenerationFormProps {
  existingMaterial?: boolean;
  targetCount?: number;
  existingCount?: number;
  allowSupplementary?: boolean;
  pending?: boolean;
  onSubmit: (values: BookGenerationValues) => void | Promise<void>;
  onCancel: () => void;
}

const DEPTHS: Array<{ value: BookMaterialDepth; label: string }> = [
  { value: 'summary', label: '快速摘要' },
  { value: 'lesson', label: '标准讲义' },
  { value: 'deep', label: '深入讲解' },
];

export function BookGenerationForm({
  existingMaterial = false,
  targetCount = 1,
  existingCount = existingMaterial ? 1 : 0,
  allowSupplementary = false,
  pending = false,
  onSubmit,
  onCancel,
}: BookGenerationFormProps) {
  const requirementsId = useId();
  const [depth, setDepth] = useState<BookMaterialDepth>('lesson');
  const [requirements, setRequirements] = useState('');
  const [replaceExisting, setReplaceExisting] = useState(existingMaterial);
  const [includeSupplementary, setIncludeSupplementary] = useState(false);
  const missingCount = Math.max(0, targetCount - existingCount);
  const replacementLabel = targetCount > 1
    ? `重新生成所选 ${targetCount} 份（将替换 ${existingCount} 份已有讲义）`
    : '重新生成讲义（生成失败时仍保留旧讲义）';
  const heading = replaceExisting
    ? targetCount > 1 ? `重新生成所选 ${targetCount} 份讲义` : '重新生成讲义'
    : existingCount > 0 ? `生成未生成的 ${missingCount} 份讲义`
      : targetCount > 1 ? `生成 ${targetCount} 份讲义` : '生成讲义';

  return (
    <form
      className="border-b bg-muted/35 px-4 py-4 sm:px-6"
      onSubmit={(event) => {
        event.preventDefault();
        void onSubmit({
          depth,
          requirements: requirements.trim() || null,
          replaceExisting,
          includeSupplementary,
        });
      }}
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-semibold text-foreground">
            {heading}
          </h3>
          <p className="mt-1 text-xs text-muted-foreground">本次参数提交后不可修改。</p>
        </div>
        <button
          type="button"
          className="inline-flex size-11 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-[var(--color-bg-hover)]"
          onClick={onCancel}
          aria-label="关闭生成设置"
        >
          <X className="size-4" aria-hidden="true" />
        </button>
      </div>

      <fieldset className="mt-4">
        <legend className="text-xs font-medium text-muted-foreground">讲解深度</legend>
        <div className="mt-2 grid grid-cols-3 rounded-md bg-muted p-1" role="radiogroup">
          {DEPTHS.map((option) => (
            <button
              key={option.value}
              type="button"
              role="radio"
              aria-checked={depth === option.value}
              className={cn(
                'min-h-10 rounded px-2 text-xs sm:text-sm',
                depth === option.value && 'bg-background font-medium shadow-sm',
              )}
              onClick={() => setDepth(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </fieldset>

      <label htmlFor={requirementsId} className="mt-4 block text-xs font-medium text-muted-foreground">
        补充要求（可选）
      </label>
      <textarea
        id={requirementsId}
        value={requirements}
        maxLength={8_000}
        rows={3}
        className="mt-2 w-full resize-y rounded-md border bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
        placeholder="例如：增加例题，或重点解释容易混淆的概念"
        onChange={(event) => setRequirements(event.target.value)}
      />

      {(existingCount > 0 || allowSupplementary) && (
        <div className="mt-3 grid gap-2 text-sm">
          {existingCount > 0 && (
            <label className="flex min-h-10 items-center gap-2">
              <input
                type="checkbox"
                checked={replaceExisting}
                onChange={(event) => setReplaceExisting(event.target.checked)}
                className="size-4"
              />
              {replacementLabel}
            </label>
          )}
          {allowSupplementary && (
            <label className="flex min-h-10 items-center gap-2">
              <input
                type="checkbox"
                checked={includeSupplementary}
                onChange={(event) => setIncludeSupplementary(event.target.checked)}
                className="size-4"
              />
              同时生成全书附加材料
            </label>
          )}
        </div>
      )}

      <div className="mt-4 flex flex-wrap justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onCancel} disabled={pending}>取消</Button>
        <Button type="submit" disabled={pending || (!replaceExisting && missingCount === 0)}>
          {pending
            ? <LoaderCircle className="mr-2 size-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
            : <Sparkles className="mr-2 size-4" aria-hidden="true" />}
          {pending ? '正在提交' : '开始生成'}
        </Button>
      </div>
    </form>
  );
}
