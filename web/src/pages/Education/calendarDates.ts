const dayMs = 86_400_000;
export const dateString = (date: Date) => date.toISOString().slice(0, 10);
export const parseDate = (value: string) => new Date(`${value}T00:00:00Z`);

// Machine date serialization, independent of the browser's locale/timezone.
export function householdToday(timezone: string, now = new Date()) {
  const parts = new Intl.DateTimeFormat('en', { timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(now);
  const get = (type: string) => parts.find(part => part.type === type)!.value;
  return `${get('year')}-${get('month')}-${get('day')}`;
}

export function calendarMonth(value: string) {
  const date = parseDate(value);
  const first = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), 1));
  const last = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + 1, 0));
  const offset = (first.getUTCDay() + 6) % 7;
  const length = Math.ceil((offset + last.getUTCDate()) / 7) * 7;
  return {
    start_date: dateString(first), end_date: dateString(last),
    cells: Array.from({ length }, (_, index) => index < offset || index >= offset + last.getUTCDate()
      ? null : dateString(new Date(first.getTime() + (index - offset) * dayMs))),
  };
}

