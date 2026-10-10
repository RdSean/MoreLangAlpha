import { useRef, useState, type ChangeEvent } from 'react';
import { CalendarDays, FileUp, RefreshCw, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { createDateFormatter } from '@/lib/format';
import { useFamilyCalendarSources, useImportFamilyCalendar, useRemoveFamilyCalendar } from './calendarQueries';
import type { FamilyCalendarSource } from './calendarApi';

function errorMessage(error: unknown, fallback: string): string {
  if (typeof error === 'object' && error !== null && 'response' in error) {
    const response = error.response;
    if (typeof response === 'object' && response !== null && 'data' in response) {
      const data = response.data;
      if (typeof data === 'object' && data !== null && 'detail' in data && typeof data.detail === 'string') return data.detail;
    }
  }
  return fallback;
}

const updatedLabel = createDateFormatter({ month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });

export default function FamilyCalendarSettings() {
  useTranslation();
  const sources = useFamilyCalendarSources();
  const upload = useImportFamilyCalendar();
  const remove = useRemoveFamilyCalendar();
  const input = useRef<HTMLInputElement>(null);
  const target = useRef<string | undefined>(undefined);
  const [removing, setRemoving] = useState<FamilyCalendarSource | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const busy = upload.isPending || remove.isPending;

  const chooseFile = (sourceId?: string) => {
    target.current = sourceId;
    input.current?.click();
  };
  const importFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    setError(''); setNotice('');
    if (!file.name.toLowerCase().endsWith('.ics') || file.size > 1024 * 1024) {
      setError('请选择不超过 1 MB 的 .ics 文件。'); return;
    }
    try {
      const source = await upload.mutateAsync({ file, sourceId: target.current });
      setNotice(`已保存「${source.name}」，${source.event_count} 项日程。`);
    } catch (reason) { setError(errorMessage(reason, '日历导入失败，请稍后重试。')); }
  };
  const confirmRemoval = async () => {
    if (!removing) return;
    setError(''); setNotice('');
    try {
      await remove.mutateAsync(removing.source_id);
      setNotice(`已移除「${removing.name}」。`);
      setRemoving(null);
    } catch (reason) { setError(errorMessage(reason, '移除失败，请稍后重试。')); setRemoving(null); }
  };

  return <section aria-labelledby="family-calendar-heading" className="border-t pt-6">
    <header className="flex flex-wrap items-center justify-between gap-3">
      <div><h3 id="family-calendar-heading" className="flex items-center gap-2 text-base font-semibold"><CalendarDays className="size-4" aria-hidden="true" />家庭日历</h3><p className="mt-1 text-xs text-muted-foreground">全家共享</p></div>
      <Button variant="outline" className="min-h-11" disabled={busy} onClick={() => chooseFile()}><FileUp className="mr-2 size-4" aria-hidden="true" />{upload.isPending ? '正在导入…' : '导入 ICS'}</Button>
      <input ref={input} aria-label="选择 ICS 文件" type="file" accept=".ics,text/calendar" className="sr-only" tabIndex={-1} disabled={busy} onChange={event => void importFile(event)} />
    </header>
    {error && <p role="alert" className="mt-3 text-sm text-[var(--color-loss)]">{error}</p>}
    {notice && <p role="status" className="mt-3 text-sm">{notice}</p>}
    {sources.isLoading ? <p className="py-5 text-sm text-muted-foreground">正在加载家庭日历…</p>
      : sources.isError ? <div className="py-5"><p role="alert" className="text-sm">家庭日历加载失败。</p><Button variant="outline" size="sm" className="mt-2" onClick={() => void sources.refetch()}>重试</Button></div>
        : !sources.data?.length ? <p className="py-5 text-sm text-muted-foreground">暂无家庭日历</p>
          : <div className="mt-4 divide-y border-y">{sources.data.map(source => <article key={source.source_id} className="flex flex-wrap items-center justify-between gap-3 py-4">
            <div className="min-w-0 flex-1"><h4 className="break-words text-sm font-medium">{source.name}</h4><p className="mt-1 break-all text-xs text-muted-foreground">{source.filename}</p><p className="mt-1 text-xs text-muted-foreground">{source.event_count} 项日程 · 更新于 {updatedLabel(new Date(source.updated_at))}</p></div>
            <div className="flex shrink-0 gap-1"><Button size="icon" variant="ghost" className="size-11" aria-label={`更新${source.name}`} title={`更新${source.name}`} disabled={busy} onClick={() => chooseFile(source.source_id)}><RefreshCw className="size-4" /></Button><Button size="icon" variant="ghost" className="size-11" aria-label={`移除${source.name}`} title={`移除${source.name}`} disabled={busy} onClick={() => setRemoving(source)}><Trash2 className="size-4" /></Button></div>
          </article>)}</div>}
    <Dialog open={Boolean(removing)} onOpenChange={open => { if (!open && !remove.isPending) setRemoving(null); }}>
      <DialogContent variant="centered" className="max-w-md"><DialogHeader><DialogTitle>移除家庭日历</DialogTitle><DialogDescription>移除「{removing?.name}」及其全部共享日程？</DialogDescription></DialogHeader><DialogFooter><Button variant="outline" disabled={remove.isPending} onClick={() => setRemoving(null)}>取消</Button><Button disabled={remove.isPending} onClick={() => void confirmRemoval()}>{remove.isPending ? '正在移除…' : '确认移除'}</Button></DialogFooter></DialogContent>
    </Dialog>
  </section>;
}
