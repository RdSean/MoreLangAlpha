import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { SubjectIcon } from '@/components/icons/SubjectIcon';
import { homeworkScheduleArtifactSchema } from '@/contracts/homeworkSchedule';
import { CARD_BG, CARD_BORDER } from './inlineCardsShared';

/**
 * The homework schedule an agent tool returned, rendered inside the transcript.
 *
 * This is a *copy* of the dashboard widget's rendering rather than a shared
 * component, and the difference is structural: the widget is a container that
 * fetches its own data, is config-driven and is aware of edit mode, whereas a
 * transcript card must render a payload and reproduce identically when the
 * thread is replayed from stored events. They are kept honest by the contract
 * instead — both derive their types from the same Pydantic models
 * (`web/src/contracts/homeworkSchedule.ts`), so a payload change fails the
 * drift test rather than one of the two silently breaking.
 *
 * Two consequences of being a leaf:
 * - Child names come from `student_names` in the payload; there is no member
 *   fetch to make.
 * - The grouping is by day, not by the widget's today-relative buckets, because
 *   the tool can be asked about any period ("上周的作业") and "tomorrow" is not a
 *   meaningful heading for last week.
 */
interface InlineHomeworkCardProps {
  artifact: Record<string, unknown>;
  onClick?: () => void;
}

function localDateStr(d: Date): string {
  return d.toLocaleDateString('en-CA');
}

function dueClock(dueAt: string): string {
  const parsed = new Date(dueAt);
  if (Number.isNaN(parsed.getTime())) return '';
  return parsed.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

function InlineHomeworkCard({ artifact, onClick }: InlineHomeworkCardProps) {
  const { t, i18n } = useTranslation();

  // The contract is enforced here rather than trusted. A payload that does not
  // satisfy it renders a plain notice instead of throwing inside the
  // transcript — the difference between a broken-looking message and a broken
  // thread.
  const parsed = useMemo(() => homeworkScheduleArtifactSchema.safeParse(artifact), [artifact]);

  const dayFormat = useMemo(
    () => new Intl.DateTimeFormat(i18n.language, { month: 'short', day: 'numeric', weekday: 'short' }),
    [i18n.language],
  );

  if (!parsed.success) {
    return (
      <div
        data-testid="inline-homework-invalid"
        style={{
          background: CARD_BG,
          border: `1px solid ${CARD_BORDER}`,
          borderRadius: 8,
          padding: '10px 12px',
          color: 'var(--color-text-tertiary)',
          fontSize: '0.75rem',
        }}
      >
        {t('dashboard.widgets.homeworkCalendar.unavailable')}
      </div>
    );
  }

  const schedule = parsed.data;
  const todayStr = localDateStr(new Date());
  const tomorrowStr = localDateStr(new Date(Date.now() + 86_400_000));
  const namedDays = (schedule.days ?? []).filter((day) => day.tasks.length > 0);

  return (
    <div
      data-testid="inline-homework-card"
      onClick={onClick}
      style={{
        background: CARD_BG,
        border: `1px solid ${CARD_BORDER}`,
        borderRadius: 8,
        padding: '12px 14px',
        cursor: onClick ? 'pointer' : 'default',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 8 }}>
        <span style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--color-text-primary)' }}>
          {t('dashboard.widgets.homeworkCalendar.title')}
        </span>
        <span
          className="dashboard-mono"
          style={{ fontSize: '0.6563rem', color: 'var(--color-text-tertiary)' }}
        >
          {schedule.start_date === schedule.end_date
            ? schedule.start_date
            : `${schedule.start_date} → ${schedule.end_date}`}
        </span>
      </div>

      <div
        data-testid="inline-homework-stats"
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '2px 14px',
          margin: '6px 0 10px',
          borderBottom: `1px solid ${CARD_BORDER}`,
          paddingBottom: 6,
        }}
      >
        {(
          [
            ['today', 'stat_today', schedule.stats.today_count],
            ['week', 'stat_week', schedule.stats.week_count],
            ['overdue', 'stat_overdue', schedule.stats.overdue_count],
            ['completed', 'stat_completed', schedule.stats.completed_count],
          ] as const
        ).map(([key, labelKey, value]) => (
          <span key={key} data-stat={key} style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
            <span
              className="dashboard-mono"
              style={{
                fontSize: '0.8125rem',
                fontWeight: 600,
                fontVariantNumeric: 'tabular-nums',
                color: key === 'overdue' && value > 0 ? 'var(--color-loss)' : 'var(--color-text-primary)',
              }}
            >
              {value}
            </span>
            <span style={{ fontSize: '0.625rem', color: 'var(--color-text-tertiary)' }}>
              {t(`dashboard.widgets.homeworkCalendar.${labelKey}`)}
            </span>
          </span>
        ))}
      </div>

      {namedDays.length === 0 ? (
        <div
          data-testid="inline-homework-empty"
          style={{ fontSize: '0.75rem', color: 'var(--color-text-tertiary)', padding: '4px 0' }}
        >
          {t('dashboard.widgets.homeworkCalendar.dayEmpty')}
        </div>
      ) : (
        namedDays.map((day) => (
          <div key={day.date} style={{ marginBottom: 8 }}>
            <div
              data-testid="inline-homework-day"
              data-date={day.date}
              style={{
                fontSize: '0.625rem',
                fontWeight: 600,
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
                color: 'var(--color-text-tertiary)',
                marginBottom: 2,
              }}
            >
              {day.date === todayStr
                ? t('dashboard.widgets.homeworkCalendar.bucket_today')
                : day.date === tomorrowStr
                  ? t('dashboard.widgets.homeworkCalendar.bucket_tomorrow')
                  : dayFormat.format(new Date(`${day.date}T00:00:00`))}
            </div>
            {day.tasks.map((task) => (
              <div
                key={task.task_id}
                data-testid="inline-homework-task"
                data-task-id={task.task_id}
                data-overdue={task.is_overdue ? 'true' : 'false'}
                style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '2px 0' }}
              >
                <SubjectIcon
                  subject={task.subject_code}
                  color={task.subject_color ?? 'var(--color-text-tertiary)'}
                  size={20}
                />
                <span
                  style={{
                    flex: 1,
                    minWidth: 0,
                    fontSize: '0.8125rem',
                    color: 'var(--color-text-primary)',
                    textDecoration: task.is_completed ? 'line-through' : undefined,
                    opacity: task.is_completed ? 0.6 : 1,
                  }}
                >
                  {task.title}
                </span>
                <span style={{ fontSize: '0.6563rem', color: 'var(--color-text-tertiary)' }}>
                  {[
                    schedule.student_names?.[task.assigned_student_id],
                    dueClock(task.due_at),
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                </span>
                {task.is_overdue ? (
                  <span
                    className="dashboard-mono"
                    style={{
                      fontSize: '0.5938rem',
                      textTransform: 'uppercase',
                      letterSpacing: '0.08em',
                      color: 'var(--color-loss)',
                    }}
                  >
                    {t('dashboard.widgets.homeworkCalendar.overdueBadge')}
                  </span>
                ) : null}
              </div>
            ))}
          </div>
        ))
      )}
    </div>
  );
}

export default InlineHomeworkCard;
