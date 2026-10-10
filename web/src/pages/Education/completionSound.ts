/** Prepare audio during the confirmation click, before the network request. */
export function createCompletionSound() {
  let context: AudioContext | undefined;
  let playing = false;
  try {
    if (typeof window !== 'undefined' && window.AudioContext) {
      context = new window.AudioContext();
      void context.resume().catch(() => undefined);
    }
  } catch { /* Unsupported audio must never prevent a check-in. */ }
  const dispose = () => {
    if (context && context.state !== 'closed') void context.close().catch(() => undefined);
  };
  return {
    play() {
      if (!context || context.state !== 'running') return;
      try {
        const oscillator = context.createOscillator();
        const gain = context.createGain();
        const start = context.currentTime;
        oscillator.type = 'sine';
        oscillator.frequency.setValueAtTime(660, start);
        oscillator.frequency.exponentialRampToValueAtTime(880, start + 0.12);
        gain.gain.setValueAtTime(0.0001, start);
        gain.gain.exponentialRampToValueAtTime(0.08, start + 0.01);
        gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.22);
        oscillator.connect(gain).connect(context.destination);
        oscillator.onended = dispose;
        oscillator.start();
        oscillator.stop(start + 0.23);
        playing = true;
      } catch { dispose(); }
    },
    close() { if (!playing) dispose(); },
  };
}
