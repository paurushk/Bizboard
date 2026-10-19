import { t } from '@/i18n';
import { formatColumnHeader } from '@/utils/reportFormat';

/** Keys that are plumbing, not something a person reads. */
const HIDDEN = new Set(['id', 'company', 'company_id', 'companyId', 'user', 'user_id', 'userId']);

function readable(value: unknown): string | null {
  if (value === null || value === undefined || value === '') return null;
  if (typeof value === 'object') return null;
  if (typeof value === 'boolean') return value ? t('common.yes') : t('common.no');
  return String(value);
}

/**
 * RPT-12: the payload of a statutory event as words ("Irn: abc · Ack No: 123"), not "irn=abc, ack_no=123".
 * Nested objects and ids are left out; only the first four readable fields are shown.
 */
export function payloadSummary(payload: unknown): string {
  if (!payload || typeof payload !== 'object') return '—';
  const parts: string[] = [];
  for (const [key, value] of Object.entries(payload as Record<string, unknown>)) {
    if (HIDDEN.has(key)) continue;
    const text = readable(value);
    if (text === null) continue;
    parts.push(`${formatColumnHeader(key)}: ${text}`);
    if (parts.length === 4) break;
  }
  return parts.length ? parts.join(' · ') : '—';
}
