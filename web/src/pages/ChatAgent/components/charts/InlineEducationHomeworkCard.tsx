import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { SubjectIcon } from '@/components/icons/SubjectIcon';
import { educationHomeworkArtifactSchema } from '@/contracts/educationHomework';
import { CARD_BG, CARD_BORDER } from './inlineCardsShared';

/**
 * The task `education_create_homework` created, rendered in the transcript.
 *
 * Before this card existed the tool's artifact had no published type, so the
 * message ended at the tool step: the work visibly happened, and nothing said
 * what it produced. The card closes that loop with the two things the parent
 * asked for in the first place — which child, and when it is due — plus the
 * stored title, with the payload validated against the generated contract
 * rather than trusted.
 */
interface InlineEducationHomeworkCardProps {
  artifact: Record<string, unknown>;
  onClick?: () => void;
}

function dueStamp(dueAt: string, language: string): string {
  const parsed = new Date(dueAt);
  if (Number.isNaN(parsed.getTime())) return dueAt;
  return new Intl.DateTimeFormat(language, {
    month: 'short',
    day: 'numeric',
    weekday: 'short',
    hour: '2-digit',
    minute: '2-digit',
  }).format(parsed);
}

function InlineEducationHomeworkCard({ artifact, onClick }: InlineEducationHomeworkCardProps) {
  const { t, i18n } = useTranslation();

  const parsed = useMemo(
    () => educationHomeworkArtifactSchema.safeParse(artifact),
    [artifact],
  );

  if (!parsed.success) {
    return (
      <div
        data-testid="inline-education-homework-invalid"
        style={{
          background: CARD_BG,
          border: `1px solid ${CARD_BORDER}`,
          borderRadius: 8,
          padding: '10px 12px',
          color: 'var(--color-text-tertiary)',
          fontSize: '0.75rem',
        }}
      >
        {t('chat.homeworkCard.unavailable')}
      </div>
    );
  }

  const homework = parsed.data;
  const task = homework.task;

  return (
    <div
      data-testid="inline-education-homework-card"
      data-task-id={homework.task_id}
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
          {t('chat.homeworkCard.title')}
        </span>
        <span
          className="dashboard-mono"
          style={{ fontSize: '0.6563rem', color: 'var(--color-text-tertiary)' }}
        >
          {dueStamp(homework.due_at, i18n.language)}
        </span>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8 }}>
        <SubjectIcon
          subject={task.subject_code}
          color="var(--color-text-tertiary)"
          size={20}
        />
        <span
          data-testid="inline-education-homework-title"
          style={{
            flex: 1,
            minWidth: 0,
            fontSize: '0.8125rem',
            color: 'var(--color-text-primary)',
          }}
        >
          {task.title}
        </span>
      </div>

      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '2px 10px',
          marginTop: 6,
          borderTop: `1px solid ${CARD_BORDER}`,
          paddingTop: 6,
          fontSize: '0.6875rem',
          color: 'var(--color-text-tertiary)',
        }}
      >
        <span data-testid="inline-education-homework-student">
          {t('chat.homeworkCard.assignedTo', { name: homework.student_name })}
        </span>
        {!homework.attachments_supported && (
          <span data-testid="inline-education-homework-text-only">
            {t('chat.homeworkCard.textOnly')}
          </span>
        )}
      </div>
    </div>
  );
}

export default InlineEducationHomeworkCard;
