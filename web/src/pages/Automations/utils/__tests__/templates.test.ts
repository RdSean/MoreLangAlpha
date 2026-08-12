import { describe, expect, it } from 'vitest';
import {
  applyTemplate,
  automationToFormState,
  AUTOMATION_TEMPLATES,
  formStateToPayload,
  INITIAL_FORM,
} from '../templates';
import type { Automation } from '@/types/automation';

describe('generic automation templates', () => {
  it('defines the four supported generic templates', () => {
    expect(AUTOMATION_TEMPLATES.map((template) => template.id)).toEqual([
      'custom',
      'daily_summary',
      'weekly_review',
      'one_time_task',
    ]);
  });

  it('applies the daily workspace summary schedule', () => {
    const form = applyTemplate('daily_summary');

    expect(form.trigger_type).toBe('cron');
    expect(form.cron_expression).toBe('0 8 * * 1-5');
    expect(form.agent_mode).toBe('flash');
  });

  it('returns the initial form for a custom automation', () => {
    expect(applyTemplate('custom')).toEqual(INITIAL_FORM);
  });
});

describe('generic automation payloads', () => {
  it('removes the one-time timestamp from a recurring payload', () => {
    const payload = formStateToPayload({
      ...INITIAL_FORM,
      trigger_type: 'cron',
      cron_expression: '0 9 * * *',
      next_run_at: '2026-01-01T09:00',
    });

    expect(payload.cron_expression).toBe('0 9 * * *');
    expect(payload.next_run_at).toBeUndefined();
  });

  it('converts a one-time timestamp to ISO format', () => {
    const payload = formStateToPayload({
      ...INITIAL_FORM,
      trigger_type: 'once',
      next_run_at: '2026-03-20T14:30',
    });

    expect(payload.next_run_at).toBe(new Date('2026-03-20T14:30').toISOString());
    expect(payload.cron_expression).toBeUndefined();
  });

  it('keeps a workspace only for PTC automations', () => {
    const flashPayload = formStateToPayload({ ...INITIAL_FORM, workspace_id: 'ws-123' });
    const ptcPayload = formStateToPayload({ ...INITIAL_FORM, agent_mode: 'ptc', workspace_id: 'ws-123' });

    expect(flashPayload.workspace_id).toBeUndefined();
    expect(ptcPayload.workspace_id).toBe('ws-123');
  });
});

describe('automationToFormState', () => {
  it('maps a recurring automation into the generic form', () => {
    const automation: Automation = {
      id: '123',
      automation_id: '123',
      name: 'Weekly review',
      status: 'active',
      trigger_type: 'cron',
      cron_expression: '0 18 * * 5',
      timezone: 'Asia/Tokyo',
      agent_mode: 'ptc',
      workspace_id: 'ws-123',
    };

    expect(automationToFormState(automation)).toMatchObject({
      name: 'Weekly review',
      trigger_type: 'cron',
      cron_expression: '0 18 * * 5',
      timezone: 'Asia/Tokyo',
      agent_mode: 'ptc',
      workspace_id: 'ws-123',
    });
  });
});
