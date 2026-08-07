import React, { useState } from 'react';
import { InlineAutomationCard } from './InlineAutomationCards';
import { InlinePreviewCard } from './InlinePreviewCard';

export const INLINE_ARTIFACT_TOOLS = new Set([
  'check_automations',
  'create_automation',
  'GetPreviewUrl',
]);

/** Build a Google favicon service URL for a web result. */
export function googleFaviconUrl(domain: string): string {
  return domain ? `https://www.google.com/s2/favicons?domain=${domain}&sz=32` : '';
}

/** Favicon image with a compact text fallback for search results. */
export function FaviconImg({ src, domain, size = 14 }: { src: string; domain: string; size?: number }): React.ReactElement {
  const [failed, setFailed] = useState(false);

  if (failed || !src) {
    return (
      <span
        style={{
          width: size,
          height: size,
          borderRadius: 2,
          backgroundColor: 'var(--color-bg-surface)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: Math.round(size * 0.64),
          fontWeight: 600,
          color: 'var(--color-text-tertiary)',
          flexShrink: 0,
        }}
      >
        {(domain || '?')[0].toUpperCase()}
      </span>
    );
  }

  return <img src={src} alt="" width={size} height={size} style={{ borderRadius: 2, flexShrink: 0 }} onError={() => setFailed(true)} />;
}

export const INLINE_ARTIFACT_MAP: Record<
  string,
  React.ComponentType<{ artifact: Record<string, unknown>; onClick?: () => void }>
> = {
  automations: InlineAutomationCard,
  preview_url: InlinePreviewCard,
};
