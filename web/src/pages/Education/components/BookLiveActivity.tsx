import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { createDateFormatter } from '@/lib/format';
import { loadQuotePool, type WaitingQuote } from '../quotePool';
import type { BookActivityEvent, BookJob, BookJobItem } from '../types';

interface Props {
  job: BookJob;
  item: BookJobItem;
  events: readonly BookActivityEvent[];
  connected: boolean;
  liveAfterSeq?: number | null;
}

export function BookLiveActivity({ job, item, events, connected, liveAfterSeq = job.high_water_seq }: Props) {
  useTranslation();
  const [visible, setVisible] = useState(() => document.visibilityState !== 'hidden');
  const [recentAt, setRecentAt] = useState<number | null>(null);
  const [quote, setQuote] = useState<WaitingQuote | null>(null);
  const [requested, setRequested] = useState<number | null>(null);
  const attemptedSeq = useRef<number | null>(null);
  const loading = useRef(false);
  const loadFailed = useRef(false);
  const lastProcessed = useRef(job.high_water_seq);
  const pool = useRef<WaitingQuote[]>([]);
  const nextQuote = useRef(0);
  const lastRotation = useRef(0);
  const active = connected && visible;

  useEffect(() => {
    const update = () => setVisible(document.visibilityState !== 'hidden');
    document.addEventListener('visibilitychange', update);
    return () => document.removeEventListener('visibilitychange', update);
  }, []);

  useEffect(() => {
    const boundary = Math.max(lastProcessed.current, liveAfterSeq ?? 0);
    lastProcessed.current = Math.max(boundary, ...events.map((entry) => entry.seq));
    if (!active || liveAfterSeq === null) return;
    const now = Date.now();
    const attemptStart = Date.parse(item.started_at ?? '');
    const latest = events.filter((entry) => {
      const created = Date.parse(entry.created_at);
      return entry.seq > boundary && entry.job_id === job.job_id && entry.item_id === item.item_id
        && entry.kind === 'tool' && created >= attemptStart
        && now - created <= 30_000 && created - now <= 5_000;
    }).sort((left, right) => right.seq - left.seq)[0];
    if (!latest) return;
    setRecentAt(Date.parse(latest.created_at));
    if (!pool.current.length && !loading.current && !loadFailed.current) setRequested(latest.seq);
    if (!pool.current.length || now - lastRotation.current < 15_000) return;
    setQuote(pool.current[nextQuote.current % pool.current.length]);
    nextQuote.current += 1;
    lastRotation.current = now;
  }, [active, events, item.item_id, item.started_at, job.job_id, liveAfterSeq]);

  useEffect(() => {
    if (requested === null || requested === attemptedSeq.current || !active || pool.current.length) return;
    attemptedSeq.current = requested;
    loading.current = true;
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 10_000);
    void loadQuotePool(controller.signal).then((quotes) => {
      if (controller.signal.aborted) return;
      pool.current = quotes;
      setQuote(quotes[0]);
      nextQuote.current = 1;
      lastRotation.current = Date.now();
    }).catch(() => {
      if (!controller.signal.aborted) loadFailed.current = true;
    }).finally(() => window.clearTimeout(timeout));
    return () => {
      controller.abort();
      loading.current = false;
      window.clearTimeout(timeout);
    };
  }, [requested, active]);

  const formatTime = createDateFormatter({ hour: '2-digit', minute: '2-digit', second: '2-digit' });
  return (
    <div className="mt-2 text-xs text-muted-foreground" aria-live="off">
      <p className="flex h-4 flex-wrap gap-x-2">{active && recentAt !== null && <><span>最近活动</span><time dateTime={new Date(recentAt).toISOString()} className="tabular-nums">{formatTime(recentAt)}</time></>}</p>
      <figure className="m-0 mt-2 h-28 overflow-y-auto" aria-label="等待时的名句" aria-live="off">
        {active && quote && <>
          <blockquote className="m-0 break-words text-sm leading-6">{quote.contents}</blockquote>
          <figcaption className="mt-1 break-words leading-5">{quote.source}</figcaption>
        </>}
      </figure>
    </div>
  );
}
