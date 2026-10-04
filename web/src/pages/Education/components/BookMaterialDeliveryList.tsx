import { useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useTranslation } from 'react-i18next';
import type {
  BookActivityEvent,
  BookJob,
  BookJobItem,
  KnowledgePointProjection,
} from '../types';
import { BOOK_JOB_STATUS_LABELS } from './bookActivityProjection';
import {
  formatBookDuration,
  hasMatchingBookTiming,
  selectBookExecutionItem,
} from './bookTimingProjection';
import { BookAgentActions } from './BookAgentActions';

export function BookMaterialDeliveryList({
  job,
  knowledgePoints = [],
  agentActions,
  onOpenMaterial,
}: {
  job: BookJob;
  knowledgePoints?: readonly KnowledgePointProjection[];
  agentActions: readonly BookActivityEvent[];
  onOpenMaterial?: (skillKpId: string) => void;
}) {
  useTranslation();
  const [completedOpen, setCompletedOpen] = useState(false);
  const [limit, setLimit] = useState(20);
  const [completedLimit, setCompletedLimit] = useState(20);
  const currentItem = selectBookExecutionItem(job);
  const items = job.items.filter((item) => item.kind === 'material');
  if (!items.length) return null;
  const completed = items.filter((item) => item.status === 'succeeded');
  const unfinished = items.filter((item) => item.status !== 'succeeded');
  const foldCompleted = completed.length > 10;
  const renderItem = (item: BookJobItem) => {
    const point = knowledgePoints.find(
      (point) =>
        point.knowledge_point_id === item.knowledge_point_id ||
        point.skill_kp_id === item.skill_kp_id,
    );
    const title =
      item.knowledge_point_title?.trim() ||
      point?.title ||
      `讲义任务（本次第 ${item.position} 项）`;
    const skillId = item.skill_kp_id ?? point?.skill_kp_id;
    const olderAvailable =
      item.status !== 'succeeded' && Boolean(point?.material_available);
    const canRead = Boolean(
      skillId && (item.status === 'succeeded' || olderAvailable),
    );
    const recordedMs = hasMatchingBookTiming(job, item)
      ? item.timing_summary!.total_ms
      : null;
    const actions = agentActions.filter(
      (entry) =>
        entry.item_id === item.item_id &&
        (!item.started_at ||
          Date.parse(entry.created_at) >= Date.parse(item.started_at)),
    );
    return (
      <li
        key={item.item_id}
        aria-label={title}
        className="border-b py-3 text-sm"
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <h3 className="break-words font-medium">{title}</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              {item.status === 'not_run'
                ? '未执行'
                : item.status === 'succeeded'
                  ? '已提交'
                  : BOOK_JOB_STATUS_LABELS[item.status]}{' '}
              · {formatBookDuration(recordedMs)}
            </p>
            {olderAvailable && (
              <p className="mt-1 text-xs text-muted-foreground">
                旧版讲义仍可阅读
              </p>
            )}
          </div>
          {canRead && onOpenMaterial && (
            <Button
              variant="outline"
              className="min-h-11 shrink-0"
              aria-label={`${olderAvailable ? '阅读旧版讲义' : '阅读讲义'}：${title}`}
              onClick={() => onOpenMaterial(skillId!)}
            >
              {olderAvailable ? '阅读旧版讲义' : '阅读讲义'}
            </Button>
          )}
        </div>
        {item.item_id !== currentItem?.item_id && actions.length > 0 && (
          <details className="mt-2">
            <summary className="min-h-11 cursor-pointer py-3 text-xs text-muted-foreground">
              Agent 上报记录（{actions.length}）
            </summary>
            <BookAgentActions actions={actions} />
          </details>
        )}
      </li>
    );
  };
  return (
    <section aria-label="讲义交付" className="my-5">
      <h2 className="text-sm font-semibold">讲义交付</h2>
      <ol>
        {unfinished.slice(0, limit).map(renderItem)}
        {(!foldCompleted ? completed : completed.slice(0, 1)).map(renderItem)}
      </ol>
      {unfinished.length > limit && (
        <Button
          variant="ghost"
          className="min-h-11"
          onClick={() => setLimit(limit + 20)}
        >
          更多讲义任务
        </Button>
      )}
      {foldCompleted && (
        <>
          <button
            type="button"
            className="flex min-h-11 items-center gap-2 text-sm"
            aria-expanded={completedOpen}
            onClick={() => setCompletedOpen(!completedOpen)}
          >
            <ChevronDown
              className={`size-4 ${completedOpen ? '' : '-rotate-90'}`}
              aria-hidden="true"
            />
            已提交讲义（{completed.length}）
          </button>
          {completedOpen && (
            <>
              <ol>{completed.slice(1, completedLimit + 1).map(renderItem)}</ol>
              {completed.length > completedLimit + 1 && (
                <Button
                  variant="ghost"
                  className="min-h-11"
                  onClick={() => setCompletedLimit(completedLimit + 20)}
                >
                  更多已提交讲义
                </Button>
              )}
            </>
          )}
        </>
      )}
    </section>
  );
}
