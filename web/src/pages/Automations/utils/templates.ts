import { CalendarDays, Clock, Plus, Timer } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import type { Automation } from '@/types/automation';

export const COMMON_TIMEZONES = [
  'UTC',
  'America/New_York',
  'America/Chicago',
  'America/Los_Angeles',
  'Europe/London',
  'Europe/Paris',
  'Asia/Tokyo',
  'Asia/Shanghai',
  'Asia/Singapore',
  'Australia/Sydney',
];

function detectTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}

export interface FormState {
  name: string;
  description: string;
  trigger_type: 'cron' | 'once';
  cron_expression: string;
  timezone: string;
  next_run_at: string;
  agent_mode: string;
  workspace_id: string;
  instruction: string;
  thread_strategy: string;
  max_failures: number | string;
  delivery_method: string;
}

export const INITIAL_FORM: FormState = {
  name: '',
  description: '',
  trigger_type: 'cron',
  cron_expression: '',
  timezone: detectTimezone(),
  next_run_at: '',
  agent_mode: 'flash',
  workspace_id: '',
  instruction: '',
  thread_strategy: 'new',
  max_failures: 3,
  delivery_method: '',
};

export type TemplateId = 'custom' | 'daily_summary' | 'weekly_review' | 'one_time_task';

export interface AutomationTemplate {
  id: TemplateId;
  nameKey: string;
  descriptionKey: string;
  icon: LucideIcon;
  defaults: Partial<FormState>;
}

export const AUTOMATION_TEMPLATES: AutomationTemplate[] = [
  { id: 'custom', nameKey: 'automation.templateCustom', descriptionKey: 'automation.templateCustomDesc', icon: Plus, defaults: {} },
  {
    id: 'daily_summary',
    nameKey: 'automation.templateDailySummary',
    descriptionKey: 'automation.templateDailySummaryDesc',
    icon: Clock,
    defaults: {
      name: 'Daily workspace summary',
      trigger_type: 'cron',
      cron_expression: '0 8 * * 1-5',
      agent_mode: 'flash',
      instruction: 'Summarize the current workspace activity and identify the next useful actions.',
    },
  },
  {
    id: 'weekly_review',
    nameKey: 'automation.templateWeeklyReview',
    descriptionKey: 'automation.templateWeeklyReviewDesc',
    icon: CalendarDays,
    defaults: {
      name: 'Weekly workspace review',
      trigger_type: 'cron',
      cron_expression: '0 18 * * 5',
      agent_mode: 'ptc',
      instruction: 'Review the work completed this week, summarize progress, and prepare a concise plan for next week.',
    },
  },
  {
    id: 'one_time_task',
    nameKey: 'automation.templateOneTimeTask',
    descriptionKey: 'automation.templateOneTimeTaskDesc',
    icon: Timer,
    defaults: { name: 'One-time task', trigger_type: 'once', agent_mode: 'ptc' },
  },
];

export function applyTemplate(templateId: TemplateId): FormState {
  const template = AUTOMATION_TEMPLATES.find((item) => item.id === templateId);
  return { ...INITIAL_FORM, ...(template?.defaults ?? {}) };
}

export function automationToFormState(automation: Automation): FormState {
  return {
    name: automation.name || '',
    description: automation.description || '',
    trigger_type: automation.trigger_type === 'once' ? 'once' : 'cron',
    cron_expression: (automation.cron_expression as string) || '',
    timezone: (automation.timezone as string) || detectTimezone(),
    next_run_at: automation.next_run_at ? String(automation.next_run_at).slice(0, 16) : '',
    agent_mode: (automation.agent_mode as string) || 'flash',
    workspace_id: automation.workspace_id || '',
    instruction: (automation.instruction as string) || '',
    thread_strategy: (automation.thread_strategy as string) || 'new',
    max_failures: (automation.max_failures as number) ?? 3,
    delivery_method: automation.delivery_config?.methods?.[0] || '',
  };
}

export function formStateToPayload(form: FormState): Record<string, unknown> {
  const payload: Record<string, unknown> = { ...form };

  if (form.trigger_type === 'cron') {
    delete payload.next_run_at;
  } else {
    delete payload.cron_expression;
    if (payload.next_run_at) payload.next_run_at = new Date(String(payload.next_run_at)).toISOString();
  }

  if (payload.agent_mode !== 'ptc') delete payload.workspace_id;
  if (!payload.description) delete payload.description;
  payload.max_failures = parseInt(String(payload.max_failures), 10) || 3;
  payload.delivery_config = payload.delivery_method ? { methods: [payload.delivery_method] } : { methods: [] };
  delete payload.delivery_method;
  return payload;
}
