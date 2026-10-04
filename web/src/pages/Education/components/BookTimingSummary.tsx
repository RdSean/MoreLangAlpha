import { useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import {
  BOOK_PHASE_LABELS,
  formatBookDuration,
  type BookTimingProjection,
} from './bookTimingProjection';

export function BookTimingSummary({
  timing,
}: {
  timing: BookTimingProjection;
}) {
  useTranslation();
  const [expanded, setExpanded] = useState(false);
  return (
    <section className="book-timing-summary" aria-label="处理计时">
      <dl className="flex flex-wrap gap-x-8 gap-y-3 text-sm">
        <div>
          <dt className="text-xs text-muted-foreground">本轮总历时</dt>
          <dd className="mt-1 tabular-nums">
            {formatBookDuration(timing.roundMs)}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">
            当前处理项{timing.attempt ? ` · 第 ${timing.attempt} 次尝试` : ''}
          </dt>
          <dd className="mt-1 tabular-nums">
            {formatBookDuration(timing.attemptMs)}
          </dd>
        </div>
      </dl>
      {timing.status === 'partial' && (
        <p className="mt-2 text-xs text-muted-foreground">部分计时未记录</p>
      )}
      <button
        type="button"
        className="mt-2 flex min-h-11 items-center gap-2 text-xs text-muted-foreground"
        aria-expanded={expanded}
        onClick={() => setExpanded(!expanded)}
      >
        <ChevronDown
          className={`size-4 ${expanded ? '' : '-rotate-90'}`}
          aria-hidden="true"
        />
        服务区间
      </button>
      {expanded && (
        <dl className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-2 text-xs">
          {timing.phases.map((phase) => (
            <div key={phase.phase} className="contents">
              <dt>
                {BOOK_PHASE_LABELS[phase.phase]}
                {phase.active ? ' · 进行中' : ''}
              </dt>
              <dd className="tabular-nums">{formatBookDuration(phase.ms)}</dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}
