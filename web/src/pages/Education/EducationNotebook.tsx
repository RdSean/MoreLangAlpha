import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { CalendarDays, ChevronLeft, ChevronRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import pokemonball from '@/assets/img/pokemonball.svg';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { createDateFormatter } from '@/lib/format';
import { calendarMonth, householdToday, parseDate, dateString } from './calendarDates';
import { useEducationTaskCalendar } from './queries';
import type { EducationCalendarTask, EducationHomeworkDictionaries, EducationMember, EducationTask } from './types';

const coreSubjects = [
  { code: 'chinese', name: '语文' },
  { code: 'math', name: '数学' },
  { code: 'english', name: '英语' },
];
const weekdays = ['一', '二', '三', '四', '五', '六', '日'];
function HomeworkDots({ tasks, dictionaries }: { tasks: EducationCalendarTask[]; dictionaries: EducationHomeworkDictionaries }) {
  // One circle per homework item; compact overflow keeps seven columns usable on phones.
  const visible = tasks.length > 3 ? tasks.slice(0, 2) : tasks;
  return <span aria-hidden="true" className="isolate flex items-center justify-center -space-x-2 sm:-space-x-2.5">
    {visible.map(task => {
      const subject = dictionaries.subjects.find(item => item.code === task.subject_code);
      const color = subject?.color || task.subject_color || 'var(--color-text-secondary)';
      const hex = /^#([0-9a-f]{6})$/i.exec(color)?.[1];
      const channels = hex ? [0, 2, 4].map(offset => {
        const value = parseInt(hex.slice(offset, offset + 2), 16) / 255;
        return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
      }) : null;
      const light = channels && channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722 > 0.179;
      return <span key={task.task_id} title={`${subject?.name ?? '作业'}：${task.title}`} className="relative flex size-[18px] shrink-0 items-center justify-center rounded-full border border-card text-[9px] font-semibold sm:size-7 sm:border-2 sm:text-xs"
        style={{ backgroundColor: color, color: light ? 'var(--color-text-primary)' : 'var(--color-bg-card)' }}>{(subject?.name ?? '作业').slice(0, 1)}</span>;
    })}
    {tasks.length > 3 && <span className="relative flex size-[18px] shrink-0 items-center justify-center rounded-full border border-card bg-[var(--color-text-primary)] text-[8px] font-semibold text-[var(--color-bg-card)] sm:size-7 sm:border-2 sm:text-[11px]">+{tasks.length - 2}</span>}
  </span>;
}

interface Props {
  role: 'parent' | 'student';
  dictionaries: EducationHomeworkDictionaries;
  members: EducationMember[];
  actions: ReactNode;
  renderTasks: (tasks: EducationTask[]) => ReactNode;
}

export default function EducationNotebook({ role, dictionaries, members, actions, renderTasks }: Props) {
  useTranslation();
  const [today, setToday] = useState(() => householdToday(dictionaries.timezone));
  const [selectedDate, setSelectedDate] = useState(today);
  const [month, setMonth] = useState(today.slice(0, 7));
  const [studentId, setStudentId] = useState('');
  useEffect(() => {
    const refresh = () => setToday(householdToday(dictionaries.timezone));
    const timer = window.setInterval(refresh, 60_000);
    window.addEventListener('focus', refresh);
    return () => { window.clearInterval(timer); window.removeEventListener('focus', refresh); };
  }, [dictionaries.timezone]);
  const range = calendarMonth(`${month}-01`);
  const calendar = useEducationTaskCalendar({ start_date: range.start_date, end_date: range.end_date, ...(role === 'parent' && studentId ? { student_id: studentId } : {}) });
  const dateLabel = useMemo(() => createDateFormatter({ timeZone: 'UTC', month: 'long', day: 'numeric', weekday: 'long' }), []);
  const monthLabel = useMemo(() => createDateFormatter({ timeZone: 'UTC', year: 'numeric', month: 'long' }), []);
  const days = new Map(calendar.data?.days.map(day => [day.date, day]) ?? []);
  const selected = days.get(selectedDate);
  const tasks = selected?.tasks ?? [];
  const optionalCodes = [...new Set(tasks.map(task => task.subject_code ?? 'other'))].filter(code => !coreSubjects.some(subject => subject.code === code));
  optionalCodes.sort((a, b) => (dictionaries.subjects.find(s => s.code === a)?.sort_order ?? 999) - (dictionaries.subjects.find(s => s.code === b)?.sort_order ?? 999));
  const subjects = [...coreSubjects, ...optionalCodes.map(code => ({ code, name: dictionaries.subjects.find(subject => subject.code === code)?.name ?? '其他作业' }))];
  const nextMonth = (delta: number) => {
    const date = parseDate(`${month}-01`);
    return dateString(new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + delta, 1)));
  };
  const maxDate = dateString(new Date(parseDate(today).getTime() + 365 * 86_400_000));
  const changeMonth = (delta: number) => { const next = nextMonth(delta); setMonth(next.slice(0, 7)); setSelectedDate(next); };
  const jumpToday = () => { setMonth(today.slice(0, 7)); setSelectedDate(today); };
  const hasData = Boolean(calendar.data) && !calendar.isError;

  return <>
    <header className="flex flex-wrap items-center justify-between gap-4">
      <div className="flex items-center gap-3">
        <div className="flex size-12 items-center justify-center rounded-full border bg-card"><img src={pokemonball} className="size-8" alt="" aria-hidden="true" /></div>
        <div><p className="text-xs text-muted-foreground">{role === 'parent' && !studentId ? '孩子们的累计积分' : '累计积分'}</p>
          <p aria-label="累计积分" aria-live="polite" className="text-xl font-semibold tabular-nums">{hasData ? calendar.data?.stats.total_points ?? '—' : '—'} <span className="text-xs font-normal text-muted-foreground">分</span></p>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">{actions}</div>
    </header>
    <section aria-label="作业日历" className="overflow-hidden rounded-xl border bg-card">
      <div className="flex flex-wrap items-start justify-between gap-4 px-4 py-5 sm:px-6">
        <div><h1 className="text-xl font-semibold">{role === 'parent' ? '家庭作业' : '我的作业'}</h1><p className="mt-1 text-sm text-muted-foreground">选一天，翻开当天的作业本。</p></div>
        {role === 'parent' && <label className="flex items-center gap-2 text-sm text-muted-foreground">孩子
          <select aria-label="选择孩子" className="min-h-11 max-w-44 rounded-md border bg-input px-3 text-foreground" value={studentId} onChange={event => setStudentId(event.target.value)}>
            <option value="">全部孩子</option>{members.filter(member => member.role === 'student').map(member => <option key={member.user_id} value={member.user_id}>{member.name}</option>)}
          </select>
        </label>}
      </div>
      <div className="flex items-center justify-between gap-2 border-t px-3 py-3 sm:px-6">
        <h2 className="flex items-center gap-2 text-sm font-semibold sm:text-base"><CalendarDays className="size-4" aria-hidden="true" />{monthLabel(parseDate(`${month}-01`))}</h2>
        <div className="flex items-center gap-1">
          <Button className="min-h-11 min-w-11" size="icon" variant="ghost" aria-label="上个月" onClick={() => changeMonth(-1)}><ChevronLeft className="size-4" /></Button>
          <Button className="min-h-11" size="sm" variant="ghost" onClick={jumpToday}>今天</Button>
          <Button className="min-h-11 min-w-11" size="icon" variant="ghost" aria-label="下个月" disabled={calendarMonth(nextMonth(1)).end_date > maxDate} onClick={() => changeMonth(1)}><ChevronRight className="size-4" /></Button>
        </div>
      </div>
      <div className="grid grid-cols-7 border-t" aria-label="选择作业日期">
        {weekdays.map(day => <span key={day} className="py-2 text-center text-xs text-muted-foreground">{day}</span>)}
        {range.cells.map((date, index) => {
          if (!date) return <div key={`empty-${index}`} className="border-t bg-[var(--color-bg-subtle)]" />;
          const day = days.get(date);
          const count = hasData ? day?.task_count ?? 0 : 0;
          return <button key={date} type="button" aria-label={`${date}${count ? `，${count}项作业，已完成${day?.completed_count ?? 0}项` : ''}`} aria-pressed={date === selectedDate} aria-current={date === today ? 'date' : undefined}
            onClick={() => setSelectedDate(date)} className={cn('relative flex min-h-[60px] min-w-0 flex-col items-center justify-start gap-1 border-t py-2 transition-colors focus-visible:z-10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring sm:min-h-[72px]', date === selectedDate ? 'bg-[var(--color-bg-tool-card)]' : 'hover:bg-[var(--color-bg-hover)]')}>
            <span className={cn('flex size-7 items-center justify-center rounded-full text-sm tabular-nums', date === selectedDate && 'bg-[var(--color-btn-primary-bg)] text-[var(--color-btn-primary-text)]', date === today && date !== selectedDate && 'font-bold ring-1 ring-border')}>{Number(date.slice(-2))}</span>
            {count > 0 && <HomeworkDots tasks={day?.tasks ?? []} dictionaries={dictionaries} />}
          </button>;
        })}
      </div>
    </section>
    <section aria-label="当天作业本" aria-busy={calendar.isLoading} className="overflow-hidden rounded-xl border bg-card">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-5 sm:px-6">
        <div><p className="text-xs text-muted-foreground">作业记录 · {selectedDate}</p><h2 className="mt-1 text-lg font-semibold">{dateLabel(parseDate(selectedDate))}</h2></div>
        {hasData && <p className="text-sm tabular-nums text-muted-foreground">已完成 {selected?.completed_count ?? 0} / {selected?.task_count ?? 0}</p>}
      </div>
      {calendar.isError ? <div className="p-6"><p role="alert" className="text-sm">作业日历加载失败，请重试。</p><Button variant="outline" className="mt-3" onClick={() => void calendar.refetch()}>重试</Button></div>
        : calendar.isLoading || !calendar.data ? <p role="status" className="p-6 text-sm text-muted-foreground">正在加载作业…</p>
          : subjects.map(subject => {
            const subjectTasks = tasks.filter(task => (task.subject_code ?? 'other') === subject.code);
            return <section key={subject.code} aria-label={`${subject.name}作业`} className="grid border-b last:border-b-0 sm:grid-cols-[112px_minmax(0,1fr)]">
              <div className="flex items-center justify-between gap-2 bg-[var(--color-bg-subtle)] px-4 py-4 sm:flex-col sm:items-start sm:justify-start sm:border-r sm:px-6 sm:py-6">
                <h3 className="text-base font-semibold">{subject.name}</h3><span className="text-xs tabular-nums text-muted-foreground">{subjectTasks.length} 项</span>
              </div>
              <div className="min-w-0 px-4 sm:px-6">{subjectTasks.length ? renderTasks(subjectTasks) : <p className="py-6 text-sm text-muted-foreground">今日未布置</p>}</div>
            </section>;
          })}
      <p className="border-t px-4 py-3 text-xs text-muted-foreground sm:px-6">每完成一项作业获得 1 分 · 打卡即完成，家长可随后反馈。</p>
    </section>
  </>;
}
