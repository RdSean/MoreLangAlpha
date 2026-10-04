import { useEffect, useMemo, useState } from 'react';
import type { BookJob } from '../types';
import { isTerminalBookJobStatus } from './bookActivityProjection';

export function useBookElapsedTime(
  job: BookJob | undefined,
  connected: boolean,
): number | null {
  const [visible, setVisible] = useState(document.visibilityState !== 'hidden');
  const [, tick] = useState(0);
  const identity = `${job?.job_id}:${job?.request_round}:${job?.items.map((item) => `${item.item_id}:${item.attempt}`).join(',')}`;
  const live = Boolean(
    job && connected && visible && !isTerminalBookJobStatus(job.status),
  );
  const baseline = useMemo(
    () => ({
      server: Date.parse(job?.server_now ?? ''),
      monotonic: performance.now(),
      identity,
      live,
    }),
    [identity, job?.server_now, live],
  );

  useEffect(() => {
    const update = () => setVisible(document.visibilityState !== 'hidden');
    document.addEventListener('visibilitychange', update);
    return () => document.removeEventListener('visibilitychange', update);
  }, []);
  useEffect(() => {
    if (!live || !Number.isFinite(baseline.server)) return;
    const timer = window.setInterval(() => tick((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, [live, baseline]);

  return Number.isFinite(baseline.server)
    ? baseline.server +
        (live ? Math.max(0, performance.now() - baseline.monotonic) : 0)
    : null;
}
