import { describe, expect, it } from 'vitest';
import { calendarMonth, householdToday } from '../calendarDates';

describe('household calendar dates', () => {
  it('uses the household day at a UTC date boundary', () => {
    const now = new Date('2026-10-10T23:30:00Z');
    expect(householdToday('Asia/Tokyo', now)).toBe('2026-10-11');
    expect(householdToday('America/Los_Angeles', now)).toBe('2026-10-10');
  });
  it('builds a Monday-first leap February without timezone day shifts', () => {
    const month = calendarMonth('2028-02-12');
    expect(month.start_date).toBe('2028-02-01');
    expect(month.end_date).toBe('2028-02-29');
    expect(month.cells[0]).toBeNull();
    expect(month.cells[1]).toBe('2028-02-01');
    expect(month.cells.filter(Boolean)).toHaveLength(29);
  });
});
