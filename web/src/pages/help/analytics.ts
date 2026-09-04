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
  const { query: rawQuery, ...safeProps } = props ?? {};
  const queryLen = typeof rawQuery === 'string' ? rawQuery.length : 0;
  const queryLenBucket = queryLen ? Math.min(2000, Math.ceil(queryLen / 20) * 20) : undefined;
  try {
    (
      window as Window & {
        bizboardAnalytics?: { track?: (event: string, data?: Record<string, unknown>) => void };
      }
    ).bizboardAnalytics?.track?.(name, { ...safeProps, queryLenBucket });
  } catch {
    // Third-party analytics are best effort and never receive raw query text.
  }
  try {
    // F3-054: the raw help-search query IS retained first-party — the server's
    // "top zero-result queries" / "repeat queries" reports need the text. This
    // is a deliberate, documented retention (first-party endpoint only; never
    // forwarded to third-party analytics above). It can contain whatever a user
    // types into help search. Send it once (not also nested in `props`).
    enqueue({
      name,
      intentId: props?.intentId,
      source: props?.source,
      state: props?.state,
      screen: props?.screen ?? (typeof window !== 'undefined' ? window.location.pathname : ''),
      query: rawQuery,
      queryLenBucket,
      props: safeProps,
    });
  } catch {
    // First-party enqueue is best effort.
  }
}
