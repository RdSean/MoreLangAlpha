import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
  EDUCATION_ICONS,
  EDUCATION_ICON_TONE_ALPHA,
  isEducationIconName,
} from '../educationIcons';
import {
  DEFAULT_SUBJECT_ICON,
  SUBJECT_ICONS,
  iconForSubject,
} from '../subjectIcons';
import { SubjectIcon } from '../SubjectIcon';

// The subject codes the backend dictionaries ship. Kept here literally so a
// new subject that reaches the UI without an icon is a test failure rather
// than a silently generic glyph.
const DICTIONARY_SUBJECT_CODES = [
  'chinese',
  'math',
  'english',
  'physics',
  'chemistry',
  'biology',
  'geography',
  'history',
  'politics',
];

describe('education icon set', () => {
  it('carries every icon with at least one path and only known tones', () => {
    const names = Object.keys(EDUCATION_ICONS);
    expect(names).toHaveLength(24);
    for (const [name, paths] of Object.entries(EDUCATION_ICONS)) {
      expect(paths.length, `${name} has no paths`).toBeGreaterThan(0);
      for (const path of paths) {
        expect([1, 2, 3]).toContain(path.tone);
        expect(path.d.length).toBeGreaterThan(8);
      }
    }
  });

  it('declares an alpha for every tone', () => {
    expect(EDUCATION_ICON_TONE_ALPHA[1]).toBe(1);
    expect(EDUCATION_ICON_TONE_ALPHA[2]).toBeGreaterThan(EDUCATION_ICON_TONE_ALPHA[3]);
  });

  it('narrows arbitrary strings', () => {
    expect(isEducationIconName('数学')).toBe(true);
    expect(isEducationIconName('数学x')).toBe(false);
  });
});

describe('subject mapping', () => {
  it('maps every dictionary subject to a real icon', () => {
    for (const code of DICTIONARY_SUBJECT_CODES) {
      const icon = iconForSubject(code);
      expect(isEducationIconName(icon), `${code} maps to unknown icon ${icon}`).toBe(true);
      expect(EDUCATION_ICONS[icon].length).toBeGreaterThan(0);
    }
  });

  it('points the literal subject matches at the matching artwork', () => {
    expect(SUBJECT_ICONS.math).toBe('数学');
    expect(SUBJECT_ICONS.english).toBe('英语');
    expect(SUBJECT_ICONS.chemistry).toBe('化学');
    expect(SUBJECT_ICONS.biology).toBe('生物');
    expect(SUBJECT_ICONS.geography).toBe('地理');
  });

  it('falls back instead of throwing for unknown or absent subjects', () => {
    expect(iconForSubject('astrophysics')).toBe(DEFAULT_SUBJECT_ICON);
    expect(iconForSubject('')).toBe(DEFAULT_SUBJECT_ICON);
    expect(iconForSubject(null)).toBe(DEFAULT_SUBJECT_ICON);
    expect(iconForSubject(undefined)).toBe(DEFAULT_SUBJECT_ICON);
  });
});

describe('SubjectIcon', () => {
  it('renders the mapped shape for a subject code', () => {
    const { container } = render(<SubjectIcon subject="math" />);
    expect(container.querySelector('svg[data-icon="数学"]')).not.toBeNull();
  });

  it('renders one path per tone with the tone alpha', () => {
    const { container } = render(<SubjectIcon subject="chemistry" />);
    const paths = container.querySelectorAll('path');
    expect(paths.length).toBe(EDUCATION_ICONS['化学'].length);
    paths.forEach((path, index) => {
      const tone = EDUCATION_ICONS['化学'][index].tone;
      expect(path.getAttribute('fill')).toBe('currentColor');
      expect(Number(path.getAttribute('fill-opacity'))).toBe(EDUCATION_ICON_TONE_ALPHA[tone]);
    });
  });

  it('takes an explicit colour and otherwise inherits', () => {
    const { container, rerender } = render(<SubjectIcon subject="math" color="#277DA1" />);
    let svg = container.querySelector('svg') as SVGElement;
    expect(svg.style.color).toBe('rgb(39, 125, 161)');

    rerender(<SubjectIcon subject="math" />);
    svg = container.querySelector('svg') as SVGElement;
    // No inline colour — the icon follows whatever text colour surrounds it.
    expect(svg.style.color).toBe('');
  });

  it('is decorative by default and named when asked', () => {
    const { container, rerender } = render(<SubjectIcon subject="math" />);
    expect(container.querySelector('svg')?.getAttribute('aria-hidden')).toBe('true');

    rerender(<SubjectIcon subject="math" title="数学" />);
    const svg = container.querySelector('svg');
    expect(svg?.getAttribute('aria-hidden')).toBeNull();
    expect(svg?.getAttribute('aria-label')).toBe('数学');
  });

  it('honours an explicit icon over the subject map', () => {
    const { container } = render(<SubjectIcon subject="math" icon="奖励" />);
    expect(container.querySelector('svg[data-icon="奖励"]')).not.toBeNull();
  });

  it('honours the requested size', () => {
    const { container } = render(<SubjectIcon subject="math" size={28} />);
    const svg = container.querySelector('svg');
    expect(svg?.getAttribute('width')).toBe('28');
    expect(svg?.getAttribute('height')).toBe('28');
  });
});
