import { z } from 'zod';

export const ANNOTATION_COLORS = ['olive', 'ochre', 'slate', 'brick'] as const;
export const annotationColorLabels = { olive: '橄榄色', ochre: '赭黄色', slate: '蓝灰色', brick: '砖红色' };
export const annotationColorTokens = { olive: 'var(--color-identity-1-fg)', ochre: 'var(--color-identity-2-fg)', slate: 'var(--color-identity-0-fg)', brick: 'var(--color-identity-3-fg)' };
const anchorSchema = z.object({
  version: z.literal(1), source: z.literal('lesson'),
  start: z.number().int().nonnegative(), end: z.number().int().positive(),
  exact: z.string().min(1).max(20_000), prefix: z.string().max(32), suffix: z.string().max(32),
  color: z.enum(ANNOTATION_COLORS).catch('olive'),
}).refine((value) => value.end > value.start && value.end - value.start === value.exact.length);
export type LessonAnchor = z.infer<typeof anchorSchema>;
export interface AnnotationItem { item_id: string; kind: string; source_anchor?: Record<string, unknown> | null }
interface TextNode {
  type?: string; tagName?: string; value?: string; properties?: Record<string, unknown>; children?: TextNode[];
}

export function parseLessonAnchor(input: unknown): LessonAnchor | null {
  const result = anchorSchema.safeParse(input);
  return result.success ? result.data : null;
}

export function resolveAnchor(text: string, anchor: LessonAnchor): { start: number; end: number } | null {
  const matches = (start: number) => text.slice(start, start + anchor.exact.length) === anchor.exact;
  const contextMatches = (start: number) => text.slice(Math.max(0, start - anchor.prefix.length), start) === anchor.prefix
    && text.slice(start + anchor.exact.length, start + anchor.exact.length + anchor.suffix.length) === anchor.suffix;
  if (matches(anchor.start) && contextMatches(anchor.start)) return { start: anchor.start, end: anchor.end };
  const candidates: number[] = [];
  for (let start = text.indexOf(anchor.exact); start !== -1; start = text.indexOf(anchor.exact, start + 1)) candidates.push(start);
  const contextual = candidates.filter(contextMatches);
  const start = contextual.length === 1 ? contextual[0] : candidates.length === 1 ? candidates[0] : undefined;
  return start === undefined ? null : { start, end: start + anchor.exact.length };
}

/** Runs after sanitization. Own text spans keep DOM offsets equal to AST offsets. */
export function annotationPlugin({ items }: { items: readonly AnnotationItem[] }) {
  return (tree: TextNode) => {
    const leaves: Array<{ node: TextNode; start: number; end: number }> = [];
    let text = '';
    const collect = (node: TextNode) => {
      if (['pre', 'code', 'math', 'svg', 'button', 'script', 'style', 'cite-bubble'].includes(node.tagName ?? '')) return;
      const classes = String(node.properties?.className ?? '');
      if (classes.includes('katex')) return;
      if (node.type === 'text' && node.value?.trim()) {
        leaves.push({ node, start: text.length, end: text.length + node.value.length });
        text += node.value;
      } else node.children?.forEach(collect);
    };
    collect(tree);
    const ranges = items.flatMap((item) => {
      const anchor = parseLessonAnchor(item.source_anchor);
      const range = anchor && resolveAnchor(text, anchor);
      return range && anchor && ['highlight', 'note'].includes(item.kind) ? [{ ...range, item, anchor }] : [];
    });
    const notes = ranges.filter((range) => range.item.kind === 'note').sort((a, b) => a.start - b.start);
    for (const { node, start, end } of leaves) {
      const cuts = Array.from(new Set([start, end, ...ranges.flatMap((range) => [Math.max(start, range.start), Math.min(end, range.end)]).filter((value) => value > start && value < end)])).sort((a, b) => a - b);
      const original = node.value!;
      node.type = 'element'; node.tagName = 'span'; node.properties = {}; delete node.value;
      node.children = cuts.slice(0, -1).map((from, index) => {
        const to = cuts[index + 1];
        const active = ranges.filter((range) => range.start < to && range.end > from);
        const note = active.find((range) => range.item.kind === 'note');
        const ordered = note ? [note, ...active.filter((range) => range !== note)] : active;
        return { type: 'element', tagName: 'span', properties: {
          'data-lesson-text-start': String(from),
          ...(active.length ? {
            'data-annotation-ids': ordered.map((range) => range.item.item_id).join(' '),
            'data-annotation-color': (note ?? active[0]).anchor.color,
            className: ['lesson-text-mark', ...(note ? ['has-note'] : [])],
            role: 'button', tabIndex: 0, 'aria-label': note ? '查看批注' : '查看标记',
            ...(note && note.end === to ? { 'data-note-number': String(notes.indexOf(note) + 1) } : {}),
          } : {}),
        }, children: [{ type: 'text', value: original.slice(from - start, to - start) }] };
      });
    }
  };
}

export function captureLessonAnchor(root: Element, range: Range): LessonAnchor | null {
  if (Array.from(root.querySelectorAll('pre, code, .katex, svg, button, img')).some((node) => range.intersectsNode(node))) return null;
  const spans = Array.from(root.querySelectorAll<HTMLElement>('[data-lesson-text-start]'));
  let start: number | undefined;
  let end: number | undefined;
  let fullText = '';
  for (const span of spans) {
    const text = span.firstChild;
    if (!text || text.nodeType !== Node.TEXT_NODE) continue;
    const length = text.textContent?.length ?? 0;
    const offset = Number(span.dataset.lessonTextStart);
    fullText += text.textContent;
    if (!range.intersectsNode(text)) continue;
    const from = range.startContainer === text ? range.startOffset : 0;
    const to = range.endContainer === text ? range.endOffset : length;
    if (range.comparePoint(text, length) < 0 || range.comparePoint(text, 0) > 0 || to <= from) continue;
    start ??= offset + from;
    end = offset + to;
  }
  if (start === undefined || end === undefined || end <= start) return null;
  const exact = fullText.slice(start, end);
  if (!exact.trim() || exact.length > 20_000) return null;
  return { version: 1, source: 'lesson', start, end, exact, prefix: fullText.slice(Math.max(0, start - 32), start), suffix: fullText.slice(end, end + 32), color: 'olive' };
}
