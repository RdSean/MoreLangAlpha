import Markdown from '@/pages/ChatAgent/components/Markdown';
import './EducationMarkdown.css';
import { annotationPlugin, type AnnotationItem } from './lessonAnnotationAnchors';
import type { ComponentProps } from 'react';

interface PositionedNode {
  type?: string;
  tagName?: string;
  position?: {
    start?: { line?: number };
    end?: { line?: number };
  };
  properties?: Record<string, unknown>;
  children?: PositionedNode[];
}

const SOURCE_BLOCK_TAGS = new Set([
  'blockquote',
  'h1',
  'h2',
  'h3',
  'h4',
  'h5',
  'h6',
  'hr',
  'li',
  'p',
  'pre',
  'table',
]);

function hiddenFrontMatterLines(content: string): number {
  if (!content.startsWith('---\n') && !content.startsWith('---\r\n')) return 0;
  const end = content.indexOf('\n---', 3);
  if (end === -1) return 0;
  const removed = content.slice(0, end + 4);
  return (removed.match(/\n/g) ?? []).length + 1;
}

function sourceLinePlugin({
  lineOffset,
}: {
  lineOffset: number;
}) {
  return (tree: PositionedNode) => {
    const visit = (node: PositionedNode, parentTag?: string) => {
      const start = node.position?.start?.line;
      const end = node.position?.end?.line;
      const isBlock = node.type === 'element'
        && Boolean(node.tagName && SOURCE_BLOCK_TAGS.has(node.tagName))
        && !(node.tagName === 'p' && parentTag === 'li');
      if (isBlock && start && end) {
        const absoluteStart = start + lineOffset;
        const absoluteEnd = end + lineOffset;
        node.properties ??= {};
        node.properties['data-source-start-line'] = String(absoluteStart);
        node.properties['data-source-end-line'] = String(absoluteEnd);
      }
      for (const child of node.children ?? []) visit(child, node.tagName);
    };
    visit(tree);
  };
}

export default function EducationMarkdown({
  content,
  variant = 'lesson',
  className = '',
  onOpenFile,
  sourceLineOffset,
  annotationOptions,
}: {
  content: string;
  variant?: 'lesson' | 'summary' | 'compact';
  className?: string;
  onOpenFile?: (path: string) => void;
  sourceLineOffset?: number;
  annotationOptions?: { items: readonly AnnotationItem[]; onOpen?: (itemId: string) => void };
}) {
  const lineOffset = sourceLineOffset === undefined
    ? undefined
    : sourceLineOffset + hiddenFrontMatterLines(content);
  const plugins: NonNullable<ComponentProps<typeof Markdown>['rehypePlugins']> = [];
  if (lineOffset !== undefined) plugins.push([sourceLinePlugin, { lineOffset }]);
  if (annotationOptions) plugins.push([annotationPlugin, { items: annotationOptions.items }]);
  return (
    <div data-education-markdown={variant}
      onClick={annotationOptions ? (event) => {
        if (window.getSelection()?.toString()) return;
        const mark = (event.target as Element).closest('[data-annotation-ids]');
        if (mark) { event.preventDefault(); annotationOptions.onOpen?.(mark.getAttribute('data-annotation-ids')!.split(' ')[0]); }
      } : undefined}
      onKeyDown={annotationOptions ? (event) => {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        const mark = (event.target as Element).closest('[data-annotation-ids]');
        if (mark) { event.preventDefault(); annotationOptions.onOpen?.(mark.getAttribute('data-annotation-ids')!.split(' ')[0]); }
      } : undefined}>
      <Markdown
        variant="panel"
        content={content}
        className={className}
        onOpenFile={onOpenFile}
        rehypePlugins={plugins}
      />
    </div>
  );
}
