import type { ComponentProps } from 'react';
import { BookReader } from './BookReader';
import LessonConversation from './LessonConversation';

export function BookLessonReader({ textbookId, assignmentId, ...props }: ComponentProps<typeof BookReader> & { textbookId?: string; assignmentId?: string }) {
  const reader = <BookReader {...props} />;
  if (!textbookId || props.view !== 'material' || !props.material?.material_available || !props.material.markdown) return reader;
  return <LessonConversation key={`${textbookId}:${assignmentId ?? ''}:${props.material.knowledge_point_id}`} textbookId={textbookId} assignmentId={assignmentId} knowledgePointId={props.material.knowledge_point_id} readingPositionKey={props.readingPositionKey}><BookReader {...props} continuous /></LessonConversation>;
}
