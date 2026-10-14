import { useCallback, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Highlighter, NotebookPen, Pencil, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useLearningAssetMutations, useStudentLearningItems } from '../queries';
import type { LearningItem } from '../types';
import { ANNOTATION_COLORS, annotationColorLabels, annotationColorTokens, parseLessonAnchor, type LessonAnchor } from './lessonAnnotationAnchors';
import EducationMarkdown from './EducationMarkdown';
import './LessonAnnotations.css';
import { AnnotationContext, useLessonAnnotations } from './lessonAnnotationContext';

interface Draft { item?: LearningItem; kind: 'highlight' | 'note'; anchor: LessonAnchor | null; content: string; deleting?: boolean }
function ColorSwatches({ value, onChange, disabled }: { value: LessonAnchor['color']; onChange: (color: LessonAnchor['color']) => void; disabled: boolean }) {
  return <div className="lesson-annotation-colors" role="group" aria-label="标记颜色">
    {ANNOTATION_COLORS.map((color) => <button key={color} type="button" aria-label={annotationColorLabels[color]} title={annotationColorLabels[color]} aria-pressed={color === value} disabled={disabled}
      style={{ '--annotation-ink': annotationColorTokens[color] } as React.CSSProperties}
      onClick={() => onChange(color)}><span /></button>)}
  </div>;
}

export function LessonAnnotationsProvider({ assignmentId, knowledgePointId, skillNodeId, children }: { assignmentId: string; knowledgePointId: string; skillNodeId?: string; children: ReactNode }) {
  const query = useStudentLearningItems(assignmentId, { knowledgePointId });
  const mutations = useLearningAssetMutations();
  const items = useMemo(() => (query.data ?? []).filter((item) => item.kind === 'highlight' || item.kind === 'note'), [query.data]);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [pending, setPending] = useState(false);
  const operationGuard = useRef(false);
  const [error, setError] = useState('');
  const open = useCallback((itemId: string, action?: 'delete') => {
    const item = items.find((entry) => entry.item_id === itemId);
    if (!item) return;
    window.getSelection()?.removeAllRanges();
    setError('');
    setDraft({ item, kind: item.kind === 'note' ? 'note' : 'highlight', anchor: parseLessonAnchor(item.source_anchor), content: item.content, deleting: action === 'delete' });
  }, [items]);
  const create = useCallback((kind: 'highlight' | 'note', anchor: LessonAnchor) => {
    window.getSelection()?.removeAllRanges();
    setError(''); setDraft({ kind, anchor, content: kind === 'note' ? '' : anchor.exact });
  }, []);
  const { refetch, isError, isLoading } = query;
  const value = useMemo(() => ({ items, open, create, error: isError, loading: isLoading, retry: () => void refetch() }), [items, open, create, isError, isLoading, refetch]);
  const save = async (remove = false) => {
    if (!draft || operationGuard.current || (!remove && !draft.content.trim())) return;
    operationGuard.current = true; setPending(true); setError('');
    try {
      if (remove && draft.item) await mutations.remove.mutateAsync({ assignmentId, itemId: draft.item.item_id });
      else if (draft.item) await mutations.update.mutateAsync({ assignmentId, itemId: draft.item.item_id, content: draft.content, sourceAnchor: draft.anchor ?? draft.item.source_anchor });
      else await mutations.add.mutateAsync({ assignmentId, knowledgePointId, skillNodeId, kind: draft.kind, content: draft.content, sourceAnchor: draft.anchor });
      setDraft(null);
    } catch { setError(remove ? '删除失败，请重试。' : '保存失败，内容已保留，请重试。'); }
    finally { operationGuard.current = false; setPending(false); }
  };
  return <AnnotationContext.Provider value={value}>
    {children}
    <Dialog open={Boolean(draft)} onOpenChange={(value) => { if (!value && !pending) setDraft(null); }}>
      <DialogContent variant="centered" className="lesson-annotation-dialog" onEscapeKeyDown={(event) => { if (pending) event.preventDefault(); }} onPointerDownOutside={(event) => event.preventDefault()}>
        <DialogHeader><DialogTitle>{draft?.deleting ? '删除批注' : draft?.kind === 'note' ? '批注' : '标记'}</DialogTitle></DialogHeader>
        {draft && <>
          {draft.anchor && <blockquote className="lesson-annotation-quote">{draft.anchor.exact}</blockquote>}
          {draft.deleting ? <p className="lesson-annotation-delete-preview">{draft.content}</p> : <>
            {draft.anchor && <ColorSwatches value={draft.anchor.color} disabled={pending} onChange={(color) => setDraft({ ...draft, anchor: { ...draft.anchor!, color } })} />}
            {draft.kind === 'note' && <textarea autoFocus aria-label="批注内容" placeholder="写下你的理解" value={draft.content} disabled={pending} maxLength={20_000} onChange={(event) => setDraft({ ...draft, content: event.target.value })} />}
          </>}
          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
          <div className="lesson-annotation-dialog-actions">
            <Button variant="ghost" disabled={pending} onClick={() => setDraft(null)}>取消</Button>
            {draft.item && <Button variant="ghost" className="lesson-annotation-delete" disabled={pending} onClick={() => void save(true)}><Trash2 className="size-4" />{draft.kind === 'note' ? '删除批注' : '删除标记'}</Button>}
            {!draft.deleting && <Button className="ml-auto" disabled={pending || !draft.content.trim()} onClick={() => void save()}>{pending ? '正在保存' : draft.kind === 'note' ? '保存批注' : '保存标记'}</Button>}
          </div>
        </>}
      </DialogContent>
    </Dialog>
  </AnnotationContext.Provider>;
}

export function AnnotationSelectionActions({ anchor, onDone }: { anchor?: LessonAnchor | null; onDone: () => void }) {
  const annotations = useLessonAnnotations();
  if (!annotations || !anchor || annotations.error || annotations.loading) return null;
  return <>
    <button type="button" aria-label="标记选段" title="标记" onClick={() => { annotations.create('highlight', anchor); onDone(); }}><Highlighter className="size-4" />标记</button>
    <button type="button" aria-label="批注选段" title="批注" onClick={() => { annotations.create('note', anchor); onDone(); }}><NotebookPen className="size-4" />批注</button>
  </>;
}

export function AnnotatedLesson({ content, onOpenFile }: { content: string; onOpenFile?: (path: string) => void }) {
  const annotations = useLessonAnnotations();
  const rootRef = useRef<HTMLDivElement>(null);
  const notesRef = useRef<HTMLElement>(null);
  const layoutRef = useRef<HTMLDivElement>(null);
  const [positions, setPositions] = useState<Array<{ item: LearningItem; top: number }>>([]);
  const [marginHeight, setMarginHeight] = useState(0);
  const activate = (target: EventTarget | null) => {
    const element = target instanceof Element ? target : null;
    const id = element?.closest<HTMLElement>('[data-note-id]')?.dataset.noteId
      ?? element?.closest<HTMLElement>('[data-annotation-ids]')?.dataset.annotationIds?.split(' ')[0];
    // Hover/focus updates only the linked DOM decoration, not Markdown rendering.
    layoutRef.current?.querySelectorAll<HTMLElement>('[data-annotation-ids], [data-note-id]').forEach((node) => {
      if (id && (node.dataset.noteId === id || node.dataset.annotationIds?.split(' ').includes(id))) node.dataset.active = 'true';
      else delete node.dataset.active;
    });
  };
  const locate = (itemId: string) => {
    const mark = Array.from(rootRef.current?.querySelectorAll<HTMLElement>('[data-annotation-ids]') ?? [])
      .find((node) => node.dataset.annotationIds?.split(' ').includes(itemId));
    if (!mark) return;
    mark.focus({ preventScroll: true });
    mark.scrollIntoView({ block: 'center', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
    activate(mark);
  };
  useLayoutEffect(() => {
    const root = rootRef.current;
    if (!root || !annotations) return;
    const measure = () => {
      const layout = layoutRef.current;
      if (layout) layout.dataset.wide = String(layout.clientWidth >= 920);
      const notes = annotations.items.filter((item) => item.kind === 'note' && parseLessonAnchor(item.source_anchor));
      const marks = Array.from(root.querySelectorAll<HTMLElement>('[data-annotation-ids]'));
      const ordered = notes.flatMap((item) => {
        const mark = marks.find((element) => element.dataset.annotationIds?.split(' ').includes(item.item_id));
        return mark ? [{ item, top: mark.getBoundingClientRect().top - root.getBoundingClientRect().top }] : [];
      }).sort((a, b) => a.top - b.top);
      let bottom = 0;
      const next = ordered.map(({ item, top }) => {
        const card = Array.from(notesRef.current?.children ?? []).find((element) => (element as HTMLElement).dataset.noteId === item.item_id);
        const offset = Math.max(top, bottom);
        bottom = offset + (card?.getBoundingClientRect().height || 140) + 12;
        return { item, top: offset };
      });
      setMarginHeight(bottom);
      setPositions((previous) => previous.length === next.length && previous.every((value, index) => value.item === next[index].item && value.top === next[index].top) ? previous : next);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(root);
    if (layoutRef.current) observer.observe(layoutRef.current);
    if (notesRef.current) observer.observe(notesRef.current);
    Array.from(notesRef.current?.children ?? []).forEach((card) => observer.observe(card));
    return () => observer.disconnect();
  }, [content, annotations, positions]);
  if (!annotations) return <EducationMarkdown content={content} onOpenFile={onOpenFile} />;
  return <div className="lesson-annotation-container">
    {annotations.error && <p role="alert" className="lesson-annotation-status">标记与批注加载失败 <Button variant="ghost" size="sm" onClick={annotations.retry}>重试加载笔记</Button></p>}
    <div ref={layoutRef} className="lesson-annotation-layout"
      onPointerOver={(event) => activate(event.target)} onPointerOut={(event) => activate(event.relatedTarget)}
      onFocusCapture={(event) => activate(event.target)} onBlurCapture={(event) => activate(event.relatedTarget)}>
      <div ref={rootRef} className="lesson-annotation-prose"><EducationMarkdown content={content} onOpenFile={onOpenFile} annotationOptions={{ items: annotations.items, onOpen: annotations.open }} /></div>
      <aside ref={notesRef} className="lesson-annotation-margin" aria-label="正文批注" style={{ minHeight: marginHeight || undefined }}>
        {positions.map(({ item, top }, index) => <article key={item.item_id} aria-label={`批注 ${index + 1}`} data-note-id={item.item_id} data-annotation-color={parseLessonAnchor(item.source_anchor)?.color} className="lesson-margin-note" style={{ top }}>
          <button type="button" className="lesson-margin-quote" aria-label={`定位批注 ${index + 1} 原文`} title={parseLessonAnchor(item.source_anchor)?.exact} onClick={() => locate(item.item_id)}><span className="lesson-note-number">{index + 1}</span><span>{parseLessonAnchor(item.source_anchor)?.exact}</span></button>
          <p>{item.content}</p>
          <div className="lesson-margin-actions">
            <Button variant="ghost" size="sm" aria-label={`编辑批注 ${index + 1}`} onClick={() => annotations.open(item.item_id)}><Pencil className="size-3" />编辑</Button>
            <Button variant="ghost" size="sm" className="lesson-annotation-delete" aria-label={`删除批注 ${index + 1}`} onClick={() => annotations.open(item.item_id, 'delete')}><Trash2 className="size-3" />删除</Button>
          </div>
        </article>)}
      </aside>
    </div>
  </div>;
}
