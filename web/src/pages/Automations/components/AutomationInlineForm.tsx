import React, { useState, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown } from 'lucide-react';
import { AnimatedTabs } from '@/components/ui/animated-tabs';
import {
  Select,
  SelectItem,
  SelectListBox,
  SelectPopover,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/aria-select';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { toast } from '@/components/ui/use-toast';
import CronScheduleBuilder from './CronScheduleBuilder';
import { useWorkspaces } from '@/hooks/useWorkspaces';
import {
  type FormState,
  COMMON_TIMEZONES,
  formStateToPayload,
} from '../utils/templates';

// ── Shared styles ──────────────────────────────────────────

const inputStyle = {
  backgroundColor: 'var(--color-bg-card)',
  borderColor: 'var(--color-border-default)',
};

const labelClass = 'form-label';

// ── Workspace type ─────────────────────────────────────────

interface WorkspaceOption {
  workspace_id: string;
  name: string;
}

// ── AutomationInlineForm ───────────────────────────────────

interface AutomationInlineFormProps {
  initialValues: FormState;
  isEdit: boolean;
  onSubmit: (payload: Record<string, unknown>) => void;
  onCancel: () => void;
  loading: boolean;
}

export default function AutomationInlineForm({
  initialValues,
  isEdit,
  onSubmit,
  onCancel,
  loading,
}: AutomationInlineFormProps) {
  const { t } = useTranslation();
  const [form, setForm] = useState<FormState>(initialValues);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const outerRef = useRef<HTMLDivElement>(null);
  const advancedRef = useRef<HTMLDivElement>(null);

  // Release overflow:hidden after expand animation so box-shadows (card shadow, focus rings) aren't clipped.
  // Re-apply overflow:hidden when any animation starts (collapse needs clipping).
  const releaseOverflow = (ref: React.RefObject<HTMLDivElement | null>) => ({
    onAnimationStart: () => { if (ref.current) ref.current.style.overflow = 'hidden'; },
    onAnimationComplete: () => { if (ref.current && ref.current.offsetHeight > 0) ref.current.style.overflow = 'visible'; },
  });

  const { data: wsData } = useWorkspaces({ limit: 100 });
  const workspaces = (wsData as { workspaces?: WorkspaceOption[] })?.workspaces ?? [];

  const set = (key: keyof FormState) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement> | string) =>
    setForm((f) => ({ ...f, [key]: typeof e === 'string' ? e : e.target.value }));

  const setSelection = (key: keyof FormState) => (k: React.Key | null) =>
    setForm((f) => ({ ...f, [key]: k == null ? '' : String(k) }));

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (form.agent_mode === 'ptc' && !form.workspace_id) {
      setAdvancedOpen(true);
      toast({ variant: 'destructive', description: t('automation.workspaceRequired') });
      return;
    }
    onSubmit(formStateToPayload(form));
  };

  return (
    <motion.div
      ref={outerRef}
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: 'auto' }}
      exit={{ opacity: 0, height: 0 }}
      transition={{ duration: 0.25, ease: 'easeInOut' }}
      style={{ overflow: 'hidden' }}
      {...releaseOverflow(outerRef)}
    >
      <form
        onSubmit={handleSubmit}
        className="automation-inline-form rounded-xl p-5 flex flex-col gap-5"
        style={{
          backgroundColor: 'var(--color-bg-elevated)',
          border: '1px solid var(--color-border-default)',
          boxShadow: 'var(--shadow-card)',
        }}
      >
        {/* ── Basic Section ─────────────────────────────── */}

        {/* Name */}
        <div className="flex flex-col gap-1.5">
          <label className={labelClass}>{t('common.name')}</label>
          <Input
            value={form.name}
            onChange={set('name')}
            placeholder={t('automation.namePlaceholder')}
            required
            className="placeholder:text-gray-500 border"
            style={inputStyle}
          />
        </div>

        {/* Trigger Type */}
        <div className="flex flex-col gap-1.5">
          <label className={labelClass}>{t('automation.triggerType')}</label>
          <AnimatedTabs
            layoutId="trigger_type"
            tabs={[
              { id: 'cron', label: t('automation.cronRecurring') },
              { id: 'once', label: t('automation.once') },
            ]}
            value={form.trigger_type}
            onChange={set('trigger_type')}
          />
        </div>

        {form.trigger_type === 'cron' && (
          <div className="flex flex-col gap-1.5">
            <label className={labelClass}>{t('automation.schedule')}</label>
            <CronScheduleBuilder
              value={form.cron_expression}
              onChange={set('cron_expression')}
            />
          </div>
        )}

        {form.trigger_type === 'once' && (
          <div className="flex flex-col gap-1.5">
            <label className={labelClass}>{t('automation.runAt')}</label>
            <Input
              type="datetime-local"
              value={form.next_run_at}
              onChange={set('next_run_at')}
              required
              className="border"
              style={inputStyle}
            />
          </div>
        )}

        {/* Instruction */}
        <div className="flex flex-col gap-1.5">
          <label className={labelClass}>{t('automation.instruction')}</label>
          <Textarea
            value={form.instruction}
            onChange={set('instruction')}
            placeholder={t('automation.instructionPlaceholder')}
            required
            rows={4}
            className="placeholder:text-gray-500 border"
            style={inputStyle}
          />
        </div>

        {/* ── Advanced Section ──────────────────────────── */}

        <div>
          <button
            type="button"
            onClick={() => setAdvancedOpen(!advancedOpen)}
            className="w-full flex items-center justify-between text-sm font-medium cursor-pointer"
            style={{ color: 'var(--color-text-primary)' }}
          >
            <span>{t('automation.advancedOptions')}</span>
            <ChevronDown
              className="h-4 w-4 transition-transform"
              style={{
                color: 'var(--color-text-tertiary)',
                transform: advancedOpen ? 'rotate(180deg)' : 'rotate(0deg)',
              }}
            />
          </button>

          <AnimatePresence>
            {advancedOpen && (
            <motion.div
              ref={advancedRef}
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.2 }}
              style={{ overflow: 'hidden' }}
              {...releaseOverflow(advancedRef)}
              className="flex flex-col gap-4 mt-3"
            >
              {/* Agent Mode */}
              <div className="flex flex-col gap-1.5">
                <label className={labelClass}>{t('automation.agentMode')}</label>
                <AnimatedTabs
                  layoutId="agent_mode"
                  tabs={[
                    { id: 'flash', label: t('automation.flash') },
                    { id: 'ptc', label: t('automation.ptcSandbox') },
                  ]}
                  value={form.agent_mode}
                  onChange={set('agent_mode')}
                />
              </div>

              {/* Workspace */}
              {form.agent_mode === 'ptc' && (
                <div className="flex flex-col gap-1.5">
                  <label className={labelClass}>{t('thread.workspace')}</label>
                  <Select
                    aria-label={t('thread.workspace')}
                    selectedKey={form.workspace_id || null}
                    onSelectionChange={setSelection('workspace_id')}
                    placeholder={t('automation.selectWorkspace')}
                  >
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectPopover>
                      <SelectListBox>
                        {workspaces.map((ws) => (
                          <SelectItem key={ws.workspace_id} id={ws.workspace_id}>
                            {ws.name}
                          </SelectItem>
                        ))}
                      </SelectListBox>
                    </SelectPopover>
                  </Select>
                </div>
              )}

              <div className="flex flex-col gap-1.5">
                <label className={labelClass}>{t('settings.timezone')}</label>
                <Select aria-label={t('settings.timezone')} selectedKey={form.timezone} onSelectionChange={setSelection('timezone')}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectPopover>
                    <SelectListBox>
                      {COMMON_TIMEZONES.map((tz) => (
                        <SelectItem key={tz} id={tz}>{tz}</SelectItem>
                      ))}
                    </SelectListBox>
                  </SelectPopover>
                </Select>
              </div>

              {/* Thread Strategy */}
              <div className="flex flex-col gap-1.5">
                <label className={labelClass}>{t('automation.threadStrategy')}</label>
                <AnimatedTabs
                  layoutId="thread_strategy"
                  tabs={[
                    { id: 'new', label: t('automation.newThreadEachRun') },
                    { id: 'continue', label: t('automation.continueExisting') },
                  ]}
                  value={form.thread_strategy}
                  onChange={set('thread_strategy')}
                />
              </div>

              {/* Delivery */}
              <div className="flex flex-col gap-1.5">
                <label className={labelClass}>{t('automation.delivery')}</label>
                <AnimatedTabs
                  layoutId="delivery_method"
                  tabs={[
                    { id: '', label: t('automation.deliverNone') },
                    { id: 'slack', label: t('automation.deliverToSlack') },
                    { id: 'discord', label: t('automation.deliverToDiscord') },
                  ]}
                  value={form.delivery_method}
                  onChange={set('delivery_method')}
                />
              </div>

              {/* Max Failures */}
              <div className="flex flex-col gap-1.5">
                <label className={labelClass}>{t('automation.maxFailures')}</label>
                <Input
                  type="number"
                  min={1}
                  max={100}
                  value={form.max_failures}
                  onChange={set('max_failures')}
                  className="border w-24"
                  style={inputStyle}
                />
              </div>

              {/* Description */}
              <div className="flex flex-col gap-1.5">
                <label className={labelClass}>{t('common.description')}</label>
                <Input
                  value={form.description}
                  onChange={set('description')}
                  placeholder={t('automation.descPlaceholder')}
                  className="placeholder:text-gray-500 border"
                  style={inputStyle}
                />
              </div>
            </motion.div>
          )}
          </AnimatePresence>
        </div>

        {/* ── Actions ───────────────────────────────────── */}

        <div
          className="form-actions flex flex-col-reverse sm:flex-row sm:justify-end gap-2 pt-4 mt-1"
          style={{ borderTop: '1px solid var(--color-border-default)' }}
        >
          <Button type="button" variant="ghost" onClick={onCancel}>
            {t('common.cancel')}
          </Button>
          <Button
            type="submit"
            disabled={loading}
            className="transition-opacity hover:opacity-90"
            style={{ backgroundColor: 'var(--color-btn-primary-bg)', color: 'var(--color-btn-primary-text)' }}
          >
            {loading ? t('common.saving') : isEdit ? t('automation.saveChanges') : t('common.create')}
          </Button>
        </div>
      </form>
    </motion.div>
  );
}
