import { apiClient, unwrapData } from '@/api/client';

const ALLOWED = new Set([
  'invoice_complete',
  'pos_line_added',
  'offline_enqueue',
  'offline_flush_fail',
  'complete_duration_ms',
  'time_to_first_invoice_ms',
]);

const sessionStart =
  typeof performance !== 'undefined' ? performance.now() : Date.now();
let firstInvoiceSent = false;

/** A-08: first-party shop-floor events. Never send GSTIN, phone, names, or line text. */
export function trackShopFloor(
  event: string,
  props?: { durationMs?: number; tapCount?: number },
): void {
  if (!ALLOWED.has(event)) return;
  const payload: Record<string, unknown> = { event };
  if (typeof props?.durationMs === 'number' && Number.isFinite(props.durationMs)) {
    payload.duration_ms = Math.max(0, Math.round(props.durationMs));
  }
  if (typeof props?.tapCount === 'number' && Number.isFinite(props.tapCount)) {
    payload.tap_count = Math.max(0, Math.round(props.tapCount));
  }
  void apiClient.post('/insights/telemetry/', payload).catch(() => undefined);
}

/** Successful Complete only — failed Complete must not fire events. */
export function trackInvoiceComplete(durationMs: number, tapCount?: number): void {
  trackShopFloor('invoice_complete', { durationMs, tapCount });
  trackShopFloor('complete_duration_ms', { durationMs, tapCount });
  if (firstInvoiceSent) return;
  firstInvoiceSent = true;
  const now = typeof performance !== 'undefined' ? performance.now() : Date.now();
  trackShopFloor('time_to_first_invoice_ms', { durationMs: Math.max(0, Math.round(now - sessionStart)) });
}

export type ShopFloorSummary = {
  days: number;
  completeP95Ms?: number | null;
  completeCount?: number;
  offlineFlushFail?: number;
  offlineEnqueue?: number;
  posLineAdded?: number;
};

export async function getShopFloorSummary(): Promise<ShopFloorSummary> {
  const { data } = await apiClient.get('/insights/telemetry/');
  return unwrapData<ShopFloorSummary>(data);
}
