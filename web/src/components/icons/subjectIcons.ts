import type { EducationIconName } from './educationIcons';

/**
 * Which icon stands for which subject.
 *
 * Keys are the `education_subjects.code` values the backend dictionary serves,
 * so nothing has to translate names at the call site.
 *
 * The batch covers most subjects literally (数学, 英语, 化学, 生物, 地理) but has
 * no dedicated 物理 / 历史 / 政治 icon. Those three borrow the closest available
 * shape rather than falling back to a generic book, because a generic icon on
 * three of nine subjects reads as "unfinished" in the picker. Swap them here
 * when the source batch grows — it is the only place the choice lives.
 */
export const SUBJECT_ICONS: Record<string, EducationIconName> = {
  chinese: '课文',
  math: '数学',
  english: '英语',
  chemistry: '化学',
  biology: '生物',
  geography: '地理',
  // Closest available: an orbit/planet for physics, a closed book for history,
  // a target for politics.
  physics: '天文',
  history: '书本',
  politics: '目标',
};

/** Used for a subject code the batch has nothing specific for. */
export const DEFAULT_SUBJECT_ICON: EducationIconName = '书本';

/** Never throws: an unknown or absent subject code gets the default icon. */
export function iconForSubject(subject: string | null | undefined): EducationIconName {
  if (!subject) return DEFAULT_SUBJECT_ICON;
  return SUBJECT_ICONS[subject] ?? DEFAULT_SUBJECT_ICON;
}
