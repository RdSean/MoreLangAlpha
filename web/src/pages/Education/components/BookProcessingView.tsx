import { useEffect, useRef, useState } from 'react';
import { ArrowDown, ArrowLeft, ChevronDown } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { createDateFormatter } from '@/lib/format';
import { Button } from '@/components/ui/button';
import { Loader } from '@/components/ui/loader';
import type {
  BookActivityEvent,
  BookJob,
  BookJobStatistics,
  BookSourceStatus,
  KnowledgePointProjection,
} from '../types';
import { BookTimingSummary } from './BookTimingSummary';
import {
  formatBookDuration,
  type BookTimingProjection,
} from './bookTimingProjection';
import {
  isTerminalBookJobStatus,
  projectBookActivity,
  BOOK_JOB_STATUS_LABELS,
  isAgentBookActivity,
  type BookActivityProjection,
} from './bookActivityProjection';
import { BookLiveActivity, BookLiveActivityView } from './BookLiveActivity';
import type { BookLiveActivityProjection } from './useBookLiveActivity';
import { ActivityIcon } from './BookActivityPanel';
import { BookServiceMilestones } from './BookServiceMilestones';
import { BookMaterialDeliveryList } from './BookMaterialDeliveryList';

interface Props {
  job: BookJob;
  events: readonly BookActivityEvent[];
  connected: boolean;
  reconnecting?: boolean;
  liveAfterSeq?: number | null;
  timing: BookTimingProjection;
  liveActivity?: BookLiveActivityProjection;
  projection?: BookActivityProjection;
  sourceStatus?: BookSourceStatus;
  knowledgePoints?: readonly KnowledgePointProjection[];
  onReturnToReading: () => void;
  onOpenMaterial?: (skillKpId: string) => void;
  historyOpen?: boolean;
  onHistoryOpenChange?: () => void;
  statistics?: readonly BookJobStatistics[];
  statisticsLoading?: boolean;
  statisticsError?: boolean;
  onLoadMoreStatistics?: () => void;
  hasMoreStatistics?: boolean;
}

export function BookProcessingView({
  job,
  events,
  connected,
  reconnecting,
  liveAfterSeq,
  timing,
  liveActivity,
  projection,
  sourceStatus,
  knowledgePoints,
  onReturnToReading,
  onOpenMaterial,
  historyOpen,
  onHistoryOpenChange,
  statistics,
  statisticsLoading,
  statisticsError,
  onLoadMoreStatistics,
  hasMoreStatistics,
}: Props) {
  useTranslation();
  const activity = projection ?? projectBookActivity(job, events);
  const terminal = isTerminalBookJobStatus(job.status);
  const [following, setFollowing] = useState(false);
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);
  const [diagnosticLimit, setDiagnosticLimit] = useState(50);
  const bottom = useRef<HTMLDivElement>(null);
  const scroll = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (following)
      bottom.current?.scrollIntoView?.({ block: 'end', behavior: 'auto' });
  }, [following, events]);
  useEffect(() => {
    setDiagnosticsOpen(false);
    setDiagnosticLimit(50);
    setFollowing(false);
  }, [job.job_id]);
  const progress = activity.currentItem?.preparation_progress;
  const formatTime = createDateFormatter({
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
  const stats = statistics?.[0];

  return (
    <section className="book-processing-view" aria-label="教材处理时间线">
      <header className="book-processing-header">
        <div className="min-w-0">
          <h1 className="text-lg font-semibold">处理时间线</h1>
          <p className="mt-1 break-words text-sm text-muted-foreground">
            {job.kind === 'structure' ? '教材结构' : '讲义加工'} ·{' '}
            {BOOK_JOB_STATUS_LABELS[job.status]}
          </p>
        </div>
        <Button
          variant="outline"
          className="min-h-11 shrink-0"
          onClick={onReturnToReading}
        >
          <ArrowLeft className="mr-2 size-4" aria-hidden="true" />
          返回阅读
        </Button>
      </header>
      <div
        className="book-processing-scroll"
        data-testid="book-processing-scroll"
        ref={scroll}
        onScroll={() => {
          const element = scroll.current;
          if (
            element &&
            element.scrollHeight - element.scrollTop - element.clientHeight > 80
          )
            setFollowing(false);
        }}
      >
        <div className="book-processing-content">
          <BookTimingSummary timing={timing} />
          {!connected && !terminal && (
            <p className="mt-2 text-xs text-muted-foreground">
              {reconnecting ? '正在重新连接活动流 · ' : ''}显示最后确认的时间
            </p>
          )}
          {activity.materialProgress && (
            <p className="mt-4 text-sm">
              已完成 {activity.materialProgress.completed}/
              {activity.materialProgress.total} 份讲义
            </p>
          )}
          {!terminal && (
            <div className="my-6 flex items-start gap-3">
              <span className="shrink-0 pt-1" aria-hidden="true">
                <Loader size={16} />
              </span>
              <div className="min-w-0 flex-1">
                {activity.currentObjectLabel && (
                  <p className="break-words text-xs text-muted-foreground">
                    {activity.currentObjectLabel}
                  </p>
                )}
                <p
                  className="mt-1 break-words text-sm font-medium"
                  aria-live="polite"
                >
                  {activity.currentStage &&
                  isAgentBookActivity(activity.currentStage)
                    ? 'PTC 执行中'
                    : activity.currentDescription}
                </p>
                {progress && (
                  <p className="mt-2 text-sm tabular-nums">
                    已校验 {progress.verified_resources}/
                    {progress.total_resources ?? '待确认'} 个资源
                  </p>
                )}
                {progress &&
                  activity.currentItem?.execution_phase === 'source_freezing' &&
                  progress.total_resources !== null &&
                  progress.verified_resources === progress.total_resources && (
                    <p className="mt-1 text-xs text-muted-foreground">
                      等待来源清单确认
                    </p>
                  )}
                {activity.currentItem &&
                  !activity.activityUnavailable &&
                  (liveActivity ? (
                    <BookLiveActivityView activity={liveActivity} />
                  ) : (
                    <BookLiveActivity
                      key={`${job.job_id}:${activity.currentItem.item_id}:${activity.currentItem.attempt}`}
                      job={job}
                      item={activity.currentItem}
                      events={events}
                      connected={connected}
                      liveAfterSeq={liveAfterSeq}
                    />
                  ))}
              </div>
            </div>
          )}
          {activity.activityUnavailable && (
            <p className="my-4 text-sm text-muted-foreground" role="status">
              活动暂不可用，任务状态仍会继续更新。
            </p>
          )}
          <BookServiceMilestones
            job={job}
            timing={timing}
            sourceStatus={sourceStatus}
            agentActions={activity.agentActions}
          />
          <BookMaterialDeliveryList
            key={job.job_id}
            job={job}
            knowledgePoints={knowledgePoints}
            agentActions={activity.agentActions}
            onOpenMaterial={onOpenMaterial}
          />
          <BookActivityTimeline
            activity={activity}
            job={job}
            onOpenMaterial={onOpenMaterial}
          />
          {terminal && (
            <p className="my-5 break-words text-sm" role="status">
              {job.safe_error || BOOK_JOB_STATUS_LABELS[job.status]}
            </p>
          )}
          {activity.toolDetails.length > 0 && (
            <section className="mt-5 border-t pt-2">
              <button
                type="button"
                className="flex min-h-11 items-center gap-2 text-sm text-muted-foreground"
                aria-expanded={diagnosticsOpen}
                onClick={() => setDiagnosticsOpen(!diagnosticsOpen)}
              >
                <ChevronDown
                  className={`size-4 ${diagnosticsOpen ? '' : '-rotate-90'}`}
                  aria-hidden="true"
                />
                诊断明细（{activity.toolDetails.length}）
              </button>
              {diagnosticsOpen && (
                <>
                  <ol className="space-y-2 text-xs text-muted-foreground">
                    {activity.toolDetails
                      .slice(-diagnosticLimit)
                      .map((entry) => (
                        <li key={entry.seq} className="break-words">
                          <time className="mr-3 tabular-nums">
                            {formatTime(Date.parse(entry.created_at))}
                          </time>
                          {entry.message}
                        </li>
                      ))}
                  </ol>
                  {diagnosticLimit < activity.toolDetails.length && (
                    <Button
                      variant="ghost"
                      className="min-h-11"
                      onClick={() => setDiagnosticLimit(diagnosticLimit + 50)}
                    >
                      更早的诊断
                    </Button>
                  )}
                </>
              )}
            </section>
          )}
          {onHistoryOpenChange && (
            <section className="mt-5 border-t pt-2">
              <button
                type="button"
                className="flex min-h-11 items-center gap-2 text-sm text-muted-foreground"
                aria-expanded={Boolean(historyOpen)}
                onClick={onHistoryOpenChange}
              >
                <ChevronDown
                  className={`size-4 ${historyOpen ? '' : '-rotate-90'}`}
                  aria-hidden="true"
                />
                尝试与批量统计
              </button>
              {historyOpen && (
                <>
                  {statisticsLoading && (
                    <p className="text-xs text-muted-foreground">
                      正在读取统计…
                    </p>
                  )}
                  {statisticsError && (
                    <p className="text-xs text-destructive">统计暂不可用</p>
                  )}
                  {stats && (
                    <p className="mb-3 text-xs text-muted-foreground">
                      本轮成功讲义样本 {stats.material_sample_count} · 中位{' '}
                      {formatBookDuration(stats.material_median_ms)} · 最长{' '}
                      {formatBookDuration(stats.material_longest_ms)}
                    </p>
                  )}
                  {stats && stats.supplementary.length > 0 && (
                    <section
                      aria-label="附加材料统计"
                      className="my-3 text-xs text-muted-foreground"
                    >
                      <h3 className="mb-2 font-medium">附加材料</h3>
                      <ol className="space-y-2">
                        {stats.supplementary.map((attempt) => (
                          <li
                            key={`${attempt.item_id}:${attempt.timing.attempt}`}
                            className="break-words"
                          >
                            第 {attempt.timing.attempt} 次尝试 ·{' '}
                            {attempt.status === 'interrupted'
                              ? '已中断'
                              : attempt.status === 'not_run'
                                ? '未执行'
                                : BOOK_JOB_STATUS_LABELS[attempt.status]}{' '}
                            · {formatBookDuration(attempt.timing.total_ms)}
                          </li>
                        ))}
                      </ol>
                    </section>
                  )}
                  <ol className="space-y-3 text-xs">
                    {statistics
                      ?.flatMap((page) => page.attempts)
                      .map((attempt) => (
                        <li
                          key={`${attempt.item_id}:${attempt.timing.attempt}`}
                          className="break-words"
                        >
                          {attempt.knowledge_point_title ||
                            (attempt.kind === 'structure'
                              ? '教材结构'
                              : attempt.kind === 'material'
                                ? '讲义任务'
                                : '附加材料')}{' '}
                          · 第 {attempt.timing.attempt} 次尝试 ·{' '}
                          {attempt.status === 'interrupted'
                            ? '已中断'
                            : attempt.status === 'not_run'
                              ? '未执行'
                              : BOOK_JOB_STATUS_LABELS[attempt.status]}{' '}
                          · {formatBookDuration(attempt.timing.total_ms)}
                        </li>
                      ))}
                  </ol>
                  {hasMoreStatistics && (
                    <Button
                      variant="ghost"
                      className="min-h-11"
                      disabled={statisticsLoading}
                      onClick={onLoadMoreStatistics}
                    >
                      更多尝试
                    </Button>
                  )}
                </>
              )}
            </section>
          )}
          <div ref={bottom} />
        </div>
      </div>
      <footer className="book-processing-footer">
        <Button
          variant="ghost"
          className="min-h-11"
          aria-pressed={following}
          onClick={() => setFollowing(!following)}
        >
          <ArrowDown className="mr-2 size-4" aria-hidden="true" />
          {following ? '正在跟随最新' : '跟随最新'}
        </Button>
      </footer>
    </section>
  );
}

export function BookActivityTimeline({
  activity,
  job,
  onOpenMaterial,
}: {
  activity: BookActivityProjection;
  job: BookJob;
  onOpenMaterial?: (skillKpId: string) => void;
}) {
  useTranslation();
  const [completedOpen, setCompletedOpen] = useState(false);
  const [limit, setLimit] = useState(20);
  const [activityLimit, setActivityLimit] = useState(50);
  useEffect(() => {
    setCompletedOpen(false);
    setLimit(20);
    setActivityLimit(50);
  }, [job.job_id]);
  const completedIds = new Set(
    job.items
      .filter((item) => item.status === 'succeeded')
      .map((item) => item.item_id),
  );
  const factualGroups = activity.groups
    .map((group) => ({
      ...group,
      events: group.events.filter((entry) => !isAgentBookActivity(entry)),
    }))
    .filter((group) => group.events.length > 0);
  const completed = factualGroups.filter(
    (group) => group.itemId && completedIds.has(group.itemId),
  );
  const collapse = completed.length > 10;
  const groups = factualGroups.filter(
    (group) => !collapse || !group.itemId || !completedIds.has(group.itemId),
  );
  const formatTime = createDateFormatter({
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
  const renderGroup = (group: BookActivityProjection['groups'][number]) => {
    const item = job.items.find((item) => item.item_id === group.itemId);
    return (
      <section key={group.key} className="book-activity-group min-w-0">
        {group.label && (
          <h3 className="mb-2 break-words text-sm font-medium">
            {group.label}
          </h3>
        )}
        <ol className="book-activity-timeline space-y-3">
          {group.events.map((entry) => (
            <li
              key={entry.seq}
              className="flex min-h-8 items-start gap-3 text-sm"
            >
              <ActivityIcon entry={entry} />
              <div className="min-w-0 flex-1">
                <p className="break-words text-muted-foreground">
                  {entry.message}
                </p>
                <time
                  className="text-xs tabular-nums text-muted-foreground"
                  dateTime={entry.created_at}
                >
                  {formatTime(Date.parse(entry.created_at))}
                </time>
              </div>
            </li>
          ))}
        </ol>
        {item?.kind === 'material' &&
          item.status === 'succeeded' &&
          item.skill_kp_id &&
          onOpenMaterial && (
            <Button
              className="mt-2 min-h-11"
              variant="outline"
              onClick={() => onOpenMaterial(item.skill_kp_id!)}
            >
              阅读讲义
            </Button>
          )}
      </section>
    );
  };
  return (
    <div className="mt-5 space-y-6">
      {groups.length > activityLimit && (
        <Button
          variant="ghost"
          className="min-h-11"
          onClick={() => setActivityLimit(activityLimit + 50)}
        >
          更早的活动记录
        </Button>
      )}
      {groups.slice(-activityLimit).map(renderGroup)}
      {collapse && (
        <section>
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
            已完成记录（{completed.length}）
          </button>
          {completedOpen && (
            <div className="space-y-6">
              {completed.slice(0, limit).map(renderGroup)}
              {limit < completed.length && (
                <Button
                  variant="ghost"
                  className="min-h-11"
                  onClick={() => setLimit(limit + 20)}
                >
                  更多已完成记录
                </Button>
              )}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
