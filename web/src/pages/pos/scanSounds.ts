/** Short Web Audio cues for a scan (BUG-UI-006). PosPage does not call this yet. */

export function playScanTone(kind: 'ok' | 'error', context?: AudioContext): void {
  try {
  const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  const audio = context ?? (Ctx ? new Ctx() : null);
  if (!audio) return;
  const osc = audio.createOscillator();
  const gain = audio.createGain();
  osc.frequency.value = kind === 'ok' ? 880 : 220;
  osc.type = kind === 'ok' ? 'sine' : 'square';
  gain.gain.value = 0.05;
  osc.connect(gain);
  gain.connect(audio.destination);
  osc.start();
  osc.stop(audio.currentTime + 0.08);
  } catch {
    /* audio blocked */
  }
}
