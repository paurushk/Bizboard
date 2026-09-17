import axios from 'axios';
import { apiClient, getErrorCode, getLastRequestId, isNetworkError, unwrapData } from '@/api/client';
import helpCodes from '@/pages/help/helpCodes.json';

const HELP_ERROR_CODES = new Set(helpCodes.codes);

const ALLOWED = new Set([
  'invoice_complete',
  'pos_line_added',
  'offline_enqueue',
  'offline_flush_fail',
  'complete_duration_ms',
  'time_to_first_invoice_ms',
  'signup_completed',
  'wizard_tax_confirmed',
  'wizard_completed',
  'journey_started',
  'journey_failed',
]);

export type JourneyName = 'signup' | 'invoice_complete' | 'pdf' | 'payment';
export type FailureReason = 'validation' | 'help_code' | 'timeout' | '5xx' | 'offline' | 'unknown';

const SESSION_KEY = 'bizboard:telemetry-session';

const sessionStart =
  typeof performance !== 'undefined' ? performance.now() : Date.now();
let firstInvoiceSent = false;

function telemetrySessionId(): string {
  if (typeof sessionStorage === 'undefined') return '';
  try {
    let id = sessionStorage.getItem(SESSION_KEY);
    if (!id) {
      id =
        typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
          ? crypto.randomUUID()
          : `s-${Date.now().toString(36)}`;
      sessionStorage.setItem(SESSION_KEY, id);
    }
    return id.slice(0, 36);
  } catch {
    return '';
  }
}

export type ShopFloorProps = {
  durationMs?: number;
  tapCount?: number;
  journey?: JourneyName;
  feature?: string;
  success?: boolean;
  failureReason?: FailureReason;
};

/** A-08 / O-Gate 2: first-party shop-floor events. Never send GSTIN, phone, names, or line text. */
export function trackShopFloor(event: string, props?: ShopFloorProps): void {
  if (!ALLOWED.has(event)) return;
  const payload: Record<string, unknown> = { event };
  if (typeof props?.durationMs === 'number' && Number.isFinite(props.durationMs)) {
    payload.duration_ms = Math.max(0, Math.round(props.durationMs));
  }
  if (typeof props?.tapCount === 'number' && Number.isFinite(props.tapCount)) {
    payload.tap_count = Math.max(0, Math.round(props.tapCount));
  }
  if (props?.journey) payload.journey = props.journey;
  if (props?.feature) payload.feature = props.feature.slice(0, 40);
  if (typeof props?.success === 'boolean') payload.success = props.success;
  if (props?.failureReason) payload.failure_reason = props.failureReason;
  const sessionId = telemetrySessionId();
  if (sessionId) payload.session_id = sessionId;
  const requestId = getLastRequestId();
  if (requestId) payload.request_id = requestId;
  void apiClient.post('/insights/telemetry/', payload).catch(() => undefined);
}

/** Successful Complete only — failed Complete must not fire invoice_complete. */
export function trackInvoiceComplete(durationMs: number, tapCount?: number): void {
  trackShopFloor('invoice_complete', { durationMs, tapCount, journey: 'invoice_complete' });
  trackShopFloor('complete_duration_ms', { durationMs, tapCount, journey: 'invoice_complete' });
  if (firstInvoiceSent) return;
  firstInvoiceSent = true;
  const now = typeof performance !== 'undefined' ? performance.now() : Date.now();
  trackShopFloor('time_to_first_invoice_ms', {
    durationMs: Math.max(0, Math.round(now - sessionStart)),
    journey: 'invoice_complete',
  });
}

export function trackJourneyStarted(journey: JourneyName, feature?: string): void {
  trackShopFloor('journey_started', { journey, feature });
}

export function trackJourneyFailed(
  journey: JourneyName,
  reason: FailureReason,
  props?: { durationMs?: number; feature?: string },
): void {
  trackShopFloor('journey_failed', {
    journey,
    failureReason: reason,
    durationMs: props?.durationMs,
    feature: props?.feature,
    success: false,
  });
}

export function classifyCompleteFailure(error: unknown): FailureReason {
  if (axios.isAxiosError(error)) {
    const code = error.code || '';
    const message = error.message || '';
    if (code === 'ECONNABORTED' || code === 'ETIMEDOUT' || /timeout/i.test(message)) {
      return 'timeout';
    }
    const status = error.response?.status;
    if (typeof status === 'number' && status >= 500) return '5xx';
    if (isNetworkError(error) || !error.response) return 'offline';
    const errCode = getErrorCode(error) || '';
    if (HELP_ERROR_CODES.has(errCode) || intentLooksLikeHelp(errCode)) return 'help_code';
    if (typeof status === 'number' && status >= 400) return 'validation';
  }
  if (error instanceof Error && /timeout/i.test(error.message)) return 'timeout';
  return 'unknown';
}

function intentLooksLikeHelp(code: string): boolean {
  return Boolean(code) && code in (helpCodes.errorCodeToIntent ?? {});
}

/** Wrap a Complete call: started on click; one invoice_complete on success; failed+reason otherwise. */
export async function runInvoiceCompleteJourney<T>(
  run: () => Promise<T>,
  opts?: { feature?: string; tapCount?: number },
): Promise<T> {
  const started = Date.now();
  trackJourneyStarted('invoice_complete', opts?.feature);
  try {
    const result = await run();
    trackInvoiceComplete(Date.now() - started, opts?.tapCount);
    return result;
  } catch (err) {
    trackJourneyFailed('invoice_complete', classifyCompleteFailure(err), {
      durationMs: Date.now() - started,
      feature: opts?.feature,
    });
    throw err;
  }
}

export type ShopFloorSummary = {
  days: number;
  completeP95Ms?: number | null;
  complete_p95_ms?: number | null;
  completeCount?: number;
  complete_count?: number;
  offlineFlushFail?: number;
  offline_flush_fail?: number;
  offlineEnqueue?: number;
  posLineAdded?: number;
  funnel?: {
    signup_completed?: number;
    signup_failed?: number;
    wizard_tax_confirmed?: number;
    wizard_completed?: number;
    invoice_complete?: number;
    invoice_complete_started?: number;
    invoice_complete_failed?: number;
    invoice_complete_failed_by_reason?: Record<string, number>;
    pdf_started?: number;
    pdf_failed?: number;
    pdf_failed_by_reason?: Record<string, number>;
    payment_started?: number;
    payment_completed?: number;
    payment_failed?: number;
    payment_failed_by_reason?: Record<string, number>;
    invoiceComplete?: number;
    invoiceCompleteStarted?: number;
    invoiceCompleteFailed?: number;
    invoiceCompleteFailedByReason?: Record<string, number>;
    signupCompleted?: number;
    signupFailed?: number;
    pdfStarted?: number;
    pdfFailed?: number;
    paymentStarted?: number;
    paymentCompleted?: number;
    paymentFailed?: number;
  };
};

export function funnelCount(
  funnel: ShopFloorSummary['funnel'] | undefined,
  snake: string,
  camel: string,
): number {
  if (!funnel) return 0;
  const rec = funnel as Record<string, unknown>;
  const value = rec[camel] ?? rec[snake];
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

export function funnelReasons(
  funnel: ShopFloorSummary['funnel'] | undefined,
  snake: string,
  camel: string,
): Record<string, number> {
  if (!funnel) return {};
  const rec = funnel as Record<string, unknown>;
  const value = rec[camel] ?? rec[snake];
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  return value as Record<string, number>;
}

export async function getShopFloorSummary(): Promise<ShopFloorSummary> {
  const { data } = await apiClient.get('/insights/telemetry/');
  return unwrapData<ShopFloorSummary>(data);
}
