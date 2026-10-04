import { useEffect, useRef, useState } from 'react';
import { loadQuotePool, type WaitingQuote } from '../quotePool';
import type { BookActivityEvent, BookJob, BookJobItem } from '../types';
import { isTerminalBookJobStatus } from './bookActivityProjection';

export interface BookLiveActivityProjection {
  active: boolean;
  recentAt: number | null;
  recentKind: string;
  quote: WaitingQuote | null;
}

export function useBookLiveActivity(
  job: BookJob | undefined,
  item: BookJobItem | null | undefined,
  events: readonly BookActivityEvent[],
  connected: boolean,
  liveAfterSeq: number | null | undefined = job?.high_water_seq,
): BookLiveActivityProjection {
  const [visible, setVisible] = useState(document.visibilityState !== 'hidden');
  const [recentAt, setRecentAt] = useState<number | null>(null);
  const [recentKind, setRecentKind] = useState('工具活动');
  const [quote, setQuote] = useState<WaitingQuote | null>(null);
  const [requested, setRequested] = useState<number | null>(null);
  const attemptedSeq = useRef<number | null>(null);
  const loading = useRef(false);
  const loadFailed = useRef(false);
  const lastProcessed = useRef(job?.high_water_seq ?? 0);
  const pool = useRef<WaitingQuote[]>([]);
  const nextQuote = useRef(0);
  const lastRotation = useRef(0);
  const identity = `${job?.job_id}:${item?.item_id}:${item?.attempt}`;
  const active = Boolean(
    job && item && connected && visible && !isTerminalBookJobStatus(job.status),
  );

  useEffect(() => {
    const update = () => setVisible(document.visibilityState !== 'hidden');
    document.addEventListener('visibilitychange', update);
    return () => document.removeEventListener('visibilitychange', update);
  }, []);
  useEffect(() => {
    lastProcessed.current = job?.high_water_seq ?? 0;
    attemptedSeq.current = null;
    setRequested(null);
    setRecentAt(null);
    setQuote(null);
    loading.current = false;
    loadFailed.current = false;
    // The small static pool survives item and layout changes; only event identity resets.
  }, [identity]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const boundary = Math.max(lastProcessed.current, liveAfterSeq ?? 0);
    lastProcessed.current = Math.max(
      boundary,
      ...events.map((entry) => entry.seq),
    );
    if (!active || !job || !item || liveAfterSeq == null) return;
    const now = Date.now();
    const attemptStart = Date.parse(item.started_at ?? '');
    const latest = events
      .filter((entry) => {
        const created = Date.parse(entry.created_at);
        return (
          entry.seq > boundary &&
          entry.job_id === job.job_id &&
          entry.item_id === item.item_id &&
          (entry.kind === 'tool' ||
            (entry.kind === 'resource' &&
              entry.metadata.origin === 'service')) &&
          created >= attemptStart &&
          now - created <= 30_000 &&
          created - now <= 5_000
        );
      })
      .sort((left, right) => right.seq - left.seq)[0];
    if (!latest) return;
    setRecentAt(Date.parse(latest.created_at));
    setRecentKind(latest.kind === 'resource' ? '存储确认' : '工具活动');
    if (!pool.current.length && !loading.current && !loadFailed.current)
      setRequested(latest.seq);
    if (!pool.current.length || now - lastRotation.current < 5000) return;
    setQuote(pool.current[nextQuote.current % pool.current.length]);
    nextQuote.current += 1;
    lastRotation.current = now;
  }, [active, events, item, job, liveAfterSeq]);

  useEffect(() => {
    if (
      requested === null ||
      requested === attemptedSeq.current ||
      !active ||
      pool.current.length
    )
      return;
    attemptedSeq.current = requested;
    loading.current = true;
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 10000);
    void loadQuotePool(controller.signal)
      .then((quotes) => {
        if (controller.signal.aborted) return;
        pool.current = quotes;
        setQuote(quotes[0]);
        nextQuote.current = 1;
        lastRotation.current = Date.now();
      })
      .catch(() => {
        if (!controller.signal.aborted) loadFailed.current = true;
      })
      .finally(() => window.clearTimeout(timeout));
    return () => {
      controller.abort();
      loading.current = false;
      window.clearTimeout(timeout);
    };
  }, [requested, active, identity]);

  return { active, recentAt, recentKind, quote };
}
