import { useEffect, useMemo, useState } from 'react';
import {
  ArrowLeft,
  BookOpen,
  Check,
  GitMerge,
  Loader2,
  Pencil,
  Scissors,
  Trash2,
  X,
} from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { useToast } from '@/components/ui/use-toast';
import {
  useKnowledgePointCandidateMutations,
  useKnowledgePointCandidateReview,
  useLatestTextbookStructure,
} from './queries';
import type {
  KnowledgePointCandidate,
  KnowledgePointCandidateNode,
  KnowledgePointCandidateStatus,
} from './types';

const statusLabels: Record<KnowledgePointCandidateStatus, string> = {
  pending: '待确认',
  accepted: '已接受',
  rejected: '已拒绝',
  merged: '已合并',
  split: '已拆分',
};

const statusClasses: Record<KnowledgePointCandidateStatus, string> = {
  pending: 'border-[var(--color-border-muted)] text-muted-foreground',
  accepted: 'border-[var(--color-success)] text-[var(--color-success)]',
  rejected: 'border-[var(--color-loss)] text-[var(--color-loss)]',
  merged: 'border-[var(--color-border-muted)] text-muted-foreground',
  split: 'border-[var(--color-border-muted)] text-muted-foreground',
};

const MAX_CANDIDATE_SELECTION = 100;
const MAX_SPLIT_ITEMS = 100;

function messageOf(error: unknown, fallback: string) {
  return error instanceof Error && error.message ? error.message : fallback;
}

function CandidateNode({
  node,
  depth,
  childrenByParent,
  selectedIds,
  selectionLimitReached,
  onToggle,
  onEdit,
  onSplit,
  lessonBasePath,
}: {
  node: KnowledgePointCandidateNode;
  depth: number;
  childrenByParent: Map<string | null, KnowledgePointCandidateNode[]>;
  selectedIds: Set<string>;
  selectionLimitReached: boolean;
  onToggle: (candidateId: string) => void;
  onEdit: (candidate: KnowledgePointCandidate) => void;
  onSplit: (candidate: KnowledgePointCandidate) => void;
  lessonBasePath: string;
}) {
  const children = childrenByParent.get(node.node_id) ?? [];
  return (
    <section
      className="border-l pl-3 sm:pl-4"
      style={{
        borderColor: depth === 0
          ? 'var(--color-accent-primary)'
          : 'var(--color-border-muted)',
        marginLeft: depth > 0 ? `${Math.min(depth, 4) * 10}px` : undefined,
      }}
      aria-label={`内容节点 ${node.title}`}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2 py-3">
        <div className="min-w-0">
          <p className="font-mono text-[11px] uppercase tracking-wide text-muted-foreground">
            {node.node_type} · {node.position}
          </p>
          <h2 className="title-font mt-1 text-base font-semibold">{node.title}</h2>
          {node.summary && (
            <p className="mt-1 max-w-3xl text-xs leading-5 text-muted-foreground">
              {node.summary}
            </p>
          )}
        </div>
        <span className="font-mono text-[11px] text-muted-foreground">
          {node.candidates.length} 个候选
        </span>
      </div>

      {node.candidates.length === 0 ? (
        <p className="border-t py-3 text-xs text-muted-foreground" style={{ borderColor: 'var(--color-border-muted)' }}>
          此节点没有知识点候选。
        </p>
      ) : (
        <div className="border-y" style={{ borderColor: 'var(--color-border-muted)' }}>
          {node.candidates.map((candidate) => (
            <div
              key={candidate.knowledge_point_id}
              className="flex min-w-0 items-start gap-3 border-b px-3 py-3 last:border-b-0"
              style={{ borderColor: 'var(--color-border-muted)' }}
            >
              <input
                type="checkbox"
                className="mt-1 size-4 shrink-0 accent-[var(--color-accent-primary)]"
                aria-label={`选择知识点 ${candidate.title}`}
                checked={selectedIds.has(candidate.knowledge_point_id)}
                disabled={
                  candidate.candidate_status !== 'pending'
                  || (
                    selectionLimitReached
                    && !selectedIds.has(candidate.knowledge_point_id)
                  )
                }
                onChange={() => onToggle(candidate.knowledge_point_id)}
              />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="break-words text-sm font-medium">{candidate.title}</p>
                  <span className="border px-1.5 py-0.5 font-mono text-[10px]" style={{ borderColor: 'var(--color-border-muted)' }}>
                    {candidate.point_type}
                  </span>
                  <span className={`border px-1.5 py-0.5 text-[10px] ${statusClasses[candidate.candidate_status]}`}>
                    {statusLabels[candidate.candidate_status]}
                  </span>
                </div>
                {candidate.summary && (
                  <p className="mt-1 break-words text-xs leading-5 text-muted-foreground">
                    {candidate.summary}
                  </p>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-1">
                {candidate.candidate_status === 'accepted' && (
                  <Link
                    to={`${lessonBasePath}/${candidate.knowledge_point_id}`}
                    aria-label={`制作课程 ${candidate.title}`}
                    title="制作课程"
                    className="inline-flex h-8 shrink-0 items-center justify-center gap-1.5 rounded-md border border-input bg-background px-2 text-xs font-medium transition-colors hover:bg-[var(--color-bg-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                  >
                    <BookOpen className="size-3.5" aria-hidden="true" />
                    制作课程
                  </Link>
                )}
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  className="size-8"
                  aria-label={`编辑 ${candidate.title}`}
                  title="编辑候选"
                  onClick={() => onEdit(candidate)}
                >
                  <Pencil className="size-3.5" />
                </Button>
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  className="size-8"
                  aria-label={`拆分 ${candidate.title}`}
                  title="拆分候选"
                  disabled={candidate.candidate_status !== 'pending'}
                  onClick={() => onSplit(candidate)}
                >
                  <Scissors className="size-3.5" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {children.length > 0 && (
        <div className="mt-3 grid gap-3">
          {children.map((child) => (
            <CandidateNode
              key={child.node_id}
              node={child}
              depth={depth + 1}
              childrenByParent={childrenByParent}
              selectedIds={selectedIds}
              selectionLimitReached={selectionLimitReached}
              onToggle={onToggle}
              onEdit={onEdit}
              onSplit={onSplit}
              lessonBasePath={lessonBasePath}
            />
          ))}
        </div>
      )}
    </section>
  );
}

export default function KnowledgePointReviewPage() {
  const { textbookId, versionId } = useParams();
  const structure = useLatestTextbookStructure(versionId, true);
  const structureId = structure.data?.structure_id;
  const review = useKnowledgePointCandidateReview(structureId, Boolean(structureId));
  const mutations = useKnowledgePointCandidateMutations();
  const { toast } = useToast();
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [editing, setEditing] = useState<KnowledgePointCandidate | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [editSummary, setEditSummary] = useState('');
  const [editType, setEditType] = useState('');
  const [mergeOpen, setMergeOpen] = useState(false);
  const [mergeTargetId, setMergeTargetId] = useState('');
  const [mergeTitle, setMergeTitle] = useState('');
  const [mergeSummary, setMergeSummary] = useState('');
  const [mergeType, setMergeType] = useState('');
  const [mergeAccepted, setMergeAccepted] = useState(false);
  const [splitTarget, setSplitTarget] = useState<KnowledgePointCandidate | null>(null);
  const [splitItems, setSplitItems] = useState([
    { title: '', summary: '', point_type: 'concept' },
    { title: '', summary: '', point_type: 'concept' },
  ]);

  const allCandidates = useMemo(
    () => review.data?.nodes.flatMap((node) => node.candidates) ?? [],
    [review.data?.nodes],
  );
  const candidatesById = useMemo(
    () => new Map(allCandidates.map((candidate) => [candidate.knowledge_point_id, candidate])),
    [allCandidates],
  );
  const childrenByParent = useMemo(() => {
    const grouped = new Map<string | null, KnowledgePointCandidateNode[]>();
    for (const node of review.data?.nodes ?? []) {
      const parentId = node.parent_node_id ?? null;
      const siblings = grouped.get(parentId) ?? [];
      siblings.push(node);
      grouped.set(parentId, siblings);
    }
    return grouped;
  }, [review.data?.nodes]);
  const roots = childrenByParent.get(null) ?? [];
  const selectedCandidates = [...selectedIds]
    .map((id) => candidatesById.get(id))
    .filter(
      (candidate): candidate is KnowledgePointCandidate =>
        candidate?.candidate_status === 'pending',
    );
  const selectedNodeIds = new Set(
    selectedCandidates.map((candidate) => candidate.content_node_id),
  );
  const selectionLimitReached =
    selectedCandidates.length >= MAX_CANDIDATE_SELECTION;
  const counts = {
    pending: allCandidates.filter((candidate) => candidate.candidate_status === 'pending').length,
    accepted: allCandidates.filter((candidate) => candidate.candidate_status === 'accepted').length,
    rejected: allCandidates.filter((candidate) => candidate.candidate_status === 'rejected').length,
  };

  useEffect(() => {
    setSelectedIds((current) => {
      const visible = new Set(
        allCandidates
          .filter((candidate) => candidate.candidate_status === 'pending')
          .map((candidate) => candidate.knowledge_point_id),
      );
      const next = new Set([...current].filter((candidateId) => visible.has(candidateId)));
      return next.size === current.size ? current : next;
    });
  }, [allCandidates]);

  const toggleCandidate = (candidateId: string) => {
    const candidate = candidatesById.get(candidateId);
    if (candidate?.candidate_status !== 'pending') return;
    if (
      !selectedIds.has(candidateId)
      && selectedCandidates.length >= MAX_CANDIDATE_SELECTION
    ) {
      return;
    }
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(candidateId)) next.delete(candidateId);
      else next.add(candidateId);
      return next;
    });
  };

  const runSelectionAction = async (
    action: 'accept' | 'reject',
  ) => {
    if (
      selectedCandidates.length === 0
      || selectedCandidates.length > MAX_CANDIDATE_SELECTION
    ) return;
    try {
      await mutations[action].mutateAsync({
        candidateIds: selectedCandidates.map(
          (candidate) => candidate.knowledge_point_id,
        ),
      });
      setSelectedIds(new Set());
    } catch (error) {
      toast({
        variant: 'destructive',
        title: action === 'accept' ? '无法接受知识点' : '无法拒绝知识点',
        description: messageOf(error, '请刷新后重试。'),
      });
    }
  };

  const openEdit = (candidate: KnowledgePointCandidate) => {
    setEditing(candidate);
    setEditTitle(candidate.title);
    setEditSummary(candidate.summary);
    setEditType(candidate.point_type);
  };

  const saveEdit = async () => {
    if (!editing) return;
    try {
      await mutations.update.mutateAsync({
        candidateId: editing.knowledge_point_id,
        title: editTitle,
        summary: editSummary,
        point_type: editType,
      });
      setEditing(null);
    } catch (error) {
      toast({
        variant: 'destructive',
        title: '无法保存知识点',
        description: messageOf(error, '请检查内容后重试。'),
      });
    }
  };

  const openMerge = () => {
    if (
      selectedCandidates.length < 2
      || selectedCandidates.length > MAX_CANDIDATE_SELECTION
      || selectedNodeIds.size !== 1
    ) return;
    const first = selectedCandidates[0];
    setMergeTargetId(first.knowledge_point_id);
    setMergeTitle(first.title);
    setMergeSummary(first.summary);
    setMergeType(first.point_type);
    setMergeAccepted(false);
    setMergeOpen(true);
  };

  const submitMerge = async () => {
    if (selectedCandidates.length < 2 || !mergeTargetId) return;
    try {
      await mutations.merge.mutateAsync({
        source_ids: selectedCandidates.map((candidate) => candidate.knowledge_point_id),
        target_id: mergeTargetId,
        title: mergeTitle,
        summary: mergeSummary,
        point_type: mergeType,
        accept: mergeAccepted,
      });
      setMergeOpen(false);
      setSelectedIds(new Set());
    } catch (error) {
      toast({
        variant: 'destructive',
        title: '无法合并知识点',
        description: messageOf(error, '请确认所选知识点属于同一内容节点。'),
      });
    }
  };

  const openSplit = (candidate: KnowledgePointCandidate) => {
    setSplitTarget(candidate);
    setSplitItems([
      { title: `${candidate.title}（一）`, summary: '', point_type: candidate.point_type },
      { title: `${candidate.title}（二）`, summary: '', point_type: candidate.point_type },
    ]);
  };

  const submitSplit = async () => {
    if (!splitTarget) return;
    if (splitItems.length < 2 || splitItems.length > MAX_SPLIT_ITEMS) return;
    if (splitItems.some((item) => !item.title.trim() || !item.point_type.trim())) return;
    try {
      await mutations.split.mutateAsync({
        candidate_id: splitTarget.knowledge_point_id,
        items: splitItems,
      });
      setSplitTarget(null);
    } catch (error) {
      toast({
        variant: 'destructive',
        title: '无法拆分知识点',
        description: messageOf(error, '请检查拆分项后重试。'),
      });
    }
  };

  if (structure.isLoading) {
    return (
      <main className="h-full overflow-y-auto bg-canvas p-8 text-sm text-muted-foreground">
        正在读取教材结构…
      </main>
    );
  }

  if (!structure.data) {
    return (
      <main className="h-full overflow-y-auto bg-canvas p-8" data-testid="knowledge-point-review">
        <Link to={`/textbooks/${textbookId}`} className="inline-flex items-center gap-1.5 text-sm text-muted-foreground">
          <ArrowLeft className="size-4" />返回教材
        </Link>
        <p className="mt-8 text-sm text-muted-foreground">教材结构尚未生成。</p>
      </main>
    );
  }

  return (
    <main className="h-full min-h-0 overflow-y-auto bg-canvas" data-testid="knowledge-point-review">
      <div className="mx-auto max-w-6xl px-4 pb-28 pt-6 sm:px-6 sm:pb-24 lg:px-8">
        <Link
          to={`/textbooks/${textbookId}`}
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" />
          返回教材
        </Link>

        <header className="mt-5 flex flex-wrap items-end justify-between gap-4 border-b pb-5" style={{ borderColor: 'var(--color-border-muted)' }}>
          <div>
            <p className="font-mono text-[11px] uppercase tracking-wide text-muted-foreground">
              generated candidate review
            </p>
            <h1 className="title-font mt-1 text-2xl font-semibold">知识点候选确认</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
              生成结果保持待确认状态。接受、合并或拆分只影响明确选中的候选，未操作项不会被自动接受。
            </p>
          </div>
          <div className="flex flex-wrap gap-2 font-mono text-[11px] text-muted-foreground">
            <span>待确认 {counts.pending}</span>
            <span>已接受 {counts.accepted}</span>
            <span>已拒绝 {counts.rejected}</span>
          </div>
        </header>

        {review.isLoading ? (
          <div className="flex min-h-56 items-center justify-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />正在读取候选…
          </div>
        ) : review.isError ? (
          <p role="alert" className="mt-6 text-sm" style={{ color: 'var(--color-loss)' }}>
            暂时无法读取知识点候选，请稍后重试。
          </p>
        ) : roots.length === 0 ? (
          <div className="flex min-h-56 items-center justify-center text-sm text-muted-foreground">
            内容树中没有可审阅节点。
          </div>
        ) : (
          <div className="mt-4 grid gap-5">
            {roots.map((node) => (
              <CandidateNode
                key={node.node_id}
                node={node}
                depth={0}
                childrenByParent={childrenByParent}
                selectedIds={selectedIds}
                selectionLimitReached={selectionLimitReached}
                onToggle={toggleCandidate}
                onEdit={openEdit}
                onSplit={openSplit}
                lessonBasePath={`/textbooks/${textbookId}/versions/${versionId}/knowledge`}
              />
            ))}
          </div>
        )}
      </div>

      <div className="fixed inset-x-0 bottom-0 z-20 border-t bg-page/95 px-4 py-3 backdrop-blur sm:left-[var(--sidebar-width)]">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3">
          <span className="text-xs text-muted-foreground">
            {selectionLimitReached
              ? `最多选择 ${MAX_CANDIDATE_SELECTION} 个知识点；取消一个后可继续选择。`
              : selectedCandidates.length === 0
                ? '请选择待确认知识点'
                : `已选择 ${selectedCandidates.length} 项`}
          </span>
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={
                selectedCandidates.length === 0
                || selectedCandidates.length > MAX_CANDIDATE_SELECTION
                || mutations.reject.isPending
              }
              onClick={() => void runSelectionAction('reject')}
            >
              <X className="mr-1.5 size-3.5" />拒绝所选
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={
                selectedCandidates.length < 2
                || selectedCandidates.length > MAX_CANDIDATE_SELECTION
                || selectedNodeIds.size !== 1
                || mutations.merge.isPending
              }
              onClick={openMerge}
            >
              <GitMerge className="mr-1.5 size-3.5" />合并所选
            </Button>
            <Button
              type="button"
              size="sm"
              disabled={
                selectedCandidates.length === 0
                || selectedCandidates.length > MAX_CANDIDATE_SELECTION
                || mutations.accept.isPending
              }
              onClick={() => void runSelectionAction('accept')}
            >
              <Check className="mr-1.5 size-3.5" />接受所选
            </Button>
          </div>
        </div>
      </div>

      <Dialog open={Boolean(editing)} onOpenChange={(open) => !open && setEditing(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>编辑知识点</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4">
            <label className="grid gap-1.5 text-sm">
              <span>知识点标题</span>
              <Input aria-label="知识点标题" value={editTitle} onChange={(event) => setEditTitle(event.target.value)} />
            </label>
            <label className="grid gap-1.5 text-sm">
              <span>知识点类型</span>
              <Input aria-label="知识点类型" value={editType} onChange={(event) => setEditType(event.target.value)} />
            </label>
            <label className="grid gap-1.5 text-sm">
              <span>摘要</span>
              <Textarea aria-label="知识点摘要" value={editSummary} onChange={(event) => setEditSummary(event.target.value)} />
            </label>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setEditing(null)}>取消</Button>
            <Button type="button" onClick={() => void saveEdit()} disabled={mutations.update.isPending || !editTitle.trim() || !editType.trim()}>
              保存修改
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={mergeOpen} onOpenChange={setMergeOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>合并所选知识点</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4">
            <label className="grid gap-1.5 text-sm">
              <span>保留哪个候选</span>
              <Select value={mergeTargetId} onChange={(event) => setMergeTargetId(event.target.value)}>
                {selectedCandidates.map((candidate) => (
                  <option key={candidate.knowledge_point_id} value={candidate.knowledge_point_id}>
                    {candidate.title}
                  </option>
                ))}
              </Select>
            </label>
            <label className="grid gap-1.5 text-sm">
              <span>合并后标题</span>
              <Input value={mergeTitle} onChange={(event) => setMergeTitle(event.target.value)} />
            </label>
            <label className="grid gap-1.5 text-sm">
              <span>知识点类型</span>
              <Input value={mergeType} onChange={(event) => setMergeType(event.target.value)} />
            </label>
            <label className="grid gap-1.5 text-sm">
              <span>摘要</span>
              <Textarea value={mergeSummary} onChange={(event) => setMergeSummary(event.target.value)} />
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={mergeAccepted} onChange={(event) => setMergeAccepted(event.target.checked)} />
              合并后直接接受
            </label>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setMergeOpen(false)}>取消</Button>
            <Button type="button" onClick={() => void submitMerge()} disabled={mutations.merge.isPending || !mergeTitle.trim() || !mergeType.trim()}>
              确认合并
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(splitTarget)} onOpenChange={(open) => !open && setSplitTarget(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>拆分知识点</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4">
            {splitItems.map((item, index) => (
              <div key={index} className="grid gap-3 border-l-2 pl-3" style={{ borderColor: 'var(--color-border-muted)' }}>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-xs font-medium text-muted-foreground">
                    拆分项 {index + 1}
                  </span>
                  <Button
                    type="button"
                    size="icon"
                    variant="ghost"
                    className="size-8"
                    aria-label={`删除拆分项 ${index + 1}`}
                    disabled={splitItems.length <= 2}
                    onClick={() =>
                      setSplitItems((current) =>
                        current.filter((_, entryIndex) => entryIndex !== index),
                      )
                    }
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                </div>
                <label className="grid gap-1.5 text-sm">
                  <span>拆分项 {index + 1} 标题</span>
                  <Input
                    value={item.title}
                    onChange={(event) => setSplitItems((current) => current.map((entry, entryIndex) => entryIndex === index ? { ...entry, title: event.target.value } : entry))}
                  />
                </label>
                <label className="grid gap-1.5 text-sm">
                  <span>知识点类型</span>
                  <Input
                    value={item.point_type}
                    onChange={(event) => setSplitItems((current) => current.map((entry, entryIndex) => entryIndex === index ? { ...entry, point_type: event.target.value } : entry))}
                  />
                </label>
                <label className="grid gap-1.5 text-sm">
                  <span>摘要</span>
                  <Textarea
                    value={item.summary}
                    onChange={(event) => setSplitItems((current) => current.map((entry, entryIndex) => entryIndex === index ? { ...entry, summary: event.target.value } : entry))}
                  />
                </label>
              </div>
            ))}
            <Button
              type="button"
              variant="outline"
              disabled={splitItems.length >= MAX_SPLIT_ITEMS}
              onClick={() =>
                setSplitItems((current) =>
                  current.length >= MAX_SPLIT_ITEMS
                    ? current
                    : [
                        ...current,
                        {
                          title: '',
                          summary: '',
                          point_type: splitTarget?.point_type ?? 'concept',
                        },
                      ],
                )
              }
            >
              增加拆分项
            </Button>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setSplitTarget(null)}>取消</Button>
            <Button
              type="button"
              onClick={() => void submitSplit()}
              disabled={
                mutations.split.isPending
                || splitItems.length < 2
                || splitItems.length > MAX_SPLIT_ITEMS
                || splitItems.some(
                  (item) => !item.title.trim() || !item.point_type.trim(),
                )
              }
            >
              确认拆分
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </main>
  );
}
