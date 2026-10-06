import { useEffect, useId, useMemo, useRef, useState, type CSSProperties } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { useTranslation } from 'react-i18next';
import {
  BookOpen,
  Check,
  ChevronDown,
  ChevronRight,
  PanelLeftClose,
  ChevronsDownUp,
  ChevronsUpDown,
  Search,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type {
  BookStructure,
  BookStructureNode,
  KnowledgePointProjection,
} from '../types';
import './BookNavigator.css';

interface BookNavigatorProps {
  structure: BookStructure;
  selectedKnowledgePointSkillId?: string;
  selectedNodeId?: string;
  onSelectKnowledgePoint?: (skillKnowledgePointId: string) => void;
  onSelectNode?: (nodeId: string) => void;
  onSelectOriginalNode?: (nodeId: string) => void;
  activeView?: 'knowledge' | 'source' | 'text';
  onNavigationChange?: (view: 'knowledge' | 'source' | 'text') => void;
  onCollapse?: () => void;
  batchMode?: boolean;
  onBatchModeChange?: (enabled: boolean) => void;
  batchDisabled?: boolean;
  selectedKnowledgePointIds?: ReadonlySet<string>;
  onBatchSelectionChange?: (knowledgePointIds: Set<string>) => void;
  learningStates?: Readonly<Record<string, 'viewed' | 'asked'>>;
}

function TreeTitle({ children }: { children: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const [distance, setDistance] = useState(0);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const measure = () => setDistance(Math.max(0, (element.firstElementChild?.scrollWidth ?? 0) - element.clientWidth));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    void document.fonts?.ready.then(measure);
    return () => observer.disconnect();
  }, [children]);
  return <span ref={ref} className="book-tree-title" title={children} style={{ '--title-shift': `${-distance}px`, '--title-duration': `${Math.max(1, distance / 45)}s` } as CSSProperties}><span>{children}</span></span>;
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
  index,
  expanded,
  selectedNodeId,
  onToggle,
  onSelect,
}: {
  node: BookStructureNode;
  depth: number;
  index: number;
  expanded: ReadonlySet<string>;
  selectedNodeId?: string;
  onToggle: (nodeId: string) => void;
  onSelect?: (nodeId: string) => void;
}) {
  const children = node.children ?? [];
  const isExpanded = expanded.has(node.id);
  const isGroup = depth === 0 && children.length > 0;
  const toggle = children.length > 0 ? (
    <button
      type="button"
      className="book-tree-toggle"
      onClick={() => onToggle(node.id)}
      aria-label={`${isExpanded ? '收起' : '展开'} ${node.title}`}
      aria-expanded={isExpanded}
    >
      {isExpanded
        ? <ChevronDown className="size-3" aria-hidden="true" />
        : <ChevronRight className="size-3" aria-hidden="true" />}
    </button>
  ) : null;
  return (
    <li>
      <div className={cn('book-tree-row', isGroup && 'book-tree-unit')} style={{ paddingLeft: `${Math.max(0, depth - 1) * 12}px` }}>
        {isGroup && toggle}
        <button
          type="button"
          className={cn(
            'book-tree-item',
            isGroup && 'book-tree-group',
            selectedNodeId === node.id && 'bg-[var(--color-bg-hover)] font-medium text-foreground',
          )}
          onClick={() => onSelect?.(node.id)}
          aria-label={`打开 ${node.title}`}
        >
          {!isGroup && <>
            <span className="book-tree-marker-space" aria-hidden="true" />
            <span className="book-tree-number" aria-hidden="true">{index + 1}</span>
          </>}
          <TreeTitle>{node.title}</TreeTitle>
        </button>
        {!isGroup && toggle}
      </div>
      {children.length > 0 && isExpanded && (
        <ul>
          {children.map((child, childIndex) => (
            <SourceNode
              key={child.id}
              node={child}
              depth={depth + 1}
              index={childIndex}
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
  onSelectOriginalNode,
  activeView,
  onNavigationChange,
  onCollapse,
  batchMode = false,
  onBatchModeChange,
  batchDisabled = false,
  selectedKnowledgePointIds = new Set(),
  onBatchSelectionChange,
  learningStates = {},
}: BookNavigatorProps) {
  const { t } = useTranslation();
  const reducedMotion = useReducedMotion();
  const tabId = useId();
  const [localView, setLocalView] = useState<'knowledge' | 'source' | 'text'>('knowledge');
  const view = activeView ?? localView;
  const setView = (next: 'knowledge' | 'source' | 'text') => { setLocalView(next); onNavigationChange?.(next); };
  const tabs: readonly ('knowledge' | 'source' | 'text')[] = onSelectOriginalNode ? ['knowledge', 'source', 'text'] : ['knowledge', 'source'];
  const [query, setQuery] = useState('');
  const [expanded, setExpanded] = useState<Set<string>>(
    () => new Set([...structure.structure.nodes.map((node) => node.id), ...structure.knowledge_points.map((point) => point.unit_skill_node_id ?? 'ungrouped')]),
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
  const expandableIds = view === 'knowledge' ? groups.map(([id]) => id ?? 'ungrouped') : [...nodeMap.values()].filter((node) => node.children?.length).map((node) => node.id);
  const allExpanded = expandableIds.length > 0 && expandableIds.every((id) => expanded.has(id));

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
    <nav className="book-navigator" aria-label="教材导航">
      <div className="book-navigator-footer">
        <div className="book-navigator-tabs" style={{ gridTemplateColumns: `repeat(${tabs.length}, minmax(0, 1fr))` }} role="tablist" aria-label={t('bookProcessing.navigation')} onKeyDown={(event) => {
          if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
          event.preventDefault();
          const target = event.key === 'Home' ? tabs[0] : event.key === 'End' ? tabs.at(-1)! : tabs[(tabs.indexOf(view) + (event.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
          setView(target);
          event.currentTarget.querySelector<HTMLButtonElement>(`[data-view="${target}"]`)?.focus();
        }}>
          {tabs.map((tab) => (
            <button key={tab} type="button" role="tab" id={`${tabId}-${tab}`} data-view={tab} aria-controls={`${tabId}-content`} tabIndex={view === tab ? 0 : -1} aria-selected={view === tab} className={cn('book-navigator-tab', view === tab && 'font-medium text-foreground')} onClick={() => setView(tab)}>
              {t(tab === 'knowledge' ? 'bookProcessing.knowledge' : tab === 'source' ? 'bookProcessing.sourceContents' : 'bookProcessing.textContents')}
              {view === tab && <motion.span className="book-navigator-indicator" layoutId={`${tabId}-indicator`} transition={{ duration: reducedMotion ? 0 : 0.18 }} />}
            </button>
          ))}
        </div>
      </div>
      <div className="book-navigator-tools">
        <label className="relative min-w-0 flex-1">
          <Search className="pointer-events-none absolute left-2 top-2 size-3.5 text-muted-foreground" aria-hidden="true" />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="h-8 w-full rounded-md border bg-background pl-7 pr-2 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring"
            placeholder="搜索标题"
            aria-label="搜索教材内容"
          />
        </label>
        <button type="button" className="book-tree-toggle" title={allExpanded ? '收起全部章节' : '展开全部章节'} aria-label={allExpanded ? '收起全部章节' : '展开全部章节'} onClick={() => setExpanded(allExpanded ? new Set() : new Set(expandableIds))}>
          {allExpanded ? <ChevronsDownUp className="size-4" /> : <ChevronsUpDown className="size-4" />}
        </button>
        {onCollapse && <button type="button" className="book-tree-toggle" title="收起教材目录" aria-label="收起教材目录" onClick={onCollapse}><PanelLeftClose className="size-4" aria-hidden="true" /></button>}
      </div>

      <motion.div key={view} id={`${tabId}-content`} role="tabpanel" aria-labelledby={`${tabId}-${view}`} initial={{ opacity: reducedMotion ? 1 : 0 }} animate={{ opacity: 1 }} transition={{ duration: reducedMotion ? 0 : 0.16 }} className="book-navigator-scroll">
        {view === 'knowledge' ? (
          groups.length > 0 ? groups.map(([unitId, entries]) => {
            const title = unitId ? nodeMap.get(unitId)?.title ?? unitId : t('bookProcessing.ungrouped');
            const count = structure.knowledge_points.filter((point) => point.unit_skill_node_id === unitId).length;
            return (
              <section key={unitId ?? 'ungrouped'} data-testid={`kp-group-${unitId ?? 'ungrouped'}`} className="mb-1">
                <div className="book-tree-row book-tree-unit">
                  {batchMode && (
                    <input
                      type="checkbox"
                      checked={entries.every((entry) => selectedKnowledgePointIds.has(entry.knowledge_point_id))}
                      onChange={() => toggleGroup(entries)}
                      aria-label={`选择 ${title} 全部知识点`}
                      className="size-4"
                    />
                  )}
                  <button type="button" className="book-tree-toggle" aria-label={`${expanded.has(unitId ?? 'ungrouped') ? '收起' : '展开'} ${title}`} aria-expanded={Boolean(normalizedQuery) || expanded.has(unitId ?? 'ungrouped')} onClick={() => toggleExpanded(unitId ?? 'ungrouped')}>
                    {normalizedQuery || expanded.has(unitId ?? 'ungrouped') ? <ChevronDown className="size-3" /> : <ChevronRight className="size-3" />}
                  </button>
                  <h3 className="book-tree-group min-w-0 flex-1"><TreeTitle>{`${title}（${count}）`}</TreeTitle></h3>
                </div>
                {(normalizedQuery || expanded.has(unitId ?? 'ungrouped')) && <ul>
                  {entries.map((entry, index) => (
                    <li key={entry.knowledge_point_id} className="book-tree-row">
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
                          'book-tree-item book-knowledge-item',
                          selectedKnowledgePointSkillId === entry.skill_kp_id && 'bg-[var(--color-bg-hover)] font-medium',
                        )}
                        onClick={() => onSelectKnowledgePoint?.(entry.skill_kp_id)}
                        aria-label={`${entry.title}${entry.material_available ? '，已生成讲义' : ''}`}
                      >
                        <span className="book-learning-stick" data-state={entry.material_available ? learningStates[entry.knowledge_point_id] ?? 'unread' : 'unavailable'} title={entry.material_available ? learningStates[entry.knowledge_point_id] === 'asked' ? '已阅读并提问' : learningStates[entry.knowledge_point_id] === 'viewed' ? '已阅读讲义' : '讲义已就绪，尚未阅读' : '尚未生成讲义'} />
                        <span className="book-tree-number" aria-hidden="true">{index + 1}</span>
                        <TreeTitle>{entry.title}</TreeTitle>
                        {entry.material_available && <Check className="size-3 shrink-0 text-muted-foreground" aria-hidden="true" />}
                      </button>
                    </li>
                  ))}
                </ul>}
              </section>
            );
          }) : <p className="px-3 py-8 text-center text-sm text-muted-foreground">没有匹配的知识点</p>
        ) : (
          sourceNodes.length > 0 ? (
            <ul>
              {sourceNodes.map((node, index) => (
                <SourceNode
                  key={node.id}
                  node={node}
                  depth={0}
                  index={index}
                  expanded={normalizedQuery ? new Set(nodeMap.keys()) : expanded}
                  selectedNodeId={selectedNodeId}
                  onToggle={toggleExpanded}
                  onSelect={view === 'source' ? onSelectOriginalNode ?? onSelectNode : onSelectNode}
                />
              ))}
            </ul>
          ) : <p className="px-3 py-8 text-center text-sm text-muted-foreground">没有匹配的目录节点</p>
        )}
      </motion.div>

      {view === 'knowledge' && structure.knowledge_points.length > 0 && onBatchModeChange && (
        <div className="book-navigator-batch">
          <button
            type="button"
            className="flex h-8 w-full items-center justify-center gap-2 rounded-md border text-xs font-medium hover:bg-[var(--color-bg-hover)]"
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
