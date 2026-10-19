/**
 * SET-19: tells the Settings frame that something was saved, without every screen having to say so.
 * The API client calls `announceWrite` for each successful write; the frame (SettingsContinuity)
 * listens. Calls that only look something up or draw a preview are not saves.
 */
const READ_ONLY_CALLS = /(preview|verify|reveal|check|usage|search|validate|propose)/i;
const listeners = new Set<() => void>();

export function announceWrite(method: string | undefined, url: string | undefined): void {
  const verb = (method || 'get').toUpperCase();
  if (verb === 'GET' || verb === 'HEAD' || verb === 'OPTIONS') return;
  if (READ_ONLY_CALLS.test(url || '')) return;
  if (typeof window === 'undefined' || !window.location.pathname.startsWith('/settings/')) return;
  listeners.forEach((fn) => fn());
}

export function onSettingsWrite(fn: () => void): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}
