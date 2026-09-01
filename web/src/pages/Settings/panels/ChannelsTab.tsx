import { useEffect, useRef, useState } from 'react';
import { CheckCircle2, QrCode, RefreshCw, Unlink } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import ConfirmDialog from '@/components/ui/ConfirmDialog';
import { cancelWechatLinkAttempt, disconnectWechat, pollWechatLinkAttempt, startWechatLinkAttempt, updateWechatStatus } from '../api';
import { useWechatStatus } from '../queries';

export function ChannelsTab() {
  const { t } = useTranslation();
  const status = useWechatStatus();
  const [expanded, setExpanded] = useState(false);
  const [attempt, setAttempt] = useState<Awaited<ReturnType<typeof startWechatLinkAttempt>> | null>(null);
  const [verificationCode, setVerificationCode] = useState('');
  const [disconnectOpen, setDisconnectOpen] = useState(false);
  const [idleMinutes, setIdleMinutes] = useState(360);
  const attemptRef = useRef(attempt);
  attemptRef.current = attempt;

  useEffect(() => {
    if (status.data) setIdleMinutes(Math.round(status.data.idle_timeout_seconds / 60));
  }, [status.data]);

  useEffect(() => () => {
    const current = attemptRef.current;
    if (current && !['linked', 'expired', 'failed', 'cancelled'].includes(current.status)) {
      void cancelWechatLinkAttempt(current.attempt_id);
    }
  }, []);

  useEffect(() => {
    if (!expanded || !attempt || ['linked', 'expired', 'failed', 'cancelled'].includes(attempt.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const next = await pollWechatLinkAttempt(attempt.attempt_id);
        setAttempt((previous) => ({
          ...next,
          qr_code_url: next.qr_code_url ?? previous?.qr_code_url,
        }));
        if (next.status === 'linked') {
          setExpanded(false);
          setAttempt(null);
          void status.refetch();
        }
      } catch { /* the next tick remains the retry boundary */ }
    }, 2_000);
    return () => window.clearInterval(timer);
  }, [expanded, attempt?.attempt_id, attempt?.status]);

  const configure = async () => {
    const next = await startWechatLinkAttempt();
    setAttempt(next);
    setVerificationCode('');
    setExpanded(true);
  };

  const collapse = () => {
    const current = attemptRef.current;
    if (current && !['linked', 'expired', 'failed', 'cancelled'].includes(current.status)) void cancelWechatLinkAttempt(current.attempt_id);
    setExpanded(false);
    setAttempt(null);
  };

  const submitVerification = async () => {
    if (!attempt || !verificationCode) return;
    const next = await pollWechatLinkAttempt(attempt.attempt_id, verificationCode);
    setVerificationCode('');
    setAttempt((previous) => ({
      ...next,
      qr_code_url: next.qr_code_url ?? previous?.qr_code_url,
    }));
    if (next.status === 'linked') {
      setExpanded(false);
      setAttempt(null);
      await status.refetch();
    }
  };

  const saveIdle = async () => {
    const bounded = Math.max(1, Math.min(10080, Number(idleMinutes) || 360));
    setIdleMinutes(bounded);
    await updateWechatStatus(bounded * 60);
    await status.refetch();
  };

  const currentStatus = status.data?.status ?? 'unlinked';
  return (
    <section className="settings-channel-panel space-y-4" aria-label={t('settings.channels')}>
      <div>
        <h3 className="text-base font-semibold" style={{ color: 'var(--color-text-primary)' }}>{t('settings.channels')}</h3>
      </div>

      <article className="overflow-hidden rounded-lg border" style={{ borderColor: 'var(--color-border-muted)' }}>
        <div className="p-5">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <QrCode className="size-5 shrink-0" aria-hidden="true" />
                <h4 className="text-base font-semibold">{t('settings.wechatIntegration')}</h4>
                {currentStatus === 'active' && <span className="flex items-center gap-1 text-xs" style={{ color: 'var(--color-success)' }}><CheckCircle2 className="size-3.5" aria-hidden="true" />{t('settings.connected')}</span>}
              </div>
              <p className="mt-1 text-sm" style={{ color: 'var(--color-text-secondary)' }}>{t('settings.wechatDescription')}</p>
            </div>
            <Button size="sm" variant="outline" className="shrink-0" onClick={expanded ? collapse : configure} aria-expanded={expanded} aria-controls="wechat-config-panel">
              <QrCode className="mr-1.5 size-3.5" aria-hidden="true" />
              {expanded ? t('settings.collapseWechat') : t('settings.configureWechat')}
            </Button>
          </div>

          {currentStatus === 'reauth_required' && <p className="mt-4 text-sm" style={{ color: 'var(--color-text-secondary)' }}>{t('settings.wechatReauth')}</p>}

          {currentStatus === 'active' && <div className="mt-5 space-y-4 border-t pt-5" style={{ borderColor: 'var(--color-border-muted)' }}>
            <label className="block text-sm" htmlFor="wechat-idle-timeout">{t('settings.wechatIdleTimeout')}</label>
            <div className="flex max-w-sm items-center gap-2"><input id="wechat-idle-timeout" className="h-9 w-28 rounded border bg-transparent px-2 text-sm" type="number" min={1} max={10080} value={idleMinutes} onChange={(e) => setIdleMinutes(Number(e.target.value))} /><Button variant="outline" onClick={saveIdle}>{t('settings.wechatSave')}</Button></div>
            <Button variant="outline" onClick={() => setDisconnectOpen(true)}><Unlink className="mr-2 size-4" aria-hidden="true" />{t('settings.wechatDisconnect')}</Button>
          </div>}

          {expanded && <div id="wechat-config-panel" className="mt-5 border-t pt-5" style={{ borderColor: 'var(--color-border-muted)' }}>
            {attempt?.qr_code_url && attempt.status !== 'expired' && <img className="mx-auto aspect-square w-full max-w-[280px] object-contain" src={attempt.qr_code_url} alt={t('settings.wechatQrAlt')} />}
            <p className="mt-3 text-center text-sm" style={{ color: 'var(--color-text-secondary)' }}>{attempt?.status === 'scanned' ? t('settings.wechatScanned') : attempt?.status === 'verification_required' ? t('settings.wechatVerification') : attempt?.status === 'expired' ? t('settings.wechatReauth') : t('settings.wechatWaiting')}</p>
            {attempt?.status === 'verification_required' && <div className="mt-4 flex gap-2"><input autoFocus inputMode="numeric" value={verificationCode} onChange={(e) => setVerificationCode(e.target.value.replace(/\D/g, ''))} className="h-9 min-w-0 flex-1 rounded border bg-transparent px-2 text-sm" aria-label={t('settings.wechatVerification')} /><Button onClick={submitVerification}><RefreshCw className="mr-2 size-4" aria-hidden="true" />{t('settings.wechatSave')}</Button></div>}
          </div>}
        </div>
      </article>
      <ConfirmDialog open={disconnectOpen} onOpenChange={setDisconnectOpen} title={t('settings.wechatDisconnect')} message={t('settings.wechatDisconnectConfirm')} confirmLabel={t('settings.wechatDisconnect')} onConfirm={async () => { await disconnectWechat(); await status.refetch(); setDisconnectOpen(false); }} />
    </section>
  );
}
