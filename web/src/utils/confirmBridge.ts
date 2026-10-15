import type { ConfirmAsk } from '@/utils/completeWithConfirms';

// The app shell registers an in-app confirmation dialog here (DN-04). completeWithConfirms
// uses it when a caller passes none, so every document "Complete" flow stops using the browser
// popup without each page wiring its own dialog. Without a registered host (tests, embeds)
// completeWithConfirms falls back to window.confirm.
let globalAsk: ConfirmAsk | null = null;

export function registerGlobalConfirm(ask: ConfirmAsk | null): void {
  globalAsk = ask;
}

export function getGlobalConfirm(): ConfirmAsk | null {
  return globalAsk;
}

/**
 * Ask one yes/no question through the in-app dialog (DN-04). Use this instead of
 * window.confirm for destructive actions; falls back to window.confirm only when no
 * host is mounted (tests, embeds).
 */
export async function confirmAction(message: string): Promise<boolean> {
  const ask = globalAsk;
  if (ask) return ask([message]);
  return window.confirm(message);
}

/** What the override dialog shows; `reasonLabel` is the text-field label. */
export type ReasonRequest = { title: string; body: string; reasonLabel: string; confirmLabel?: string };
export type ReasonAsk = (request: ReasonRequest) => Promise<string | null>;

let globalReason: ReasonAsk | null = null;

export function registerGlobalReason(ask: ReasonAsk | null): void {
  globalReason = ask;
}

/**
 * Ask for a written reason before an Owner/Accountant override (cancelled GSTIN, 3-way mismatch).
 * Resolves the trimmed reason, or null when cancelled. Falls back to window.prompt without a host.
 */
export async function askReason(request: ReasonRequest): Promise<string | null> {
  if (globalReason) return globalReason(request);
  const typed = window.prompt(`${request.body}

${request.reasonLabel}`);
  const reason = (typed ?? '').trim();
  return reason || null;
}
