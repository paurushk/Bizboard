import { HELP_EVENTS, type HelpEventName } from './events';
import { postHelpEvents } from '@/api/help';

export { HELP_EVENTS };

const PENDING_CAP = 80;
const pending: Record<string, unknown>[] = [];
let flushTimer: number | null = null;

function scheduleFlush(delayMs: number) {
  if (flushTimer != null) return;
  flushTimer = window.setTimeout(() => {
    flushTimer = null;
    const batch = pending.splice(0, pending.length);
    if (!batch.length) return;
    void postHelpEvents(batch).catch(() => {
      pending.unshift(...batch);
      if (pending.length > PENDING_CAP) pending.length = PENDING_CAP;
      scheduleFlush(2000);
    });
  }, delayMs);
}

function enqueue(event: Record<string, unknown>) {
  pending.push(event);
  if (pending.length > PENDING_CAP) pending.splice(0, pending.length - PENDING_CAP);
  scheduleFlush(400);
}

export function trackHelpEvent(name: HelpEventName | string, props?: Record<string, unknown>): void {
  try {
    if (import.meta.env.VITE_ONBOARDING_ANALYTICS === 'console' || import.meta.env.DEV) {
      console.info('[help]', name, props);
    }
  } catch {
    // Analytics must never interrupt Help.
  }
  try {
    const { query: rawQuery, ...safe } = props ?? {};
    const queryLen = typeof rawQuery === 'string' ? rawQuery.length : 0;
    (
      window as Window & {
        bizboardAnalytics?: { track?: (event: string, data?: Record<string, unknown>) => void };
      }
    ).bizboardAnalytics?.track?.(name, {
      ...safe,
      queryLenBucket: queryLen ? Math.min(2000, Math.ceil(queryLen / 20) * 20) : undefined,
    });
  } catch {
    // Third-party analytics are best effort and never receive raw query text.
  }
  try {
    enqueue({
      name,
      intentId: props?.intentId,
      source: props?.source,
      state: props?.state,
      screen: props?.screen ?? (typeof window !== 'undefined' ? window.location.pathname : ''),
      query: props?.query,
      props,
    });
  } catch {
    // First-party enqueue is best effort.
  }
}
