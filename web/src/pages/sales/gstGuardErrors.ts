import { getErrorCode } from '@/api/client';

export interface GstGuardIssue {
  code: string;
  message: string;
}

/**
 * The blocking GST Guard issues carried by a `gst_guard_blocked` API error, or
 * null when the error is something else. One parser for every Complete flow.
 */
export function gstGuardIssuesFromError(err: unknown): GstGuardIssue[] | null {
  if (getErrorCode(err) !== 'gst_guard_blocked') return null;
  const data = (err as { response?: { data?: Record<string, unknown> } })?.response?.data;
  const nested = data?.error as { details?: { blocking?: unknown } } | undefined;
  const blocking = nested?.details?.blocking;
  return Array.isArray(blocking) ? (blocking as GstGuardIssue[]) : [];
}
