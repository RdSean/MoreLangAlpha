import { BookOpen } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useTranslation } from 'react-i18next';
import type {
  BookActivityEvent,
  BookJob,
  KnowledgePointProjection,
} from '../types';
import {
  formatBookDuration,
  hasMatchingBookTiming,
} from './bookTimingProjection';

export function BookMaterialDeliveryList({
  job,
  knowledgePoints = [],
  onOpenMaterial,
}: {
  job: BookJob;
  knowledgePoints?: readonly KnowledgePointProjection[];
  agentActions?: readonly BookActivityEvent[];
  onOpenMaterial?: (skillKpId: string) => void;
}) {
  const { t } = useTranslation();
  const items = job.items.filter((item) => item.kind === 'material');
  const pointFor = (item: BookJob['items'][number]) =>
    knowledgePoints.find(
      (point) =>
        point.knowledge_point_id === item.knowledge_point_id ||
        point.skill_kp_id === item.skill_kp_id,
    );
  // Keep a readable result available immediately, without expanding the batch.
  const submitted = items.find((item) => item.status === 'succeeded');
  const older = items.find(
    (item) => item.status !== 'succeeded' && pointFor(item)?.material_available,
  );
  const visible = [submitted, older].filter(
    (item): item is BookJob['items'][number] => Boolean(item),
  );
  if (!visible.length) return null;
  return (
    <section
      aria-label={t('bookProcessing.delivery')}
      className="book-material-delivery"
    >
      <ol>
        {visible.map((item) => {
          const point = pointFor(item);
          const skillId = item.skill_kp_id ?? point?.skill_kp_id;
          const title =
            item.knowledge_point_title?.trim() ||
            point?.title ||
            t('bookProcessing.itemTitle', { position: item.position });
          const isOlder = item.status !== 'succeeded';
          const command = t(
            isOlder
              ? 'bookProcessing.readOlder'
              : 'bookProcessing.readMaterial',
          );
          return (
            <li
              key={item.item_id}
              aria-label={title}
              className="flex min-w-0 items-center justify-between gap-3 py-1 text-xs"
            >
              <div className="min-w-0 text-muted-foreground">
                <p className="truncate" title={title}>
                  {title}
                </p>
                <p>
                  {t(
                    isOlder
                      ? `bookProcessing.status.${item.status}`
                      : 'bookProcessing.submitted',
                  )}{' '}
                  ·{' '}
                  {formatBookDuration(
                    hasMatchingBookTiming(job, item)
                      ? item.timing_summary!.total_ms
                      : null,
                  )}
                </p>
                {isOlder && <p>{t('bookProcessing.older')}</p>}
              </div>
              {skillId && onOpenMaterial && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="shrink-0"
                  aria-label={`${command}：${title}`}
                  onClick={() => onOpenMaterial(skillId)}
                >
                  <BookOpen className="mr-1.5 size-3.5" aria-hidden="true" />
                  {command}
                </Button>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
