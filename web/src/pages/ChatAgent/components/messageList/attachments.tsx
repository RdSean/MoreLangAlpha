import React, { useState } from 'react';
import { FileText, ImageIcon } from 'lucide-react';
import { type WidgetContextPreviewShape } from '@/components/ui/WidgetContextPreview';
import { WidgetContextDeck } from '@/components/ui/WidgetContextDeck';

/* --- Attachment helpers --- */
const formatFileSize = (bytes: number | null | undefined): string => {
  if (!bytes || bytes === 0) return '';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
};

// --- AttachmentCard ---

export interface AttachmentData {
  name?: string;
  type?: string;
  size?: number;
  preview?: string;
  dataUrl?: string;
  url?: string;
  [key: string]: unknown;
}

interface AttachmentCardProps {
  attachment: AttachmentData;
}

/** Local alias for the preview shape — keeps inline-deck internals decoupled from the import path. */
export type WidgetChipShape = WidgetContextPreviewShape;

/**
 * Static read-only deck rendered below the user message bubble. Reuses the
 * shared `WidgetContextDeck` — no eyebrow, no remove buttons, just the
 * stacked cards with click-to-fan / click-to-preview semantics. Width is
 * pinned at 320px since the user-message column has a `max-w-[80%]`
 * constraint that would otherwise collapse absolute-positioned cards.
 */
export function InlineWidgetDeck({ snapshots }: { snapshots: WidgetChipShape[] }) {
  const [fanned, setFanned] = useState(false);
  return (
    <WidgetContextDeck
      snapshots={snapshots}
      fanned={fanned}
      onToggleFan={() => setFanned((p) => !p)}
      onCollapse={() => setFanned(false)}
      compactCardGrid
      style={{
        width: 320,
        borderBottom: 'none',
        marginBottom: 0,
        paddingBottom: 0,
      }}
    />
  );
}

/**
 * AttachmentCard -- 96x96 preview card matching FilePreviewCard styling.
 * Handles both live attachments (with preview/dataUrl) and history
 * attachments (name/type/size only).
 */
export function AttachmentCard({ attachment }: AttachmentCardProps): React.ReactElement {
  const att = attachment;
  const isImage = att.type?.startsWith('image/') || att.type === 'image';
  const hasPreview = att.dataUrl || att.url || att.preview;
  const ext = att.name?.split('.').pop() || '';

  if (isImage && hasPreview) {
    return (
      <div className="relative group flex-shrink-0 w-24 h-24 rounded-xl overflow-hidden" style={{ border: '1px solid var(--color-border-muted)', background: 'var(--color-bg-input)' }}>
        <img src={att.dataUrl || att.url || att.preview} alt={att.name} className="w-full h-full object-cover" />
        <div className="absolute inset-0 bg-black/20" />
      </div>
    );
  }

  if (isImage && !hasPreview) {
    // History image -- no thumbnail available, show placeholder
    return (
      <div className="relative flex-shrink-0 w-24 h-24 rounded-xl overflow-hidden" style={{ border: '1px solid var(--color-border-muted)', background: 'var(--color-bg-input)' }}>
        <div className="w-full h-full p-3 flex flex-col items-center justify-center gap-2">
          <ImageIcon className="w-6 h-6" style={{ color: 'var(--color-icon-muted)' }} />
          <p className="text-[0.625rem] truncate w-full text-center" style={{ color: 'var(--color-text-tertiary)' }}>{att.name}</p>
        </div>
      </div>
    );
  }

  // PDF / generic file card
  return (
    <div className="relative flex-shrink-0 w-24 h-24 rounded-xl overflow-hidden" style={{ border: '1px solid var(--color-border-muted)', background: 'var(--color-bg-input)' }}>
      <div className="w-full h-full p-3 flex flex-col justify-between">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded" style={{ background: 'var(--color-border-muted)' }}>
            <FileText className="w-4 h-4" style={{ color: 'var(--color-text-tertiary)' }} />
          </div>
          <span className="text-[0.625rem] font-medium uppercase tracking-wider truncate" style={{ color: 'var(--color-text-tertiary)' }}>
            {ext}
          </span>
        </div>
        <div className="space-y-0.5">
          <p className="text-xs font-medium truncate" style={{ color: 'var(--color-text-muted)' }} title={att.name}>{att.name}</p>
          {(att.size ?? 0) > 0 && (
            <p className="text-[0.625rem]" style={{ color: 'var(--color-text-tertiary)' }}>{formatFileSize(att.size)}</p>
          )}
        </div>
      </div>
    </div>
  );
}
