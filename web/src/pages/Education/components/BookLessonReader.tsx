import type { ComponentProps, ReactNode } from 'react';
import { Columns2, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { BookReader } from './BookReader';
import LessonConversation from './LessonConversation';
import { BookLessonExport } from './BookLessonExport';
import './BookLessonReader.css';
import { LessonAnnotationsProvider } from './LessonAnnotations';

interface ComparisonProps {
  comparisonEnabled?: boolean;
  onComparisonChange?: (enabled: boolean) => void;
  comparisonContent?: ReactNode;
}

export function BookLessonReader({ textbookId, assignmentId, annotationNodeId, comparisonEnabled = false, onComparisonChange, comparisonContent, ...props }: ComponentProps<typeof BookReader> & { textbookId?: string; assignmentId?: string; annotationNodeId?: string } & ComparisonProps) {
  const { t } = useTranslation();
  const reader = <BookReader {...props} />;
  if (!textbookId || props.view !== 'material' || !props.material?.material_available || !props.material.markdown) return reader;
  const material = props.material;
  const toggleLabel = t(comparisonEnabled ? 'bookProcessing.closeComparison' : 'bookProcessing.compareOriginal');
  const comparisonButton = onComparisonChange ? <TooltipProvider delayDuration={300}><Tooltip><TooltipTrigger asChild>
    <Button type="button" variant="ghost" size="icon" className="size-11 shrink-0" aria-label={toggleLabel} aria-pressed={comparisonEnabled} onClick={() => onComparisonChange(!comparisonEnabled)}>
      <Columns2 className="size-4" aria-hidden="true" />
    </Button>
  </TooltipTrigger><TooltipContent>{toggleLabel}</TooltipContent></Tooltip></TooltipProvider> : null;
  const layout = <div className="book-lesson-container"><div className={`book-lesson-layout${comparisonEnabled ? ' is-comparing' : ''}`}>
    <div className="book-lesson-primary">
      <LessonConversation key={`${textbookId}:${assignmentId ?? ''}:${material.knowledge_point_id}`} textbookId={textbookId} assignmentId={assignmentId} knowledgePointId={material.knowledge_point_id} readingPositionKey={props.readingPositionKey}>
        {({ questionsBusy }) => <BookReader {...props} continuous headerActions={<>
          {comparisonButton}
          <BookLessonExport key={material.knowledge_point_id} textbookId={textbookId} assignmentId={assignmentId} knowledgePointId={material.knowledge_point_id} markdown={material.markdown ?? ''} questionsBusy={questionsBusy} />
        </>} />}
      </LessonConversation>
    </div>
    {comparisonEnabled && <aside className="book-lesson-original" aria-label={t('bookProcessing.comparisonOriginal')}>
      <header className="book-lesson-original-header">
        <span>{t('bookProcessing.sourceContents')}</span>
        <Button type="button" variant="ghost" size="icon" className="size-11 shrink-0" aria-label={t('common.close')} title={t('bookProcessing.closeComparison')} onClick={() => onComparisonChange?.(false)}><X className="size-4" aria-hidden="true" /></Button>
      </header>
      <div className="book-lesson-original-content">{comparisonContent}</div>
    </aside>}
  </div></div>;
  return assignmentId ? <LessonAnnotationsProvider key={`${assignmentId}:${material.knowledge_point_id}`} assignmentId={assignmentId} knowledgePointId={material.knowledge_point_id} skillNodeId={annotationNodeId}>{layout}</LessonAnnotationsProvider> : layout;
}
