import { useEffect, useRef, useState } from 'react';
import { CheckCircle2, QrCode, RefreshCw, Unlink } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import ConfirmDialog from '@/components/ui/ConfirmDialog';
import { cancelWechatLinkAttempt, disconnectWechat, pollWechatLinkAttempt, startWechatLinkAttempt, updateWechatStatus } from '../api';
import { useWechatStatus } from '../queries';

export function ChannelsTab() {
  const { t } = useTranslation();
  const status = useWechatStatus();
  const [open, setOpen] = useState(false);
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
    if (!open || !attempt || ['linked', 'expired', 'failed', 'cancelled'].includes(attempt.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const next = await pollWechatLinkAttempt(attempt.attempt_id);
        setAttempt(next);
        if (next.status === 'linked') {
          setOpen(false);
          void status.refetch();
        }
      } catch { /* the next tick remains the retry boundary */ }
    }, 2_000);
    return () => window.clearInterval(timer);
  }, [open, attempt?.attempt_id, attempt?.status]);

  const configure = async () => {
    const next = await startWechatLinkAttempt();
    setAttempt(next);
    setVerificationCode('');
    setOpen(true);
  };

  const close = (nextOpen: boolean) => {
    if (nextOpen) { setOpen(true); return; }
    const current = attemptRef.current;
    if (current && !['linked', 'expired', 'failed', 'cancelled'].includes(current.status)) void cancelWechatLinkAttempt(current.attempt_id);
    setOpen(false);
    setAttempt(null);
  };

  const submitVerification = async () => {
    if (!attempt || !verificationCode) return;
    const next = await pollWechatLinkAttempt(attempt.attempt_id, verificationCode);
    setVerificationCode('');
    setAttempt(next);
  };

  const saveIdle = async () => {
    const bounded = Math.max(1, Math.min(10080, Number(idleMinutes) || 360));
    setIdleMinutes(bounded);
    await updateWechatStatus(bounded * 60);
    await status.refetch();
  };

  const currentStatus = status.data?.status ?? 'unlinked';
  return (
    <section className="settings-channel-panel" aria-label={t('settings.channels')}>
      <div className="flex items-center justify-between gap-4 border-b pb-4" style={{ borderColor: 'var(--color-border-muted)' }}>
        <div className="flex items-center gap-3"><QrCode className="size-5" aria-hidden="true" /><h3 className="text-base font-semibold">{t('settings.wechat')}</h3></div>
        {currentStatus === 'active' && <span className="flex items-center gap-1 text-sm" style={{ color: 'var(--color-success)' }}><CheckCircle2 className="size-4" aria-hidden="true" />{t('settings.connected')}</span>}
      </div>
      <div className="py-5">
        {currentStatus !== 'active' && <>
          {currentStatus === 'reauth_required' && <p className="mb-4 text-sm" style={{ color: 'var(--color-text-secondary)' }}>{t('settings.wechatReauth')}</p>}
          <Button onClick={configure}><QrCode className="mr-2 size-4" aria-hidden="true" />{t('settings.configureWechat')}</Button>
        </>}
        {currentStatus === 'active' && <div className="space-y-4">
          <label className="block text-sm" htmlFor="wechat-idle-timeout">{t('settings.wechatIdleTimeout')}</label>
          <div className="flex max-w-sm items-center gap-2"><input id="wechat-idle-timeout" className="h-9 w-28 rounded border bg-transparent px-2 text-sm" type="number" min={1} max={10080} value={idleMinutes} onChange={(e) => setIdleMinutes(Number(e.target.value))} /><Button variant="outline" onClick={saveIdle}>{t('settings.wechatSave')}</Button></div>
          <Button variant="outline" onClick={() => setDisconnectOpen(true)}><Unlink className="mr-2 size-4" aria-hidden="true" />{t('settings.wechatDisconnect')}</Button>
        </div>}
      </div>
      <Dialog open={open} onOpenChange={close}>
        <DialogContent variant="centered" className="max-w-sm">
          <DialogHeader><DialogTitle>{t('settings.configureWechat')}</DialogTitle></DialogHeader>
          {attempt?.qr_code_url && <img className="mx-auto aspect-square w-full max-w-[280px] object-contain" src={attempt.qr_code_url} alt={t('settings.wechatQrAlt')} />}
          <p className="text-center text-sm" style={{ color: 'var(--color-text-secondary)' }}>{attempt?.status === 'scanned' ? t('settings.wechatScanned') : attempt?.status === 'verification_required' ? t('settings.wechatVerification') : attempt?.status === 'expired' ? t('settings.wechatReauth') : t('settings.wechatWaiting')}</p>
          {attempt?.status === 'verification_required' && <div className="flex gap-2"><input autoFocus inputMode="numeric" value={verificationCode} onChange={(e) => setVerificationCode(e.target.value.replace(/\D/g, ''))} className="h-9 min-w-0 flex-1 rounded border bg-transparent px-2 text-sm" aria-label={t('settings.wechatVerification')} /><Button onClick={submitVerification}><RefreshCw className="mr-2 size-4" aria-hidden="true" />{t('settings.wechatSave')}</Button></div>}
          <DialogFooter><Button variant="outline" onClick={() => close(false)}>{t('common.cancel')}</Button></DialogFooter>
        </DialogContent>
      </Dialog>
      <ConfirmDialog open={disconnectOpen} onOpenChange={setDisconnectOpen} title={t('settings.wechatDisconnect')} message={t('settings.wechatDisconnectConfirm')} confirmLabel={t('settings.wechatDisconnect')} onConfirm={async () => { await disconnectWechat(); await status.refetch(); setDisconnectOpen(false); }} />
    </section>
  );
}
