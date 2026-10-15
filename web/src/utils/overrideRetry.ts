import { getErrorCode, getErrorDetails } from '@/api/client';
import { t } from '@/i18n';
import { askReason } from '@/utils/confirmBridge';

export type GstinHoldOverride = { gstinHoldOverride?: boolean; gstinHoldReason?: string };

/** Text for the cancelled-GSTIN dialog, from the details the server attaches to the refusal. */
export function gstinCancelledText(err: unknown, kind: 'bill' | 'pay'): { title: string; body: string } {
  const details = getErrorDetails(err);
  const supplier = String(details?.supplierName ?? details?.supplier_name ?? '');
  const date = String(details?.cancelledOn ?? details?.cancelled_on ?? '');
  return {
    title: t('billing.gstinCancelledTitle'),
    body: t(kind === 'pay' ? 'billing.gstinCancelledPayBody' : 'billing.gstinCancelledBillBody', { supplier, date }),
  };
}

/**
 * Run a payment call; if the server holds it because the supplier's GSTIN is cancelled, ask an
 * Owner/Accountant for a written reason and retry once with the override. Any other error, a
 * declined dialog, or a role the server refuses, surfaces the original error unchanged.
 */
export async function withGstinHoldOverride<T>(run: (override: GstinHoldOverride) => Promise<T>): Promise<T> {
  try {
    return await run({});
  } catch (err) {
    if (getErrorCode(err) !== 'SUPPLIER_GSTIN_CANCELLED') throw err;
    const reason = await askReason({
      ...gstinCancelledText(err, 'pay'),
      reasonLabel: t('billing.overrideReasonLabel'),
      confirmLabel: t('billing.gstinCancelledApprove'),
    });
    if (!reason) throw err;
    return run({ gstinHoldOverride: true, gstinHoldReason: reason });
  }
}
