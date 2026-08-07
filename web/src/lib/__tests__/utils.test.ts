import { describe, it, expect } from 'vitest';
import { cn, dateStrInTz, utcOffsetLabel } from '../utils';

describe('cn', () => {
  it('merges simple class names', () => {
    expect(cn('foo', 'bar')).toBe('foo bar');
  });

  it('handles conditional classes via clsx syntax', () => {
    // eslint-disable-next-line no-constant-binary-expression
    expect(cn('base', false && 'hidden', 'visible')).toBe('base visible');
  });

  it('merges tailwind conflicting classes (last wins)', () => {
    // twMerge should resolve conflicts
    const result = cn('px-2 py-1', 'px-4');
    expect(result).toContain('px-4');
    expect(result).not.toContain('px-2');
  });

  it('returns empty string for no inputs', () => {
    expect(cn()).toBe('');
  });

  it('handles undefined and null inputs gracefully', () => {
    expect(cn('a', undefined, null, 'b')).toBe('a b');
  });
});

describe('dateStrInTz', () => {
  it('formats the same instant as different local dates', () => {
    // 2025-07-02 23:00 UTC is already July 3 in Hong Kong and still July 2 in New York.
    const ms = Date.UTC(2025, 6, 2, 23, 0);
    expect(dateStrInTz(ms, 'Asia/Hong_Kong')).toBe('2025-07-03');
    expect(dateStrInTz(ms, 'America/New_York')).toBe('2025-07-02');
  });
});

describe('utcOffsetLabel', () => {
  const summer = new Date(Date.UTC(2025, 6, 2, 12, 0));
  const winter = new Date(Date.UTC(2025, 0, 15, 12, 0));

  it('labels whole-hour offsets without minutes', () => {
    expect(utcOffsetLabel('Asia/Hong_Kong', summer)).toBe('UTC+8');
    expect(utcOffsetLabel('Asia/Hong_Kong', winter)).toBe('UTC+8'); // no DST
  });

  it('is DST-aware', () => {
    expect(utcOffsetLabel('America/New_York', summer)).toBe('UTC-4');
    expect(utcOffsetLabel('America/New_York', winter)).toBe('UTC-5');
    expect(utcOffsetLabel('Europe/London', summer)).toBe('UTC+1');
    expect(utcOffsetLabel('Europe/London', winter)).toBe('UTC');
  });

  it('keeps minutes for half-hour zones', () => {
    expect(utcOffsetLabel('Asia/Kolkata', summer)).toBe('UTC+5:30');
  });
});
