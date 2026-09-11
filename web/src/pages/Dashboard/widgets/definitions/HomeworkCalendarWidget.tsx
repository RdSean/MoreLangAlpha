import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { CalendarCheck, Check, ChevronLeft, ChevronRight } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { SubjectIcon } from '@/components/icons/SubjectIcon';
import { useEducationMembers, useEducationTaskCalendar } from '@/pages/Education/queries';
import type { EducationCalendarTask, EducationMember } from '@/pages/Education/types';
import { registerWidget } from '../framework/WidgetRegistry';
import { useWidgetContextExport } from '../framework/contextSnapshot';
import { serializeRowsToMarkdown, wrapWidgetContext } from '../framework/snapshotSerializers';
import { HomeworkCalendarConfigSchema } from '../framework/configSchemas';
import { RowAttachButton } from '../../components/RowAttachButton';
import { EnumField } from '../framework/settings/EnumField';
import { SettingsDoneButton } from '../framework/settings/SettingsDoneButton';
import type { WidgetRenderProps, WidgetSettingsProps } from '../types';

type HomeworkCalendarConfig = {
  window?: '1w' | '2w' | '1m';
  showCompleted?: boolean;
};

/** Window length in days. Also the step size of the range stepper. */
const WINDOW_DAYS: Record<NonNullable<HomeworkCalendarConfig['window']>, number> = {
  '1w': 7,
  '2w': 14,
  '1m': 31,
};

/**
 * How many windows back the stepper may go. The API bounds the range (`end -
 * start < 62` days) and how far ahead the end may be, but puts no floor on how
 * old the start may be, so this is purely a guard against a held key spinning
 * the query key forever.
 */
const MAX_LOOKBACK_WINDOWS = 8;

type BucketKey = 'past' | 'today' | 'tomorrow' | 'week' | 'next' | 'later';

const BUCKET_KEY: Record<BucketKey, string> = {
  past: 'dashboard.widgets.homeworkCalendar.bucket_past',
  today: 'dashboard.widgets.homeworkCalendar.bucket_today',
  tomorrow: 'dashboard.widgets.homeworkCalendar.bucket_tomorrow',
  week: 'dashboard.widgets.homeworkCalendar.bucket_thisWeek',
  next: 'dashboard.widgets.homeworkCalendar.bucket_nextWeek',
  later: 'dashboard.widgets.homeworkCalendar.bucket_later',
};

const BUCKET_ORDER: BucketKey[] = ['past', 'today', 'tomorrow', 'week', 'next', 'later'];

/** Local-date YYYY-MM-DD. `toISOString()` would emit UTC, which crosses the
 *  day boundary for anyone east or west of it — a task due "today" would
 *  silently land in yesterday's or tomorrow's bucket. */
function localDateStr(d: Date = new Date()): string {
  return d.toLocaleDateString('en-CA');
}

function shiftDays(base: Date, days: number): Date {
  const next = new Date(base);
  next.setDate(next.getDate() + days);
  return next;
}

/** Whole days between two local YYYY-MM-DD strings, ignoring DST wobble. */
function daysBetween(from: string, to: string): number {
  const a = new Date(`${from}T00:00:00`).getTime();
  const b = new Date(`${to}T00:00:00`).getTime();
  return Math.round((b - a) / 86_400_000);
}

function bucketFor(dateStr: string, todayStr: string): BucketKey {
  const diff = daysBetween(todayStr, dateStr);
  if (diff < 0) return 'past';
  if (diff === 0) return 'today';
  if (diff === 1) return 'tomorrow';
  if (diff <= 6) return 'week';
  if (diff <= 13) return 'next';
  return 'later';
}

function dueClock(dueAt: string): string {
  const parsed = new Date(dueAt);
  if (Number.isNaN(parsed.getTime())) return '';
  return parsed.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

function memberName(members: EducationMember[], studentId: string): string | null {
  return members.find((member) => member.user_id === studentId)?.name ?? null;
}

function serializeTasksToMarkdown(
  tasks: EducationCalendarTask[],
  nameFor: (id: string) => string | null,
): string {
  // Flattened to display rows first: `serializeRowsToMarkdown` can only read
  // stored fields, and "overdue" is derived rather than stored.
  const rows = tasks.map((task) => ({
    date: task.occurrence_date,
    task: task.title,
    child: nameFor(task.assigned_student_id) ?? '',
    due: dueClock(task.due_at),
    status: task.is_overdue ? 'overdue' : task.status,
  }));
  return serializeRowsToMarkdown(rows, [
    { key: 'date', label: 'date' },
    { key: 'task', label: 'task' },
    { key: 'child', label: 'child' },
    { key: 'due', label: 'due' },
    { key: 'status', label: 'status' },
  ]);
}

interface TaskRowProps {
  task: EducationCalendarTask;
  instanceId: string;
  childName: string | null;
  onOpen: () => void;
}

function TaskRow({ task, instanceId, childName, onOpen }: TaskRowProps) {
  const { t } = useTranslation();
  const clock = dueClock(task.due_at);

  return (
    <button
      type="button"
      data-testid="homework-task"
      data-task-id={task.task_id}
      data-overdue={task.is_overdue ? 'true' : 'false'}
      data-completed={task.is_completed ? 'true' : 'false'}
      onClick={onOpen}
      aria-label={t('dashboard.widgets.homeworkCalendar.openTask', { title: task.title })}
      className="row-attach-host group relative flex w-full items-center gap-2 rounded-md border border-transparent px-2 py-1.5 text-left transition-colors hover:bg-[var(--color-bg-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      {/* 20px is the floor for this artwork: it is 1024-unit art whose tones
          carry the shape, and below ~20px the dark silhouette swallows the
          detail into a blob. */}
      <SubjectIcon
        subject={task.subject_code}
        color={task.subject_color ?? 'var(--color-text-tertiary)'}
        size={20}
        className="shrink-0"
      />
      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span
          className="truncate text-[0.8125rem] leading-tight"
          style={{
            color: 'var(--color-text-primary)',
            textDecoration: task.is_completed ? 'line-through' : undefined,
            opacity: task.is_completed ? 0.6 : 1,
          }}
        >
          {task.title}
        </span>
        {(childName || clock) && (
          <span
            className="truncate text-[0.6563rem]"
            style={{ color: 'var(--color-text-tertiary)' }}
          >
            {[childName, clock].filter(Boolean).join(' · ')}
          </span>
        )}
      </span>
      {task.is_completed ? (
        <Check
          className="size-3.5 flex-shrink-0"
          aria-hidden="true"
          style={{ color: 'var(--color-success)' }}
        />
      ) : null}
      {task.is_overdue ? (
        <span
          className="dashboard-mono flex-shrink-0 text-[0.5938rem] uppercase tracking-wider"
          style={{ color: 'var(--color-loss)' }}
        >
          {t('dashboard.widgets.homeworkCalendar.overdueBadge')}
        </span>
      ) : null}
      <span className="absolute right-1 top-1/2 -translate-y-1/2">
        <RowAttachButton instanceId={instanceId} rowId={task.task_id} />
      </span>
    </button>
  );
}

function BucketSection({
  label,
  bucket,
  tasks,
  instanceId,
  nameFor,
  onOpen,
}: {
  label: string;
  bucket: BucketKey;
  tasks: EducationCalendarTask[];
  instanceId: string;
  nameFor: (id: string) => string | null;
  onOpen: () => void;
}) {
  if (!tasks.length) return null;
  return (
    <div className="flex flex-col" data-testid="homework-bucket" data-bucket={bucket}>
      <div
        className="sticky top-0 z-10 -mx-1 mb-0.5 flex items-baseline gap-2 px-3 py-1"
        style={{ backgroundColor: 'var(--color-bg-card)' }}
      >
        <span
          className="text-[0.5938rem] font-semibold uppercase tracking-[0.16em]"
          style={{ color: 'var(--color-text-tertiary)' }}
        >
          {label}
        </span>
        <span className="h-px flex-1" style={{ backgroundColor: 'var(--color-border-muted)' }} />
        <span
          className="dashboard-mono text-[0.625rem] tabular-nums"
          style={{ color: 'var(--color-text-tertiary)', opacity: 0.7 }}
        >
          {String(tasks.length).padStart(2, '0')}
        </span>
      </div>
      <div className="flex flex-col">
        {tasks.map((task) => (
          <TaskRow
            key={task.task_id}
            task={task}
            instanceId={instanceId}
            childName={nameFor(task.assigned_student_id)}
            onOpen={onOpen}
          />
        ))}
      </div>
    </div>
  );
}

function StatChip({ stat, value }: { stat: string; value: number }) {
  const { t } = useTranslation();
  const labelKey = {
    today: 'dashboard.widgets.homeworkCalendar.stat_today',
    week: 'dashboard.widgets.homeworkCalendar.stat_week',
    overdue: 'dashboard.widgets.homeworkCalendar.stat_overdue',
    completed: 'dashboard.widgets.homeworkCalendar.stat_completed',
  }[stat] as string;
  const emphasize = stat === 'overdue' && value > 0;
  return (
    <span className="flex items-baseline gap-1" data-stat={stat}>
      <span
        className="dashboard-mono text-[0.875rem] font-semibold tabular-nums"
        style={{ color: emphasize ? 'var(--color-loss)' : 'var(--color-text-primary)' }}
      >
        {value}
      </span>
      <span className="text-[0.625rem]" style={{ color: 'var(--color-text-tertiary)' }}>
        {t(labelKey)}
      </span>
    </span>
  );
}

function HomeworkCalendarWidget({ instance }: WidgetRenderProps<HomeworkCalendarConfig>) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { member } = useAuth();
  const [offset, setOffset] = useState(0);

  const windowDays = WINDOW_DAYS[instance.config.window ?? '2w'];
  const showCompleted = instance.config.showCompleted ?? false;

  // The window starts at today and runs forward, so the default view answers
  // "what is coming up". Stepping back shifts the same-length window into the
  // past, which is what the previous-week control is for.
  const today = useMemo(() => new Date(), []);
  const todayStr = localDateStr(today);
  const range = useMemo(() => {
    const start = shiftDays(today, -offset * windowDays);
    return {
      start_date: localDateStr(start),
      end_date: localDateStr(shiftDays(start, windowDays - 1)),
    };
  }, [today, offset, windowDays]);

  const { data, isLoading } = useEducationTaskCalendar(range);
  // Students cannot read the household member list; asking would 403. The
  // calendar itself is already narrowed to their own tasks server-side.
  const { data: members = [] } = useEducationMembers(member?.role === 'parent');

  const nameFor = (studentId: string) => memberName(members, studentId);

  const tasks = useMemo(() => {
    const flat = (data?.days ?? [])
      .flatMap((day) => day.tasks)
      .filter((task) => task.status !== 'cancelled');
    return showCompleted ? flat : flat.filter((task) => !task.is_completed);
  }, [data, showCompleted]);

  const grouped = useMemo(() => {
    const buckets = {
      past: [] as EducationCalendarTask[],
      today: [] as EducationCalendarTask[],
      tomorrow: [] as EducationCalendarTask[],
      week: [] as EducationCalendarTask[],
      next: [] as EducationCalendarTask[],
      later: [] as EducationCalendarTask[],
    };
    for (const task of tasks) {
      buckets[bucketFor(task.occurrence_date, todayStr)].push(task);
    }
    for (const bucket of BUCKET_ORDER) {
      buckets[bucket].sort((a, b) => {
        const byDue = a.due_at.localeCompare(b.due_at);
        return byDue !== 0 ? byDue : a.task_id.localeCompare(b.task_id);
      });
    }
    return buckets;
  }, [tasks, todayStr]);

  useWidgetContextExport(instance.id, {
    full: () => {
      const sections: string[] = [];
      for (const bucket of BUCKET_ORDER) {
        if (!grouped[bucket].length) continue;
        sections.push(
          `### ${t(BUCKET_KEY[bucket])} (${grouped[bucket].length})`,
          '',
          serializeTasksToMarkdown(grouped[bucket], nameFor),
          '',
        );
      }
      const body = sections.length
        ? sections.join('\n').trimEnd()
        : `_${t('dashboard.widgets.homeworkCalendar.empty')}_`;
      return {
        widget_type: 'education.homeworkCalendar',
        widget_id: instance.id,
        label: `${t('dashboard.widgets.homeworkCalendar.title')} · ${tasks.length}`,
        description: `${range.start_date} → ${range.end_date}`,
        captured_at: new Date().toISOString(),
        text: wrapWidgetContext(
          'education.homeworkCalendar',
          {
            start_date: range.start_date,
            end_date: range.end_date,
            count: tasks.length,
            show_completed: String(showCompleted),
          },
          body,
        ),
        data: {
          start_date: range.start_date,
          end_date: range.end_date,
          stats: data?.stats ?? null,
          tasks,
        },
      };
    },
    rows: (rowId: string) => {
      const task = tasks.find((candidate) => candidate.task_id === rowId);
      if (!task) return null;
      const lines = [`**${task.title}** · ${task.occurrence_date}`];
      const child = nameFor(task.assigned_student_id);
      if (child) lines.push(child);
      if (task.description) lines.push(task.description);
      return {
        widget_type: 'education.homeworkCalendar/row',
        widget_id: `${instance.id}/${rowId}`,
        label: `${task.title} · ${task.occurrence_date}`,
        description: t('dashboard.widgets.homeworkCalendar.title'),
        captured_at: new Date().toISOString(),
        text: wrapWidgetContext(
          'education.homeworkCalendar/row',
          { task_id: task.task_id, date: task.occurrence_date },
          lines.join('\n'),
        ),
        data: { row: task },
      };
    },
  });

  const openEducation = () => navigate('/education');

  return (
    <div className="dashboard-glass-card flex h-full flex-col p-5" data-testid="homework-widget">
      <div className="mb-3 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div
            className="text-[0.5938rem] font-semibold uppercase tracking-[0.16em]"
            style={{ color: 'var(--color-text-tertiary)' }}
          >
            {t('dashboard.widgets.homeworkCalendar.title')}
          </div>
          <div
            className="dashboard-mono mt-0.5 text-[0.6563rem] tabular-nums"
            style={{ color: 'var(--color-text-tertiary)' }}
          >
            {offset === 0
              ? t('dashboard.widgets.homeworkCalendar.thisWeek')
              : `${range.start_date} → ${range.end_date}`}
          </div>
        </div>
        <div className="flex flex-shrink-0 items-center gap-0.5">
          <button
            type="button"
            data-testid="homework-prev"
            onClick={() => setOffset((current) => Math.min(current + 1, MAX_LOOKBACK_WINDOWS))}
            disabled={offset >= MAX_LOOKBACK_WINDOWS}
            title={t('dashboard.widgets.homeworkCalendar.previousWeek')}
            aria-label={t('dashboard.widgets.homeworkCalendar.previousWeek')}
            className="flex size-6 items-center justify-center rounded-md transition-colors hover:bg-[var(--color-bg-hover)] disabled:opacity-40"
          >
            <ChevronLeft className="size-3.5" aria-hidden="true" />
          </button>
          <button
            type="button"
            data-testid="homework-next"
            onClick={() => setOffset((current) => Math.max(current - 1, 0))}
            disabled={offset === 0}
            title={t('dashboard.widgets.homeworkCalendar.nextWeek')}
            aria-label={t('dashboard.widgets.homeworkCalendar.nextWeek')}
            className="flex size-6 items-center justify-center rounded-md transition-colors hover:bg-[var(--color-bg-hover)] disabled:opacity-40"
          >
            <ChevronRight className="size-3.5" aria-hidden="true" />
          </button>
        </div>
      </div>

      {/* The strip summarises where the household stands *right now*, so it is
          hidden while browsing a past window rather than mislabelled. */}
      {data && offset === 0 ? (
        <div
          data-testid="homework-stats"
          className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 border-b pb-2"
          style={{ borderColor: 'var(--color-border-muted)' }}
        >
          <StatChip stat="today" value={data.stats.today_count} />
          <StatChip stat="week" value={data.stats.week_count} />
          <StatChip stat="overdue" value={data.stats.overdue_count} />
          <StatChip stat="completed" value={data.stats.completed_count} />
        </div>
      ) : null}

      <div className="min-h-0 flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="flex h-full items-center justify-center">
            <span className="text-[0.6875rem]" style={{ color: 'var(--color-text-tertiary)' }}>
              {t('dashboard.widgets.common.loading')}
            </span>
          </div>
        ) : tasks.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
            <div
              className="flex size-9 items-center justify-center rounded-full"
              style={{ backgroundColor: 'var(--color-bg-subtle)' }}
            >
              <CalendarCheck
                className="size-4"
                aria-hidden="true"
                style={{ color: 'var(--color-text-tertiary)' }}
              />
            </div>
            <div
              className="dashboard-mono text-sm"
              style={{ color: 'var(--color-text-primary)' }}
            >
              {t('dashboard.widgets.homeworkCalendar.empty')}
            </div>
            <div className="text-[0.6875rem]" style={{ color: 'var(--color-text-tertiary)' }}>
              {t('dashboard.widgets.homeworkCalendar.emptyHint')}
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {BUCKET_ORDER.map((bucket) => (
              <BucketSection
                key={bucket}
                bucket={bucket}
                label={t(BUCKET_KEY[bucket])}
                tasks={grouped[bucket]}
                instanceId={instance.id}
                nameFor={nameFor}
                onOpen={openEducation}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function HomeworkCalendarSettings({
  config,
  onChange,
  onClose,
}: WidgetSettingsProps<HomeworkCalendarConfig>) {
  const { t } = useTranslation();
  const showCompleted = config.showCompleted ?? false;
  return (
    <div className="flex flex-col gap-4">
      <EnumField
        label={t('dashboard.widgets.homeworkCalendar.settings.window')}
        value={config.window ?? '2w'}
        onChange={(next) => onChange({ window: next as HomeworkCalendarConfig['window'] })}
        options={[
          { value: '1w', label: t('dashboard.widgets.homeworkCalendar.settings.window_1w') },
          { value: '2w', label: t('dashboard.widgets.homeworkCalendar.settings.window_2w') },
          { value: '1m', label: t('dashboard.widgets.homeworkCalendar.settings.window_1m') },
        ]}
      />
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={showCompleted}
          onChange={(event) => onChange({ showCompleted: event.target.checked })}
        />
        <span className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
          {t('dashboard.widgets.homeworkCalendar.settings.showCompleted')}
        </span>
      </label>
      <SettingsDoneButton onClick={onClose} />
    </div>
  );
}

registerWidget<HomeworkCalendarConfig>({
  type: 'education.homeworkCalendar',
  titleKey: 'dashboard.widgets.homeworkCalendar.title',
  descriptionKey: 'dashboard.widgets.homeworkCalendar.description',
  category: 'personal',
  icon: CalendarCheck,
  component: HomeworkCalendarWidget,
  defaultConfig: { window: '2w', showCompleted: false },
  configSchema: HomeworkCalendarConfigSchema,
  defaultSize: { w: 4, h: 26 },
  minSize: { w: 3, h: 15 },
  settingsComponent: HomeworkCalendarSettings,
});

export default HomeworkCalendarWidget;
