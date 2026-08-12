import { useState } from 'react';
import { Code2, FileText, Trash2 } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { clearPreferences } from '@/api/user';
import { usePreferences } from '@/hooks/usePreferences';
import { useUpdatePreferences } from '@/hooks/useUpdatePreferences';
import { queryKeys } from '@/lib/queryKeys';
import { useToast } from '@/components/ui/use-toast';
import ConfirmDialog from '@/components/ui/ConfirmDialog';

export function PreferencesTab() {
  const { preferences } = usePreferences();
  const updatePreferences = useUpdatePreferences();
  const queryClient = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  const [error, setError] = useState<string | null>(null);
  const [showResetConfirm, setShowResetConfirm] = useState(false);
  const [isResetting, setIsResetting] = useState(false);

  const agentPreference = (
    preferences as { agent_preference?: Record<string, unknown> } | null
  )?.agent_preference ?? {};
  const outputFormat = agentPreference.output_format === 'html' ? 'html' : 'markdown';

  const handleOutputFormatChange = async (format: 'markdown' | 'html') => {
    try {
      await updatePreferences.mutateAsync({
        agent_preference: {
          ...agentPreference,
          output_format: format === 'html' ? 'html' : null,
        },
      });
    } catch {
      toast({
        variant: 'destructive',
        title: t('common.error'),
        description: t('settings.failedToSaveSettings'),
      });
    }
  };

  const handleResetConfirm = async () => {
    setIsResetting(true);
    try {
      await clearPreferences();
      queryClient.invalidateQueries({ queryKey: queryKeys.user.preferences() });
      queryClient.invalidateQueries({ queryKey: queryKeys.features.all });
      setShowResetConfirm(false);
    } catch {
      setError(t('settings.failedToResetPreferences'));
      setShowResetConfirm(false);
    } finally {
      setIsResetting(false);
    }
  };

  return (
    <>
      <div className="space-y-5">
        <p className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
          {t('settings.preferencesDesc')}
        </p>

        <div
          className="p-3 rounded-lg"
          style={{ backgroundColor: 'var(--color-bg-card)', border: '1px solid var(--color-border-muted)' }}
        >
          <div className="flex items-center justify-between gap-3">
            <label className="text-sm font-medium" style={{ color: 'var(--color-text-primary)' }}>
              {t('settings.outputFormat')}
            </label>
            <div className="inline-flex rounded-lg overflow-hidden" style={{ border: '1px solid var(--color-border-muted)' }}>
              <button
                type="button"
                onClick={() => handleOutputFormatChange('markdown')}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium transition-colors"
                style={{
                  backgroundColor: outputFormat === 'markdown' ? 'var(--color-accent-soft)' : 'transparent',
                  color: outputFormat === 'markdown' ? 'var(--color-accent-primary)' : 'var(--color-text-tertiary)',
                }}
              >
                <FileText className="h-3.5 w-3.5" />
                {t('settings.outputFormatDefault')}
              </button>
              <button
                type="button"
                onClick={() => handleOutputFormatChange('html')}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium transition-colors"
                style={{
                  backgroundColor: outputFormat === 'html' ? 'var(--color-accent-soft)' : 'transparent',
                  color: outputFormat === 'html' ? 'var(--color-accent-primary)' : 'var(--color-text-tertiary)',
                }}
              >
                <Code2 className="h-3.5 w-3.5" />
                {t('settings.outputFormatHtml')}
              </button>
            </div>
          </div>
          <p className="text-xs mt-2" style={{ color: 'var(--color-text-tertiary)' }}>
            {outputFormat === 'html'
              ? t('settings.outputFormatDescriptionHtml')
              : t('settings.outputFormatDescriptionDefault')}
          </p>
        </div>

        {error && (
          <div className="p-3 rounded-md" style={{ backgroundColor: 'var(--color-loss-soft)', border: '1px solid var(--color-border-loss)' }}>
            <p className="text-sm" style={{ color: 'var(--color-loss)' }}>{error}</p>
          </div>
        )}

        <div className="flex justify-between pt-4" style={{ borderTop: '1px solid var(--color-border-muted)' }}>
          <button
            type="button"
            onClick={() => setShowResetConfirm(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors"
            style={{ color: 'var(--color-loss)', backgroundColor: 'transparent', border: '1px solid var(--color-loss)' }}
          >
            <Trash2 className="h-4 w-4" /> {t('settings.resetPreferences')}
          </button>
        </div>
      </div>

      <ConfirmDialog
        open={showResetConfirm}
        title={t('settings.resetPreferences')}
        message={t('settings.resetConfirmMsg')}
        confirmLabel={isResetting ? t('settings.resetting') : t('settings.resetPreferences')}
        onConfirm={handleResetConfirm}
        onOpenChange={setShowResetConfirm}
      />
    </>
  );
}
