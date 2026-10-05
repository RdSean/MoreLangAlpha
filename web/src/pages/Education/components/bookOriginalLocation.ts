export function firstJsonPage(nodes: readonly { page_range?: unknown }[]): number | undefined {
  const pages = nodes.flatMap((node) => {
    const range = node.page_range;
    if (!range || typeof range !== 'object' || !('start' in range) || !('label' in range)) return [];
    if (typeof range.label !== 'string' || !/^PDF(?:\b|页)/i.test(range.label.trim())) return [];
    return typeof range.start === 'number' && Number.isSafeInteger(range.start) && range.start > 0 ? [range.start] : [];
  });
  return pages.length ? Math.min(...pages) : undefined;
}
