import { api } from '@/api/client';

export interface FamilyCalendarSource {
  source_id: string;
  household_id: string;
  name: string;
  filename: string;
  event_count: number;
  updated_at: string;
}

export interface FamilyCalendarEvent {
  event_id: string;
  uid: string;
  source_id: string;
  source_name: string;
  title: string;
  description: string;
  location: string;
  all_day: boolean;
  start_at: string;
  end_at: string;
  dates: string[];
}

export interface FamilyCalendarRange { start_date: string; end_date: string }
export interface FamilyCalendarEvents extends FamilyCalendarRange {
  household_id: string;
  timezone: string;
  events: FamilyCalendarEvent[];
}

export async function getFamilyCalendarSources(): Promise<FamilyCalendarSource[]> {
  return (await api.get<FamilyCalendarSource[]>('/api/v1/education/calendar/sources')).data;
}

export async function importFamilyCalendar({ file, sourceId }: { file: File; sourceId?: string }): Promise<FamilyCalendarSource> {
  const form = new FormData();
  form.append('file', file);
  if (sourceId) form.append('source_id', sourceId);
  return (await api.post<FamilyCalendarSource>('/api/v1/education/calendar/sources', form, { headers: { 'Content-Type': 'multipart/form-data' } })).data;
}

export async function removeFamilyCalendar(sourceId: string): Promise<void> {
  await api.delete(`/api/v1/education/calendar/sources/${encodeURIComponent(sourceId)}`);
}

export async function getFamilyCalendarEvents(params: FamilyCalendarRange): Promise<FamilyCalendarEvents> {
  return (await api.get<FamilyCalendarEvents>('/api/v1/education/calendar/events', { params })).data;
}
