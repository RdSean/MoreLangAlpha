import i18n from '@/i18n';
import type {
  BookActivityEvent,
  BookJobItem,
  FrozenBookSource,
} from '../types';

export function bookActivityText(entry: BookActivityEvent): string {
  if (
    entry.status === 'succeeded' &&
    ['material', 'structure', 'supplementary', 'item', 'job'].includes(
      entry.kind,
    )
  )
    return i18n.t(`bookProcessing.terminal.${entry.kind}`);
  if (
    ['failed', 'cancelled', 'not_run'].includes(entry.status) &&
    entry.kind !== 'progress' &&
    entry.kind !== 'tool'
  )
    return i18n.t(`bookProcessing.status.${entry.status}`);
  if (entry.kind === 'tool') {
    const match = /^(Running|Finished) (.+)$|^(.+) failed$/.exec(entry.message);
    if (match && i18n.language.startsWith('zh'))
      return match[3]
        ? `${match[3]} 执行失败`
        : `${match[2]} ${match[1] === 'Running' ? '执行中' : '已结束'}`;
  }
  if (!i18n.language.startsWith('zh')) {
    const action = entry.metadata.action;
    const stage = entry.metadata.stage;
    for (const [group, value] of [
      ['action', action],
      ['stage', stage],
    ]) {
      const key = `bookProcessing.${group}.${value}`;
      if (typeof value === 'string' && i18n.exists(key)) return i18n.t(key);
    }
  }
  return entry.message;
}

export function bookItemTitle(item: BookJobItem): string {
  if (item.kind === 'structure') return i18n.t('bookProcessing.structure');
  if (item.kind === 'supplementary')
    return i18n.t('bookProcessing.supplementary');
  return item.knowledge_point_title?.trim()
    ? i18n.t('bookProcessing.kpTitle', { title: item.knowledge_point_title })
    : i18n.t('bookProcessing.itemTitle', { position: item.position });
}

export function bookSourceInfo(
  source?: Pick<
    FrozenBookSource,
    'filename' | 'media_type' | 'page_count'
  > | null,
): string {
  if (!source) return '';
  const extension = source.filename.split('.').at(-1)?.toUpperCase();
  const type =
    source.media_type === 'application/pdf'
      ? 'PDF'
      : extension && extension !== source.filename.toUpperCase()
        ? extension
        : source.media_type;
  return [
    type,
    source.page_count && source.page_count > 0
      ? i18n.t('bookProcessing.pages', { count: source.page_count })
      : null,
  ]
    .filter(Boolean)
    .join(' · ');
}
