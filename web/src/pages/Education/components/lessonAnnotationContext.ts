import { createContext, useContext } from 'react';
import type { LearningItem } from '../types';
import type { LessonAnchor } from './lessonAnnotationAnchors';

export interface LessonAnnotationContext {
  items: LearningItem[];
  open: (itemId: string) => void;
  create: (kind: 'highlight' | 'note', anchor: LessonAnchor) => void;
  error: boolean;
  loading: boolean;
  retry: () => void;
}
export const AnnotationContext = createContext<LessonAnnotationContext | null>(null);
export const useLessonAnnotations = () => useContext(AnnotationContext);
