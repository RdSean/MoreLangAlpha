import { z } from 'zod';

/**
 * Per-widget Zod schemas applied at the prefs-load boundary
 * (`migrations.ts → sanitizeConfig`). Per-field `.catch()` recovers
 * individual bad values; whole-config failure falls back to `defaultConfig`.
 *
 * Centralizing schemas in one file keeps the contract visible: schema
 * changes here are intentional, not buried in every widget file.
 *
 * Upstream carried thirty of these, one per finance/TradingView widget. This
 * branch registers the finance-free set only, so the rest were dropped with
 * their widgets — the generic recovery behaviour they exercised is covered by
 * fixtures in `__tests__/migrations.test.ts`.
 *
 * Enum tuples are exported `as const` so settings dialogs can derive their
 * dropdown options from the same source of truth and never drift from the
 * schema (Zod v4's `.options` is hidden after `.catch()` is applied — keep
 * the const around).
 */

const intInRange = (def: number, min: number, max: number) =>
  z.number().int().min(min).max(max).catch(def);

export const AutomationsConfigSchema = z.object({
  limit: intInRange(8, 1, 100).optional().catch(8),
});

export const WorkspacePickerConfigSchema = z.object({
  limit: intInRange(12, 1, 100).optional().catch(12),
});

export const RecentThreadsConfigSchema = z.object({
  // 'all' | 'current' | <workspace UUID> — accept any non-empty string.
  workspaceId: z.string().min(1).optional().catch('all'),
  limit: intInRange(15, 1, 100).optional().catch(15),
});

export const ConversationConfigSchema = z.object({}).catch({});

export const HOMEWORK_CALENDAR_WINDOWS = ['1w', '2w', '1m'] as const;
export const HomeworkCalendarConfigSchema = z.object({
  window: z.enum(HOMEWORK_CALENDAR_WINDOWS).optional().catch('2w'),
  showCompleted: z.boolean().optional().catch(false),
});
