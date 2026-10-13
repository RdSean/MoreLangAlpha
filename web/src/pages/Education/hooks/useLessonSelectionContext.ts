import { useCallback, useEffect, useState, type RefObject } from 'react';
import type { QuotedContext } from '@/lib/quotedContext';
import { captureLessonAnchor, type LessonAnchor } from '../components/lessonAnnotationAnchors';

interface LessonSelection extends QuotedContext {
  lineCount: number;
  left: number;
  top: number;
  anchor?: LessonAnchor | null;
}

function elementFor(node: Node | null): Element | null {
  return node instanceof Element ? node : node?.parentElement ?? null;
}

/** Only prose in this mounted lesson may become question context. */
export function useLessonSelectionContext(containerRef: RefObject<HTMLDivElement | null>, disabled: boolean) {
  const [selection, setSelection] = useState<LessonSelection | null>(null);
  const [quotes, setQuotes] = useState<QuotedContext[]>([]);
  const dismiss = useCallback(() => setSelection(null), []);

  useEffect(() => {
    if (disabled) { setSelection(null); return; }
    const container = containerRef.current;
    if (!container) return;
    const update = () => {
      const current = window.getSelection();
      if (!current || current.isCollapsed || current.rangeCount !== 1 || !current.toString().trim()) {
        setSelection(null);
        return;
      }
      const range = current.getRangeAt(0);
      const start = elementFor(range.startContainer);
      const end = elementFor(range.endContainer);
      const markdown = start?.closest('[data-education-markdown]');
      const source = markdown?.closest('.lesson-original') ? 'lesson' : markdown?.closest('.lesson-turn-answer') ? 'answer' : null;
      const interactive = 'button, input, textarea, select, [contenteditable="true"]';
      if (!markdown || !source || !container.contains(markdown) || end?.closest('[data-education-markdown]') !== markdown
        || start?.closest(interactive) || end?.closest(interactive)) {
        setSelection(null);
        return;
      }
      const bounds = container.getBoundingClientRect();
      const viewport = window.visualViewport;
      const leftEdge = Math.max(bounds.left, viewport?.offsetLeft ?? 0) + 8;
      const rightEdge = Math.min(bounds.right, (viewport?.offsetLeft ?? 0) + (viewport?.width ?? window.innerWidth)) - 8;
      const topEdge = Math.max(bounds.top, viewport?.offsetTop ?? 0) + 8;
      const bottomEdge = Math.min(bounds.bottom, (viewport?.offsetTop ?? 0) + (viewport?.height ?? window.innerHeight)) - 8;
      // The 44px control always stays inside the scroll region, above the composer.
      if (rightEdge - leftEdge < 160 || bottomEdge - topEdge < 44) { setSelection(null); return; }
      const rect = Array.from(range.getClientRects()).find((item) => item.width > 0 && item.bottom > topEdge && item.top < bottomEdge);
      if (!rect) { setSelection(null); return; }
      const text = current.toString().trim();
      const lines = text.split('\n').length;
      const preferBelow = window.matchMedia('(pointer: coarse)').matches;
      setSelection({
        anchor: source === 'lesson' ? captureLessonAnchor(markdown, range) : null,
        text, source, label: `${source === 'lesson' ? '讲义选段' : '回答选段'} · ${lines} 行`, lineCount: lines,
        left: Math.max(leftEdge, Math.min(rect.left + rect.width / 2 - 80, rightEdge - 160)),
        top: Math.max(topEdge, Math.min(!preferBelow && rect.top - 52 >= topEdge ? rect.top - 52 : rect.bottom + 8, bottomEdge - 44)),
      });
    };
    const keydown = (event: KeyboardEvent) => { if (event.key === 'Escape') dismiss(); };
    // Selection changes fire continuously while the pointer is dragging. Keep
    // them out of React and let the terminal pointer/keyboard event decide
    // when to measure and render the action, matching Flash chat.
    let pendingUpdate: number | null = null;
    const scheduleUpdate = () => {
      if (pendingUpdate !== null) window.clearTimeout(pendingUpdate);
      pendingUpdate = window.setTimeout(() => { pendingUpdate = null; update(); }, 10);
    };
    const pointerup = () => scheduleUpdate();
    const keyup = (event: KeyboardEvent) => { if (event.key !== 'Escape') scheduleUpdate(); };
    document.addEventListener('pointerup', pointerup);
    document.addEventListener('keyup', keyup);
    document.addEventListener('keydown', keydown);
    window.addEventListener('scroll', dismiss, true);
    window.addEventListener('resize', dismiss);
    window.visualViewport?.addEventListener('resize', dismiss);
    window.visualViewport?.addEventListener('scroll', dismiss);
    return () => {
      if (pendingUpdate !== null) window.clearTimeout(pendingUpdate);
      document.removeEventListener('pointerup', pointerup);
      document.removeEventListener('keyup', keyup);
      document.removeEventListener('keydown', keydown);
      window.removeEventListener('scroll', dismiss, true);
      window.removeEventListener('resize', dismiss);
      window.visualViewport?.removeEventListener('resize', dismiss);
      window.visualViewport?.removeEventListener('scroll', dismiss);
    };
  }, [containerRef, disabled, dismiss]);

  const addSelection = () => {
    if (!selection || disabled) return;
    const { text, source, label } = selection;
    setQuotes((previous) => previous.some((quote) => quote.text === text && quote.source === source)
      ? previous : [...previous, { text, source, label }]);
    window.getSelection()?.removeAllRanges();
    dismiss();
  };

  return { selection, quotes, addSelection, dismiss,
    removeQuote: (index: number) => setQuotes((previous) => previous.filter((_, current) => current !== index)),
    clearQuotes: () => setQuotes([]),
  };
}
