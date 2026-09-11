import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import {
  CalendarCheck,
  CalendarDays,
  Check,
  ChevronLeft,
  ChevronRight,
  List,
} from 'lucide-react';
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

type HomeworkCalendarWindow = '1w' | '2w' | '1m';
type HomeworkCalendarView = 'list' | 'month';

type HomeworkCalendarConfig = {
  window?: HomeworkCalendarWindow;
  showCompleted?: boolean;
  view?: HomeworkCalendarView;
};

/** Window length in days. Also the step size of the range stepper. */
const WINDOW_DAYS: Record<HomeworkCalendarWindow, number> = {
  '1w': 7,
  '2w': 14,
  '1m': 31,
};

const WINDOW_OPTIONS: HomeworkCalendarWindow[] = ['1w', '2w', '1m'];

/**
 * How many windows back the list stepper may go. The API bounds the range
 * (`end - start < 62` days) and how far ahead the end may be, but puts no floor
 * on how old the start may be, so this is purely a guard against a held key
 * spinning the query key forever.
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

const WINDOW_LABEL_KEY: Record<HomeworkCalendarWindow, string> = {
  '1w': 'dashboard.widgets.homeworkCalendar.range_1w',
  '2w': 'dashboard.widgets.homeworkCalendar.range_2w',
  '1m': 'dashboard.widgets.homeworkCalendar.range_1m',
};

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

function startOfMonth(base: Date): Date {
  return new Date(base.getFullYear(), base.getMonth(), 1);
}

function endOfMonth(base: Date): Date {
  return new Date(base.getFullYear(), base.getMonth() + 1, 0);
}

function isSameMonth(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth();
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

/**
 * The week starts on Monday, matching how the backend derives its week window
 * (`isoweekday`), so the widget's "this week" and the grid's columns agree.
 */
function weekdayHeaders(locale: string): string[] {
  // 2024-01-01 is a Monday; walk forward so the formatter supplies the names.
  const monday = new Date(2024, 0, 1);
  const format = new Intl.DateTimeFormat(locale, { weekday: 'narrow' });
  return Array.from({ length: 7 }, (_, index) => format.format(shiftDays(monday, index)));
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
  testId: string;
}

function TaskRow({ task, instanceId, childName, onOpen, testId }: TaskRowProps) {
  const { t } = useTranslation();
  const clock = dueClock(task.due_at);

  return (
    <button
      type="button"
      data-testid={testId}
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
            testId="homework-task"
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

/** Distinct subject colours for a day, capped, with a remainder count. */
function dayDots(tasks: EducationCalendarTask[]): { colors: string[]; extra: number } {
  const seen = new Set<string>();
  const colors: string[] = [];
  for (const task of tasks) {
    const key = task.subject_code ?? `__${task.task_id}`;
    if (seen.has(key)) continue;
    seen.add(key);
    if (colors.length < 3) colors.push(task.subject_color ?? 'var(--color-text-tertiary)');
  }
  return { colors, extra: Math.max(0, seen.size - 3) };
}

function MonthGrid({
  cursor,
  today,
  locale,
  selectedDate,
  tasksByDate,
  onSelect,
}: {
  cursor: Date;
  today: Date;
  locale: string;
  selectedDate: string;
  tasksByDate: Map<string, EducationCalendarTask[]>;
  onSelect: (date: string) => void;
}) {
  const { t } = useTranslation();
  const headers = useMemo(() => weekdayHeaders(locale), [locale]);
  const monthStart = startOfMonth(cursor);
  // Monday-first, so a Monday has zero leading blanks.
  const leadingBlanks = (monthStart.getDay() + 6) % 7;
  const dayCount = endOfMonth(cursor).getDate();
  const todayStr = localDateStr(today);
  const dateFormat = useMemo(
    () => new Intl.DateTimeFormat(locale, { month: 'long', day: 'numeric', weekday: 'long' }),
    [locale],
  );

  return (
    <div data-testid="homework-month-grid" className="flex flex-col gap-0.5">
      <div className="grid grid-cols-7 gap-0.5">
        {headers.map((label, index) => (
          <span
            key={index}
            aria-hidden="true"
            className="py-0.5 text-center text-[0.5625rem] font-semibold uppercase tracking-wider"
            style={{ color: 'var(--color-text-tertiary)' }}
          >
            {label}
          </span>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-0.5">
        {Array.from({ length: leadingBlanks }, (_, index) => (
          <span key={`blank-${index}`} aria-hidden="true" />
        ))}
        {Array.from({ length: dayCount }, (_, index) => {
          const day = index + 1;
          const date = new Date(cursor.getFullYear(), cursor.getMonth(), day);
          const dateStr = localDateStr(date);
          const dayTasks = tasksByDate.get(dateStr) ?? [];
          const { colors, extra } = dayDots(dayTasks);
          const isToday = dateStr === todayStr;
          const selected = dateStr === selectedDate;
          const overdue = dayTasks.some((task) => task.is_overdue);
          return (
            <button
              key={dateStr}
              type="button"
              data-testid="homework-day"
              data-date={dateStr}
              data-in-month="true"
              data-overdue={overdue ? 'true' : 'false'}
              aria-pressed={selected}
              aria-label={`${dateFormat.format(date)} · ${dayTasks.length}`}
              onClick={() => onSelect(dateStr)}
              className="flex aspect-square flex-col items-center justify-center gap-0.5 rounded-md border transition-colors hover:bg-[var(--color-bg-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              style={{
                borderColor: isToday && !selected ? 'var(--color-accent-primary)' : 'transparent',
                backgroundColor: selected ? 'var(--color-bg-subtle)' : 'transparent',
              }}
            >
              <span
                className="dashboard-mono text-[0.6875rem] leading-none tabular-nums"
                style={{
                  color: overdue
                    ? 'var(--color-loss)'
                    : isToday
                      ? 'var(--color-accent-primary)'
                      : 'var(--color-text-primary)',
                  fontWeight: isToday || selected ? 600 : 400,
                }}
              >
                {day}
              </span>
              <span className="flex h-1.5 items-center gap-0.5">
                {colors.map((color, dotIndex) => (
                  <span
                    key={dotIndex}
                    data-dot="true"
                    className="size-1 rounded-full"
                    style={{ backgroundColor: color }}
                  />
                ))}
                {extra > 0 ? (
                  <span
                    className="text-[0.5rem] leading-none"
                    style={{ color: 'var(--color-text-tertiary)' }}
                  >
                    +{extra}
                  </span>
                ) : null}
              </span>
            </button>
          );
        })}
      </div>
      {dayCount === 0 ? <span>{t('dashboard.widgets.common.loading')}</span> : null}
    </div>
  );
}

function HomeworkCalendarWidget({ instance, updateConfig }: WidgetRenderProps<HomeworkCalendarConfig>) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { member } = useAuth();
  const [offset, setOffset] = useState(0);

  const windowSize = instance.config.window ?? '2w';
  const windowDays = WINDOW_DAYS[windowSize];
  const showCompleted = instance.config.showCompleted ?? false;
  const view: HomeworkCalendarView = instance.config.view ?? 'list';

  const today = useMemo(() => new Date(), []);
  const todayStr = localDateStr(today);
  const [monthCursor, setMonthCursor] = useState(() => startOfMonth(today));
  const [selectedDate, setSelectedDate] = useState(todayStr);

  // Range depends on the view: the list looks forward from today and can be
  // stepped back, the month grid always asks for exactly the month on screen.
  const range = useMemo(() => {
    if (view === 'month') {
      return {
        start_date: localDateStr(startOfMonth(monthCursor)),
        end_date: localDateStr(endOfMonth(monthCursor)),
      };
    }
    // The window starts at today and runs forward, so the default view answers
    // "what is coming up". Stepping back shifts the same-length window into the
    // past, which is what the previous-period control is for.
    const start = shiftDays(today, -offset * windowDays);
    return {
      start_date: localDateStr(start),
      end_date: localDateStr(shiftDays(start, windowDays - 1)),
    };
  }, [view, monthCursor, today, offset, windowDays]);

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

  const tasksByDate = useMemo(() => {
    const map = new Map<string, EducationCalendarTask[]>();
    for (const task of tasks) {
      const list = map.get(task.occurrence_date);
      if (list) list.push(task);
      else map.set(task.occurrence_date, [task]);
    }
    for (const list of map.values()) {
      list.sort((a, b) => {
        const byDue = a.due_at.localeCompare(b.due_at);
        return byDue !== 0 ? byDue : a.task_id.localeCompare(b.task_id);
      });
    }
    return map;
  }, [tasks]);

  const selectedTasks = view === 'month' ? (tasksByDate.get(selectedDate) ?? []) : [];

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
            view,
            show_completed: String(showCompleted),
          },
          body,
        ),
        data: {
          start_date: range.start_date,
          end_date: range.end_date,
          view,
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

  const onCurrentPeriod = view === 'month' ? isSameMonth(monthCursor, today) : offset === 0;
  const monthLabel = useMemo(
    () => new Intl.DateTimeFormat(i18n.language, { year: 'numeric', month: 'long' }).format(monthCursor),
    [i18n.language, monthCursor],
  );

  const goPrevious = () => {
    if (view === 'month') {
      const previous = new Date(monthCursor.getFullYear(), monthCursor.getMonth() - 1, 1);
      setMonthCursor(previous);
      setSelectedDate(isSameMonth(previous, today) ? todayStr : localDateStr(previous));
      return;
    }
    setOffset((current) => Math.min(current + 1, MAX_LOOKBACK_WINDOWS));
  };

  const goNext = () => {
    if (view === 'month') {
      const next = new Date(monthCursor.getFullYear(), monthCursor.getMonth() + 1, 1);
      setMonthCursor(next);
      setSelectedDate(isSameMonth(next, today) ? todayStr : localDateStr(next));
      return;
    }
    setOffset((current) => Math.max(current - 1, 0));
  };

  const goToCurrentMonth = () => {
    setMonthCursor(startOfMonth(today));
    setSelectedDate(todayStr);
  };

  return (
    <div className="dashboard-glass-card flex h-full flex-col p-5" data-testid="homework-widget">
      <div className="mb-2 flex flex-col gap-1.5">
        <div className="flex items-start justify-between gap-2">
          <div
            className="truncate text-[0.5938rem] font-semibold uppercase tracking-[0.16em]"
            style={{ color: 'var(--color-text-tertiary)' }}
          >
            {t('dashboard.widgets.homeworkCalendar.title')}
          </div>
          <div
            role="group"
            aria-label={t('dashboard.widgets.homeworkCalendar.title')}
            className="flex flex-shrink-0 items-center gap-0.5 rounded-md border p-0.5"
            style={{ borderColor: 'var(--color-border-muted)' }}
          >
            {(
              [
                { value: 'list' as const, icon: List, key: 'view_list', testId: 'homework-view-list' },
                {
                  value: 'month' as const,
                  icon: CalendarDays,
                  key: 'view_month',
                  testId: 'homework-view-month',
                },
              ]
            ).map(({ value, icon: Icon, key, testId }) => {
              const active = view === value;
              return (
                <button
                  key={value}
                  type="button"
                  data-testid={testId}
                  aria-pressed={active}
                  title={t(`dashboard.widgets.homeworkCalendar.${key}`)}
                  onClick={() => updateConfig({ view: value })}
                  className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[0.625rem] transition-colors"
                  style={{
                    backgroundColor: active ? 'var(--color-bg-elevated)' : 'transparent',
                    color: active ? 'var(--color-text-primary)' : 'var(--color-text-tertiary)',
                    fontWeight: active ? 600 : 400,
                  }}
                >
                  <Icon size={11} aria-hidden="true" />
                  {t(`dashboard.widgets.homeworkCalendar.${key}`)}
                </button>
              );
            })}
          </div>
        </div>

        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-1.5">
            {view === 'list' ? (
              <div
                role="group"
                aria-label={t('dashboard.widgets.homeworkCalendar.settings.window')}
                className="flex items-center gap-0.5"
              >
                {WINDOW_OPTIONS.map((option) => {
                  const active = windowSize === option;
                  return (
                    <button
                      key={option}
                      type="button"
                      data-testid={`homework-range-${option}`}
                      aria-pressed={active}
                      onClick={() => updateConfig({ window: option })}
                      className="rounded px-1.5 py-0.5 text-[0.625rem] tabular-nums transition-colors"
                      style={{
                        backgroundColor: active ? 'var(--color-bg-subtle)' : 'transparent',
                        color: active ? 'var(--color-text-primary)' : 'var(--color-text-tertiary)',
                        fontWeight: active ? 600 : 400,
                      }}
                    >
                      {t(WINDOW_LABEL_KEY[option])}
                    </button>
                  );
                })}
              </div>
            ) : (
              <>
                <span
                  className="dashboard-mono truncate text-[0.6875rem] tabular-nums"
                  style={{ color: 'var(--color-text-secondary)' }}
                >
                  {monthLabel}
                </span>
                {!onCurrentPeriod ? (
                  <button
                    type="button"
                    data-testid="homework-back-to-month"
                    onClick={goToCurrentMonth}
                    className="rounded px-1.5 py-0.5 text-[0.625rem] transition-colors hover:bg-[var(--color-bg-hover)]"
                    style={{ color: 'var(--color-accent-primary)' }}
                  >
                    {t('dashboard.widgets.homeworkCalendar.backToThisMonth')}
                  </button>
                ) : null}
              </>
            )}
          </div>

          <div className="flex flex-shrink-0 items-center gap-0.5">
            <button
              type="button"
              data-testid="homework-prev"
              onClick={goPrevious}
              disabled={view === 'list' && offset >= MAX_LOOKBACK_WINDOWS}
              title={t('dashboard.widgets.homeworkCalendar.previousPeriod')}
              aria-label={t('dashboard.widgets.homeworkCalendar.previousPeriod')}
              className="flex size-6 items-center justify-center rounded-md transition-colors hover:bg-[var(--color-bg-hover)] disabled:opacity-40"
            >
              <ChevronLeft className="size-3.5" aria-hidden="true" />
            </button>
            <button
              type="button"
              data-testid="homework-next"
              onClick={goNext}
              disabled={view === 'list' && offset === 0}
              title={t('dashboard.widgets.homeworkCalendar.nextPeriod')}
              aria-label={t('dashboard.widgets.homeworkCalendar.nextPeriod')}
              className="flex size-6 items-center justify-center rounded-md transition-colors hover:bg-[var(--color-bg-hover)] disabled:opacity-40"
            >
              <ChevronRight className="size-3.5" aria-hidden="true" />
            </button>
          </div>
        </div>
      </div>

      {/* The strip summarises where the household stands *right now*, so it is
          hidden while browsing anything other than the current period — a past
          window or another month — rather than being mislabelled. */}
      {data && onCurrentPeriod ? (
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
        ) : view === 'month' ? (
          <div className="flex flex-col gap-3">
            <MonthGrid
              cursor={monthCursor}
              today={today}
              locale={i18n.language}
              selectedDate={selectedDate}
              tasksByDate={tasksByDate}
              onSelect={setSelectedDate}
            />
            <div className="flex flex-col gap-1" data-testid="homework-day-list">
              {selectedTasks.length === 0 ? (
                <p
                  data-testid="homework-day-empty"
                  className="py-3 text-center text-[0.6875rem]"
                  style={{ color: 'var(--color-text-tertiary)' }}
                >
                  {t('dashboard.widgets.homeworkCalendar.dayEmpty')}
                </p>
              ) : (
                selectedTasks.map((task) => (
                  <TaskRow
                    key={task.task_id}
                    task={task}
                    instanceId={instance.id}
                    childName={nameFor(task.assigned_student_id)}
                    onOpen={openEducation}
                    testId="homework-day-task"
                  />
                ))
              )}
            </div>
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
        onChange={(next) => onChange({ window: next as HomeworkCalendarWindow })}
        options={[
          { value: '1w', label: t('dashboard.widgets.homeworkCalendar.settings.window_1w') },
          { value: '2w', label: t('dashboard.widgets.homeworkCalendar.settings.window_2w') },
          { value: '1m', label: t('dashboard.widgets.homeworkCalendar.settings.window_1m') },
        ]}
      />
      <EnumField
        label={t('dashboard.widgets.homeworkCalendar.settings.defaultView')}
        value={config.view ?? 'list'}
        onChange={(next) => onChange({ view: next as HomeworkCalendarView })}
        options={[
          { value: 'list', label: t('dashboard.widgets.homeworkCalendar.view_list') },
          { value: 'month', label: t('dashboard.widgets.homeworkCalendar.view_month') },
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
  defaultConfig: { window: '2w', showCompleted: false, view: 'list' },
  configSchema: HomeworkCalendarConfigSchema,
  defaultSize: { w: 4, h: 26 },
  // The month grid needs roughly six rows of cells plus a day list, so the
  // frame's floor is higher than a plain list would need.
  minSize: { w: 3, h: 20 },
  settingsComponent: HomeworkCalendarSettings,
});

export default HomeworkCalendarWidget;
