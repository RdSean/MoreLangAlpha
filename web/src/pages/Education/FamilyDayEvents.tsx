import { useMemo } from 'react';
import { ChevronDown, MapPin } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { createDateFormatter } from '@/lib/format';
import type { FamilyCalendarEvent } from './calendarApi';

export default function FamilyDayEvents({ events, timezone }: { events: FamilyCalendarEvent[]; timezone: string }) {
  useTranslation();
  const time = useMemo(() => createDateFormatter({ timeZone: timezone, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }), [timezone]);
  const dateTime = useMemo(() => createDateFormatter({ timeZone: timezone, month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }), [timezone]);
  if (!events.length) return null;
  return <section aria-label="当天家庭日程" className="border-b px-4 py-4 sm:px-6">
    <h3 className="mb-2 text-sm font-semibold">家庭日程 <span className="ml-1 text-xs font-normal text-muted-foreground">{events.length} 项</span></h3>
    <div className="divide-y">{events.map(event => {
      const start = new Date(event.start_at);
      const end = new Date(event.end_at);
      const crossDay = event.start_at.slice(0, 10) !== event.end_at.slice(0, 10);
      const label = event.all_day ? '全天' : event.start_at === event.end_at ? time(start) : crossDay ? `${dateTime(start)} 至 ${dateTime(end)}` : `${time(start)} – ${time(end)}`;
      return <details key={event.event_id} className="group py-2">
        <summary className="grid min-h-11 cursor-pointer list-none grid-cols-[minmax(0,1fr)_20px] items-center gap-x-4 gap-y-1 rounded-sm py-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring sm:grid-cols-[144px_minmax(0,1fr)_20px] [&::-webkit-details-marker]:hidden">
          <span className="break-words text-xs tabular-nums text-muted-foreground sm:row-span-2">{label}</span>
          <span className="row-span-3 flex justify-end sm:col-start-3 sm:row-span-2"><ChevronDown aria-hidden="true" className="size-4 text-muted-foreground transition-transform group-open:rotate-180" /></span>
          <span className="min-w-0 break-words text-sm font-medium [overflow-wrap:anywhere] sm:col-start-2 sm:row-start-1">{event.title}</span>
          <span className="break-words text-xs text-muted-foreground sm:col-start-2">{event.source_name}</span>
        </summary>
        <div className="min-w-0 space-y-2 pb-2 pt-3 text-sm sm:ml-[160px]">
          {event.location && <p className="flex items-start gap-2"><MapPin aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-muted-foreground" /><span className="break-words [overflow-wrap:anywhere]">{event.location}</span></p>}
          {event.description && <p className="whitespace-pre-wrap break-words text-muted-foreground [overflow-wrap:anywhere]">{event.description}</p>}
          {!event.location && !event.description && <p className="text-xs text-muted-foreground">暂无备注</p>}
        </div>
      </details>;
    })}</div>
  </section>;
}
