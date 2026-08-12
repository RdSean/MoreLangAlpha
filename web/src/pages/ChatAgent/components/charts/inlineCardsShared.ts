export const CARD_BG = 'var(--color-bg-tool-card)';
export const CARD_BORDER = 'var(--color-border-muted)';

export interface InlineCardProps {
  artifact: Record<string, unknown> | null | undefined;
  onClick?: () => void;
}
