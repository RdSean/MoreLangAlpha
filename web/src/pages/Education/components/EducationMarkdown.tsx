import Markdown from '@/pages/ChatAgent/components/Markdown';

interface SourceLineRange {
  start: number;
  end: number;
}

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
  highlight,
}: {
  lineOffset: number;
  highlight?: SourceLineRange;
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
        if (highlight && absoluteStart <= highlight.end && absoluteEnd >= highlight.start) {
          node.properties['data-source-highlight'] = 'true';
        }
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
  highlightSourceRange,
}: {
  content: string;
  variant?: 'lesson' | 'summary' | 'compact';
  className?: string;
  onOpenFile?: (path: string) => void;
  sourceLineOffset?: number;
  highlightSourceRange?: SourceLineRange;
}) {
  const lineOffset = sourceLineOffset === undefined
    ? undefined
    : sourceLineOffset + hiddenFrontMatterLines(content);
  return (
    <div data-education-markdown={variant}>
      <Markdown
        variant="panel"
        content={content}
        className={className}
        onOpenFile={onOpenFile}
        rehypePlugins={lineOffset === undefined
          ? []
          : [[sourceLinePlugin, { lineOffset, highlight: highlightSourceRange }]]}
      />
    </div>
  );
}
