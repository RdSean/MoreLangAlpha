import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Pencil, Plus, RotateCcw, Sparkles } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import ConfirmDialog from './components/ConfirmDialog';
import LayoutModeToggle from './components/LayoutModeToggle';
import { DashboardGrid } from './widgets/framework/DashboardGrid';
import { AddWidgetDialog } from './widgets/framework/AddWidgetDialog';
import { PresetsDialog } from './widgets/framework/PresetsDialog';
import { getWidget } from './widgets/framework/WidgetRegistry';
import { placeAtBottom } from './widgets/framework/reconcile';
import { newWidgetId } from './widgets/framework/ids';
import { useDashboardPrefs } from './widgets/framework/useDashboardPrefs';
import { useScrollMemory } from '@/lib/scrollMemory';
import type { DashboardPrefs, WidgetInstance } from './widgets/types';
import type { PresetId } from './widgets/presets';
// Side-effect: populate the registry before any preset factory runs.
import './widgets/index';
import './Dashboard.css';

interface DashboardCustomProps {
  mode: 'classic' | 'custom';
  onModeChange: (mode: 'classic' | 'custom') => void;
}

/**
 * The widget canvas.
 *
 * Upstream's version was 403 lines because it also hosted the market websocket
 * provider, four finance dialogs and a floating chat card. None of those exist
 * here, so this is the canvas and its toolbar: the grid, the gallery, the preset
 * picker, reset, and the edit-mode switch.
 */
export default function DashboardCustom({ mode, onModeChange }: DashboardCustomProps) {
  const { t } = useTranslation();
  const { prefs, update, applyPreset, resetToDefault } = useDashboardPrefs();
  const [editMode, setEditMode] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [presetsOpen, setPresetsOpen] = useState(false);
  const [resetConfirmOpen, setResetConfirmOpen] = useState(false);
  const [settingsFor, setSettingsFor] = useState<string | null>(null);
  const mainRef = useRef<HTMLElement>(null);
  useScrollMemory(mainRef, 'page:dashboard-custom');

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && editMode) setEditMode(false);
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [editMode]);

  const handleAddWidget = useCallback(
    (type: string) => {
      const def = getWidget(type);
      if (!def) return;
      const initialConfig = def.initConfig
        ? def.initConfig()
        : { ...(def.defaultConfig as object) };
      const instance: WidgetInstance = { id: newWidgetId(), type, config: initialConfig };
      update((prev: DashboardPrefs) => {
        if (def.singleton && prev.widgets.some((widget) => widget.type === type)) return prev;
        return {
          ...prev,
          widgets: [...prev.widgets, instance],
          layouts: placeAtBottom(prev.layouts, instance.id, def.defaultSize.w, def.defaultSize.h),
        };
      });
    },
    [update],
  );

  const handleApplyPreset = useCallback(
    (id: PresetId) => {
      applyPreset(id);
      setPresetsOpen(false);
    },
    [applyPreset],
  );

  const settingsInstance = settingsFor
    ? (prefs.widgets.find((widget) => widget.id === settingsFor) ?? null)
    : null;
  const settingsDef = settingsInstance ? getWidget(settingsInstance.type) : undefined;

  return (
    <div className="dashboard-container min-h-full">
      <main
        ref={mainRef}
        className="flex min-h-0 flex-1 flex-col overflow-y-auto overflow-x-hidden"
      >
        <header
          className="sticky top-0 z-20 flex flex-wrap items-center justify-between gap-3 border-b px-3 py-2 sm:px-6"
          style={{
            borderColor: 'var(--color-border-muted)',
            backgroundColor: 'var(--color-bg-canvas)',
          }}
        >
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              data-testid="canvas-add-widget"
              onClick={() => setAddOpen(true)}
              className="flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs transition-colors hover:bg-[var(--color-bg-hover)]"
              style={{
                borderColor: 'var(--color-border-muted)',
                color: 'var(--color-text-primary)',
              }}
            >
              <Plus size={12} aria-hidden="true" />
              {t('dashboard.widgets.shell.addWidget')}
            </button>
            <button
              type="button"
              data-testid="canvas-presets"
              onClick={() => setPresetsOpen(true)}
              className="flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs transition-colors hover:bg-[var(--color-bg-hover)]"
              style={{
                borderColor: 'var(--color-border-muted)',
                color: 'var(--color-text-primary)',
              }}
            >
              <Sparkles size={12} aria-hidden="true" />
              {t('dashboard.widgets.shell.presets')}
            </button>
            <button
              type="button"
              data-testid="canvas-edit"
              onClick={() => setEditMode((current) => !current)}
              aria-pressed={editMode}
              title={t(
                editMode
                  ? 'dashboard.layoutToggle.exitEditLayout'
                  : 'dashboard.layoutToggle.editLayout',
              )}
              className="flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs transition-colors hover:bg-[var(--color-bg-hover)]"
              style={{
                borderColor: editMode
                  ? 'var(--color-accent-primary)'
                  : 'var(--color-border-muted)',
                color: editMode ? 'var(--color-accent-primary)' : 'var(--color-text-primary)',
              }}
            >
              <Pencil size={12} aria-hidden="true" />
              {editMode
                ? t('dashboard.widgets.shell.done')
                : t('dashboard.layoutToggle.editLayout')}
            </button>
            <button
              type="button"
              data-testid="canvas-reset"
              onClick={() => setResetConfirmOpen(true)}
              className="flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs transition-colors hover:bg-[var(--color-bg-hover)]"
              style={{
                borderColor: 'var(--color-border-muted)',
                color: 'var(--color-text-secondary)',
              }}
            >
              <RotateCcw size={12} aria-hidden="true" />
              {t('dashboard.widgets.shell.reset')}
            </button>
          </div>
          <LayoutModeToggle mode={mode} onModeChange={onModeChange} />
        </header>

        <div className="mx-auto w-full max-w-[1920px] p-3 pb-24 sm:p-6">
          <DashboardGrid
            prefs={prefs}
            editMode={editMode}
            onChange={(next) => update(() => next)}
            onOpenSettings={setSettingsFor}
          />
        </div>
      </main>

      <AddWidgetDialog
        open={addOpen}
        onOpenChange={setAddOpen}
        onAdd={handleAddWidget}
        existingWidgets={prefs.widgets}
      />
      <PresetsDialog
        open={presetsOpen}
        onOpenChange={setPresetsOpen}
        onApply={handleApplyPreset}
      />

      <ConfirmDialog
        open={resetConfirmOpen}
        title={t('dashboard.widgets.shell.resetTitle')}
        message={t('dashboard.widgets.shell.resetMessage')}
        confirmLabel={t('dashboard.widgets.shell.resetConfirm')}
        onConfirm={resetToDefault}
        onOpenChange={setResetConfirmOpen}
      />

      {/* Widget settings are a focused dialog over one instance; the frame owns
          the button, the canvas owns the dialog. */}
      {settingsInstance && settingsDef?.settingsComponent ? (
        <SettingsDialogShell
          title={t(settingsDef.titleKey)}
          open
          onClose={() => setSettingsFor(null)}
        >
          <settingsDef.settingsComponent
            config={settingsInstance.config}
            onChange={(patch) =>
              update((prev: DashboardPrefs) => ({
                ...prev,
                widgets: prev.widgets.map((widget) =>
                  widget.id === settingsInstance.id
                    ? { ...widget, config: { ...(widget.config as object), ...patch } }
                    : widget,
                ),
              }))
            }
            onClose={() => setSettingsFor(null)}
          />
        </SettingsDialogShell>
      ) : null}
    </div>
  );
}

function SettingsDialogShell({
  title,
  open,
  onClose,
  children,
}: {
  title: string;
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent
        className="sm:max-w-md border"
        style={{
          backgroundColor: 'var(--color-bg-elevated)',
          borderColor: 'var(--color-border-elevated)',
        }}
      >
        <DialogHeader>
          <DialogTitle className="title-font" style={{ color: 'var(--color-text-primary)' }}>
            {t('dashboard.widgets.shell.settingsDialogTitle', { title })}
          </DialogTitle>
        </DialogHeader>
        <div className="pt-2">{children}</div>
      </DialogContent>
    </Dialog>
  );
}
