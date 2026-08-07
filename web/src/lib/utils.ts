import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** Convert UTC Unix ms (or a Date) to a YYYY-MM-DD date string in `tz`. */
export const dateStrInTz = (d: number | Date, tz: string): string =>
  new Date(d).toLocaleDateString('en-CA', { timeZone: tz });
/**
 * "UTC+8" / "UTC-4" / "UTC+5:30" label for a timezone at a given instant
 * (DST-aware — New York flips between UTC-5 and UTC-4).
 */
const offsetFormatters = new Map<string, Intl.DateTimeFormat>();

export function utcOffsetLabel(tz: string, at: Date = new Date()): string {
  // Intl.DateTimeFormat construction is expensive relative to formatting;
  // callers invoke this every clock tick, so cache one formatter per zone.
  let fmt = offsetFormatters.get(tz);
  if (!fmt) {
    fmt = new Intl.DateTimeFormat('en-US', { timeZone: tz, timeZoneName: 'longOffset' });
    offsetFormatters.set(tz, fmt);
  }
  const name = fmt.formatToParts(at).find((p) => p.type === 'timeZoneName')?.value ?? '';
  const m = name.match(/GMT([+-])(\d{2}):(\d{2})/);
  if (!m) return 'UTC'; // bare "GMT" — the zone IS UTC
  const [, sign, hours, minutes] = m;
  // ICU-version drift: some CLDR builds spell the zero offset "GMT+00:00"
  // instead of bare "GMT" — both mean plain UTC.
  if (Number(hours) === 0 && minutes === '00') return 'UTC';
  return `UTC${sign}${Number(hours)}${minutes === '00' ? '' : `:${minutes}`}`;
}

export const safeLocalStorage = {
  getItem: (key: string): string | null => {
    try {
      return localStorage.getItem(key);
    } catch (e) {
      if (import.meta.env.DEV) console.warn('safeLocalStorage.getItem failed:', e);
      return null;
    }
  },
  setItem: (key: string, value: string): void => {
    try {
      localStorage.setItem(key, value);
    } catch (e) {
      if (import.meta.env.DEV) console.warn('safeLocalStorage.setItem failed:', e);
    }
  },
  removeItem: (key: string): void => {
    try {
      localStorage.removeItem(key);
    } catch (e) {
      if (import.meta.env.DEV) console.warn('safeLocalStorage.removeItem failed:', e);
    }
  },
};
