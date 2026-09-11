import {
  EDUCATION_ICON_TONE_ALPHA,
  EDUCATION_ICONS,
  type EducationIconName,
} from './educationIcons';
import { iconForSubject } from './subjectIcons';

export interface SubjectIconProps {
  /** Subject code from the education dictionary, e.g. `math`. Unknown codes
   *  fall back rather than rendering nothing. */
  subject?: string | null;
  /** Pick a shape explicitly instead of going through the subject map. */
  icon?: EducationIconName;
  /** Rendered size in px; the artwork is square. */
  size?: number;
  /**
   * Tint. Omit to inherit the surrounding text colour — that is what makes the
   * icon usable inside a selected (colour-on-colour) button without a second
   * variant.
   */
  color?: string;
  className?: string;
  /** Set to give the icon an accessible name; omitted renders it decorative. */
  title?: string;
}

/**
 * One icon from the education batch, tinted with the current colour.
 *
 * The three source tones are drawn as `currentColor` at different alphas, so a
 * single colour prop yields the same two-tone read the original artwork has —
 * and it survives a dark surface, where a hard-coded light tint would not.
 */
export function SubjectIcon({
  subject,
  icon,
  size = 16,
  color,
  className,
  title,
}: SubjectIconProps) {
  const name = icon ?? iconForSubject(subject);
  const paths = EDUCATION_ICONS[name];

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 1024 1024"
      data-icon={name}
      className={className}
      role={title ? 'img' : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
      focusable="false"
      style={{ color, display: 'block', flexShrink: 0 }}
    >
      {title ? <title>{title}</title> : null}
      {paths.map((path, index) => (
        <path
          key={index}
          d={path.d}
          fill="currentColor"
          fillOpacity={EDUCATION_ICON_TONE_ALPHA[path.tone]}
        />
      ))}
    </svg>
  );
}

export default SubjectIcon;
