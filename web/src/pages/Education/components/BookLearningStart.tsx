import { useId, useState } from 'react';
import { ArrowRight, BookOpen, Check, ChevronDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import type { BookMaterialDepth } from '../types';
import type { BookGenerationValues } from './BookGenerationForm';
import './BookLearningStart.css';

interface BookLearningStartProps {
  onStart?: (values: BookGenerationValues) => void | Promise<void>;
  pending?: boolean;
  error?: string | null;
}

const MODES = [
  { value: 'summary', label: '简洁', description: '快速掌握核心观点与重点知识' },
  { value: 'lesson', label: '标准', description: '完整讲解知识点，配合例子帮助理解' },
  { value: 'deep', label: '深入', description: '深入分析原理，拓展应用与易错点' },
  { value: 'custom', label: '自定义', description: '选择讲解深度，补充你的学习要求' },
] as const;
type LearningMode = typeof MODES[number]['value'];

export function BookLearningStart({ onStart, pending = false, error }: BookLearningStartProps) {
  const [mode, setMode] = useState<LearningMode>('lesson');
  const [depth, setDepth] = useState<BookMaterialDepth>('lesson');
  const [requirements, setRequirements] = useState('');
  const depthId = useId();
  const requirementsId = useId();
  const currentMode = MODES.find((entry) => entry.value === mode)!;
  return (
    <section className="book-learning-start" aria-label="开始知识点学习">
      <div className="book-learning-start-icon" aria-hidden="true">
        <BookOpen size={36} strokeWidth={1.6} />
        <span><Check size={14} strokeWidth={3} /></span>
      </div>
      <span className="book-learning-start-status">{pending ? 'PREPARING' : 'READY'}</span>
      <h2>{pending ? '正在准备课程' : onStart ? '准备就绪' : '等待家长准备课程'}</h2>
      <p>{pending ? '课程准备好后，即可开始学习' : onStart ? '点击下方按钮，AI 将为你讲解这个知识点' : '课程准备好后，即可开始学习这个知识点'}</p>
      {onStart && (
        <form className="book-learning-start-form" onSubmit={(event) => {
          event.preventDefault();
          if (pending) return;
          void onStart({
            depth: mode === 'custom' ? depth : mode,
            requirements: mode === 'custom' ? requirements.trim() || null : null,
            replaceExisting: false,
            includeSupplementary: false,
          });
        }}>
          <div className="book-learning-start-actions">
            <Button type="submit" disabled={pending} className="book-learning-start-button">
              {pending ? '正在准备课程' : '开始学习'}{!pending && <ArrowRight size={16} aria-hidden="true" />}
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button type="button" disabled={pending} className="book-learning-mode-button" aria-label="选择讲解模式">
                  {currentMode.label}<ChevronDown size={14} aria-hidden="true" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" alignOffset={-120} sideOffset={8} className="book-learning-mode-menu">
                <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">讲解模式</DropdownMenuLabel>
                {MODES.map((entry) => (
                  <DropdownMenuItem key={entry.value} onSelect={() => setMode(entry.value)} className="items-start py-3">
                    <Check size={16} aria-hidden="true" className={mode === entry.value ? 'mt-0.5 shrink-0 text-[var(--color-accent-primary)]' : 'invisible mt-0.5 shrink-0'} />
                    <span className="min-w-0"><span className="block font-medium">{entry.label}</span><span className="mt-1 block text-xs leading-5 text-muted-foreground">{entry.description}</span></span>
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
          {error && <p role="alert" className="mt-4 text-sm text-destructive">{error}</p>}
          {mode === 'custom' && (
            <div className="book-learning-custom">
              <label htmlFor={depthId}>讲解深度</label>
              <select id={depthId} value={depth} disabled={pending} onChange={(event) => setDepth(event.target.value as BookMaterialDepth)}>
                <option value="summary">简洁</option><option value="lesson">标准</option><option value="deep">深入</option>
              </select>
              <label htmlFor={requirementsId}>补充要求（可选）</label>
              <textarea id={requirementsId} value={requirements} maxLength={8000} rows={3} disabled={pending} placeholder="例如：多给两个例子，重点讲解容易混淆的概念" onChange={(event) => setRequirements(event.target.value)} />
            </div>
          )}
        </form>
      )}
    </section>
  );
}
