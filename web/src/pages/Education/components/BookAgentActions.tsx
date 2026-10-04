import { useState } from 'react';
import { Circle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { createDateFormatter } from '@/lib/format';
import { Button } from '@/components/ui/button';
import type { BookActivityEvent } from '../types';

export function BookAgentActions({
  actions,
}: {
  actions: readonly BookActivityEvent[];
}) {
  useTranslation();
  const [limit, setLimit] = useState(30);
  const formatTime = createDateFormatter({
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
  if (!actions.length) return null;
  return (
    <div className="mt-3 border-l pl-4">
      {actions.length > limit && (
        <Button
          variant="ghost"
          className="min-h-11 text-xs"
          onClick={() => setLimit(limit + 30)}
        >
          更早的 Agent 上报
        </Button>
      )}
      <ol className="space-y-3" aria-label="Agent 上报记录">
        {actions.slice(-limit).map((entry) => (
          <li key={entry.seq} className="flex items-start gap-2 text-sm">
            <Circle
              className="mt-1 size-3 shrink-0 text-muted-foreground"
              aria-hidden="true"
            />
            <div className="min-w-0">
              <p className="break-words text-muted-foreground">
                {entry.message}
              </p>
              <time
                className="text-xs tabular-nums text-muted-foreground"
                dateTime={entry.created_at}
              >
                {formatTime(Date.parse(entry.created_at))}
              </time>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
