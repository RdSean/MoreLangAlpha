import { useId, useMemo, useState } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import {
  BookOpen,
  Check,
  ChevronDown,
  ChevronRight,
  ListTree,
  Search,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type {
  BookStructure,
  BookStructureNode,
  KnowledgePointProjection,
} from '../types';

interface BookNavigatorProps {
  structure: BookStructure;
  selectedKnowledgePointSkillId?: string;
  selectedNodeId?: string;
  onSelectKnowledgePoint?: (skillKnowledgePointId: string) => void;
  onSelectNode?: (nodeId: string) => void;
  batchMode?: boolean;
  onBatchModeChange?: (enabled: boolean) => void;
  batchDisabled?: boolean;
  selectedKnowledgePointIds?: ReadonlySet<string>;
  onBatchSelectionChange?: (knowledgePointIds: Set<string>) => void;
}

function flattenNodes(nodes: readonly BookStructureNode[]) {
  const result = new Map<string, BookStructureNode>();
  const visit = (node: BookStructureNode) => {
    result.set(node.id, node);
    for (const child of node.children ?? []) visit(child);
  };
  for (const node of nodes) visit(node);
  return result;
}

function filterNode(node: BookStructureNode, query: string): BookStructureNode | null {
  const children = (node.children ?? [])
    .map((child) => filterNode(child, query))
    .filter((child): child is BookStructureNode => child !== null);
  if (!node.title.toLocaleLowerCase().includes(query) && children.length === 0) return null;
  return { ...node, children };
}

function SourceNode({
  node,
  depth,
  expanded,
  selectedNodeId,
  onToggle,
  onSelect,
}: {
  node: BookStructureNode;
  depth: number;
  expanded: ReadonlySet<string>;
  selectedNodeId?: string;
  onToggle: (nodeId: string) => void;
  onSelect?: (nodeId: string) => void;
}) {
  const children = node.children ?? [];
  const isExpanded = expanded.has(node.id);
  return (
    <li>
      <div className="flex min-h-11 items-center gap-1" style={{ paddingLeft: `${depth * 12}px` }}>
        {children.length > 0 ? (
          <button
            type="button"
            className="inline-flex size-10 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-[var(--color-bg-hover)]"
            onClick={() => onToggle(node.id)}
            aria-label={`${isExpanded ? '收起' : '展开'} ${node.title}`}
            aria-expanded={isExpanded}
          >
            {isExpanded
              ? <ChevronDown className="size-4" aria-hidden="true" />
              : <ChevronRight className="size-4" aria-hidden="true" />}
          </button>
        ) : <span className="w-10 shrink-0" />}
        <button
          type="button"
          className={cn(
            'min-h-11 min-w-0 flex-1 rounded-md px-2 py-2 text-left text-sm hover:bg-[var(--color-bg-hover)]',
            selectedNodeId === node.id && 'bg-[var(--color-bg-hover)] font-medium text-foreground',
          )}
          onClick={() => onSelect?.(node.id)}
          aria-label={`打开 ${node.title}`}
        >
          <span className="block break-words">{node.title}</span>
        </button>
      </div>
      {children.length > 0 && isExpanded && (
        <ul>
          {children.map((child) => (
            <SourceNode
              key={child.id}
              node={child}
              depth={depth + 1}
              expanded={expanded}
              selectedNodeId={selectedNodeId}
              onToggle={onToggle}
              onSelect={onSelect}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

export function BookNavigator({
  structure,
  selectedKnowledgePointSkillId,
  selectedNodeId,
  onSelectKnowledgePoint,
  onSelectNode,
  batchMode = false,
  onBatchModeChange,
  batchDisabled = false,
  selectedKnowledgePointIds = new Set(),
  onBatchSelectionChange,
}: BookNavigatorProps) {
  const { t } = useTranslation();
  const reducedMotion = useReducedMotion();
  const tabId = useId();
  const [view, setView] = useState<'knowledge' | 'source'>('knowledge');
  const [query, setQuery] = useState('');
  const [expanded, setExpanded] = useState<Set<string>>(
    () => new Set(structure.structure.nodes.map((node) => node.id)),
  );
  const nodeMap = useMemo(
    () => flattenNodes(structure.structure.nodes),
    [structure.structure.nodes],
  );
  const normalizedQuery = query.trim().toLocaleLowerCase();
  const filteredKnowledgePoints = structure.knowledge_points.filter(
    (entry) => !normalizedQuery || entry.title.toLocaleLowerCase().includes(normalizedQuery),
  );
  const groups = useMemo(() => {
    const grouped = new Map<string | null, KnowledgePointProjection[]>();
    for (const entry of filteredKnowledgePoints) {
      const key = entry.unit_skill_node_id;
      grouped.set(key, [...(grouped.get(key) ?? []), entry]);
    }
    return [...grouped.entries()];
  }, [filteredKnowledgePoints]);
  const sourceNodes = normalizedQuery
    ? structure.structure.nodes
      .map((node) => filterNode(node, normalizedQuery))
      .filter((node): node is BookStructureNode => node !== null)
    : structure.structure.nodes;

  const toggleExpanded = (nodeId: string) => {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(nodeId)) next.delete(nodeId);
      else next.add(nodeId);
      return next;
    });
  };

  const toggleKnowledgePoint = (knowledgePointId: string) => {
    const next = new Set(selectedKnowledgePointIds);
    if (next.has(knowledgePointId)) next.delete(knowledgePointId);
    else next.add(knowledgePointId);
    onBatchSelectionChange?.(next);
  };

  const toggleGroup = (entries: readonly KnowledgePointProjection[]) => {
    const next = new Set(selectedKnowledgePointIds);
    const everySelected = entries.every((entry) => next.has(entry.knowledge_point_id));
    for (const entry of entries) {
      if (everySelected) next.delete(entry.knowledge_point_id);
      else next.add(entry.knowledge_point_id);
    }
    onBatchSelectionChange?.(next);
  };

  return (
    <nav className="flex h-full min-h-0 flex-col bg-background" aria-label="教材导航">
      <div className="border-b p-3">
        <div className="book-navigator-tabs" role="tablist" aria-label={t('bookProcessing.navigation')} onKeyDown={(event) => {
          if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
          event.preventDefault();
          const target = event.key === 'Home' ? 'knowledge' : event.key === 'End' ? 'source' : view === 'knowledge' ? 'source' : 'knowledge';
          setView(target);
          event.currentTarget.querySelector<HTMLButtonElement>(`[data-view="${target}"]`)?.focus();
        }}>
          {(['knowledge', 'source'] as const).map((tab) => (
            <button key={tab} type="button" role="tab" id={`${tabId}-${tab}`} data-view={tab} aria-controls={`${tabId}-content`} tabIndex={view === tab ? 0 : -1} aria-selected={view === tab} className={cn('book-navigator-tab', view === tab && 'font-medium text-foreground')} onClick={() => setView(tab)}>
              {t(tab === 'knowledge' ? 'bookProcessing.knowledge' : 'bookProcessing.sourceContents')}
              {view === tab && <motion.span className="book-navigator-indicator" layoutId={`${tabId}-indicator`} transition={{ duration: reducedMotion ? 0 : 0.18 }} />}
            </button>
          ))}
        </div>
        <label className="relative mt-3 block">
          <Search className="pointer-events-none absolute left-3 top-3 size-4 text-muted-foreground" aria-hidden="true" />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="h-10 w-full rounded-md border bg-background pl-9 pr-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
            placeholder="搜索标题"
            aria-label="搜索教材内容"
          />
        </label>
      </div>

      <motion.div key={view} id={`${tabId}-content`} role="tabpanel" aria-labelledby={`${tabId}-${view}`} initial={{ opacity: reducedMotion ? 1 : 0 }} animate={{ opacity: 1 }} transition={{ duration: reducedMotion ? 0 : 0.16 }} className="min-h-0 flex-1 overflow-y-auto p-2">
        {view === 'knowledge' ? (
          groups.length > 0 ? groups.map(([unitId, entries]) => {
            const title = unitId ? nodeMap.get(unitId)?.title ?? unitId : t('bookProcessing.ungrouped');
            const count = structure.knowledge_points.filter((point) => point.unit_skill_node_id === unitId).length;
            return (
              <section key={unitId ?? 'ungrouped'} data-testid={`kp-group-${unitId ?? 'ungrouped'}`} className="mb-3">
                <div className="flex min-h-10 items-center gap-2 px-2">
                  {batchMode && (
                    <input
                      type="checkbox"
                      checked={entries.every((entry) => selectedKnowledgePointIds.has(entry.knowledge_point_id))}
                      onChange={() => toggleGroup(entries)}
                      aria-label={`选择 ${title} 全部知识点`}
                      className="size-4"
                    />
                  )}
                  <ListTree className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                  <h3 className="min-w-0 break-words text-xs font-semibold text-muted-foreground">{title}（{count}）</h3>
                </div>
                <ul>
                  {entries.map((entry) => (
                    <li key={entry.knowledge_point_id} className="flex min-h-11 items-center gap-2">
                      {batchMode && (
                        <input
                          type="checkbox"
                          checked={selectedKnowledgePointIds.has(entry.knowledge_point_id)}
                          onChange={() => toggleKnowledgePoint(entry.knowledge_point_id)}
                          aria-label={`选择 ${entry.title}`}
                          className="ml-2 size-4 shrink-0"
                        />
                      )}
                      <button
                        type="button"
                        className={cn(
                          'flex min-h-11 min-w-0 flex-1 items-center gap-2 rounded-md px-2 py-2 text-left text-sm hover:bg-[var(--color-bg-hover)]',
                          selectedKnowledgePointSkillId === entry.skill_kp_id && 'bg-[var(--color-bg-hover)] font-medium',
                        )}
                        onClick={() => onSelectKnowledgePoint?.(entry.skill_kp_id)}
                        aria-label={`${entry.title}${entry.material_available ? '，已生成讲义' : ''}`}
                      >
                        <span className="min-w-0 flex-1 break-words">{entry.title}</span>
                        {entry.material_available && <Check className="size-4 shrink-0 text-emerald-600" aria-hidden="true" />}
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            );
          }) : <p className="px-3 py-8 text-center text-sm text-muted-foreground">没有匹配的知识点</p>
        ) : (
          sourceNodes.length > 0 ? (
            <ul>
              {sourceNodes.map((node) => (
                <SourceNode
                  key={node.id}
                  node={node}
                  depth={0}
                  expanded={normalizedQuery ? new Set(nodeMap.keys()) : expanded}
                  selectedNodeId={selectedNodeId}
                  onToggle={toggleExpanded}
                  onSelect={onSelectNode}
                />
              ))}
            </ul>
          ) : <p className="px-3 py-8 text-center text-sm text-muted-foreground">没有匹配的目录节点</p>
        )}
      </motion.div>

      {view === 'knowledge' && structure.knowledge_points.length > 0 && onBatchModeChange && (
        <div className="border-t p-3">
          <button
            type="button"
            className="flex min-h-11 w-full items-center justify-center gap-2 rounded-md border text-sm font-medium hover:bg-[var(--color-bg-hover)]"
            onClick={() => onBatchModeChange?.(!batchMode)}
            disabled={batchDisabled}
          >
            <BookOpen className="size-4" aria-hidden="true" />
            {batchMode ? '退出批量选择' : '批量选择'}
          </button>
        </div>
      )}
    </nav>
  );
}
