import type { ComponentProps } from 'react';
import { BookReader } from './BookReader';
import LessonConversation from './LessonConversation';
import { BookLessonExport } from './BookLessonExport';

export function BookLessonReader({ textbookId, assignmentId, ...props }: ComponentProps<typeof BookReader> & { textbookId?: string; assignmentId?: string }) {
  const reader = <BookReader {...props} />;
  if (!textbookId || props.view !== 'material' || !props.material?.material_available || !props.material.markdown) return reader;
  const material = props.material;
  return <LessonConversation key={`${textbookId}:${assignmentId ?? ''}:${material.knowledge_point_id}`} textbookId={textbookId} assignmentId={assignmentId} knowledgePointId={material.knowledge_point_id} readingPositionKey={props.readingPositionKey}>
    {({ questionsBusy }) => <BookReader {...props} continuous headerActions={<BookLessonExport key={material.knowledge_point_id} textbookId={textbookId} assignmentId={assignmentId} knowledgePointId={material.knowledge_point_id} markdown={material.markdown ?? ''} questionsBusy={questionsBusy} />} />}
  </LessonConversation>;
}
