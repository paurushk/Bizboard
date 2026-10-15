import { getErrorCode, getErrorDetails } from '@/api/client';
import { t } from '@/i18n';
import { askReason, confirmAction, getGlobalConfirm } from '@/utils/confirmBridge';
import { gstinCancelledText } from '@/utils/overrideRetry';
import type { PurchasePayNow } from '@/types/domain';

export type CompleteExtra = {
  confirmBlankPos?: boolean;
  confirmGstinTotalChange?: boolean;
  confirmNoRcm?: boolean;
  confirmDuplicateBill?: boolean;
  confirmAdditionalDebit?: boolean;
  confirmPaidInvoice?: boolean;
  confirmPriceOverride?: boolean;
  /** Owner/Manager approval of a 3-way match difference, with a written reason. */
  confirmThreeWayOverride?: boolean;
  threeWayReason?: string;
  /** Owner/Accountant release of a cancelled-GSTIN ITC block, with a written reason. */
  gstinCancelOverride?: boolean;
  gstinCancelReason?: string;
  /** Owner-only DN-07 override of the invoice-value cap, with a written reason. */
  confirmExcessiveDebit?: boolean;
  excessiveDebitReason?: string;
  /** Purchase pay-at-entry; carried through every confirm retry unchanged. */
  payNow?: PurchasePayNow;
  /** Per-gesture key for the whole complete call (confirm retries derive their own). */
  idempotencyKey?: string;
};

type ConfirmFlag = Exclude<
  keyof CompleteExtra,
  'excessiveDebitReason' | 'payNow' | 'idempotencyKey' | 'threeWayReason' | 'gstinCancelReason'
>;

function confirmCodesFromError(err: unknown): string[] {
  if (typeof err !== 'object' || err === null) return [];
  const response = (err as { response?: { data?: Record<string, unknown> } }).response;
  const data = response?.data;
  const nested = data?.error;
  const details =
    nested && typeof nested === 'object'
      ? ((nested as { details?: Record<string, unknown> }).details ?? undefined)
      : undefined;
  const fromDetails =
    details && typeof details === 'object'
      ? (details.confirmCodes ?? details.confirm_codes)
      : undefined;
  const fromData = data?.confirmCodes ?? data?.confirm_codes;
  const raw = Array.isArray(fromDetails) ? fromDetails : fromData;
  if (!Array.isArray(raw)) return [];
  return raw.filter((c): c is string => typeof c === 'string' && Boolean(c.trim()));
}

/**
 * F2-017 / F2-035 / R-010: run a document "complete" call, and on known confirm
 * codes prompt the user and retry with the matching flag. Prefers a single 409
 * with `details.confirm_codes` (sets every flag, retries once). Still handles
 * one-code-at-a-time 409s. Loop bound is `len(flagFor) + 1`.
 */
/** Asks the user about every pending confirmation at once; resolves true to continue. */
export type ConfirmAsk = (messages: string[]) => Promise<boolean>;

export async function completeWithConfirms<T>(
  complete: (extra: CompleteExtra) => Promise<T>,
  base: CompleteExtra = {},
  // DN-04: an in-app dialog replaces window.confirm when the caller provides one.
  ask?: ConfirmAsk,
): Promise<T> {
  const confirmed: CompleteExtra = { ...base };
  const askUser = ask ?? getGlobalConfirm() ?? undefined;
  const prompts: Record<string, string> = {
    place_of_supply_unresolved: 'billing.confirmBlankPos',
    GSTIN_TOTAL_CHANGED: 'billing.confirmGstinTotalChange',
    confirm_no_rcm: 'billing.confirmNoRcm',
    confirm_duplicate_bill: 'billing.confirmDuplicateBill',
    confirm_additional_debit: 'billing.confirmAdditionalDebit',
    confirm_cn_on_paid_invoice: 'billing.confirmCnOnPaidInvoice',
    confirm_cn_price_override: 'billing.confirmCnPriceOverride',
  };
  const flagFor: Record<string, ConfirmFlag> = {
    place_of_supply_unresolved: 'confirmBlankPos',
    GSTIN_TOTAL_CHANGED: 'confirmGstinTotalChange',
    confirm_no_rcm: 'confirmNoRcm',
    confirm_duplicate_bill: 'confirmDuplicateBill',
    confirm_additional_debit: 'confirmAdditionalDebit',
    confirm_cn_on_paid_invoice: 'confirmPaidInvoice',
    confirm_cn_price_override: 'confirmPriceOverride',
  };
  for (let attempt = 0; attempt < Object.keys(flagFor).length + 3; attempt += 1) {
    try {
      return await complete(confirmed);
    } catch (err) {
      const bundled = confirmCodesFromError(err);
      const codes = bundled.length ? bundled : [getErrorCode(err) ?? ''];
      let progressed = false;
      // Overrides need a written reason (and the right role), so they get their own dialog.
      if (codes.includes('THREE_WAY_MATCH_FAILED') && !confirmed.confirmThreeWayOverride) {
        const details = getErrorDetails(err);
        if (details?.canOverride === false || details?.can_override === false) {
          throw new Error(t('billing.threeWayNoRole'), { cause: err });
        }
        const breaches = Array.isArray(details?.breaches) ? (details.breaches as unknown[]).map(String) : [];
        const reason = await askReason({
          title: t('billing.threeWayTitle'),
          body: t('billing.threeWayBody', { lines: breaches.join('\n') }),
          reasonLabel: t('billing.overrideReasonLabel'),
          confirmLabel: t('billing.threeWayApprove'),
        });
        if (!reason) throw err;
        confirmed.confirmThreeWayOverride = true;
        confirmed.threeWayReason = reason;
        continue;
      }
      if (codes.includes('SUPPLIER_GSTIN_CANCELLED') && !confirmed.gstinCancelOverride) {
        const reason = await askReason({
          ...gstinCancelledText(err, 'bill'),
          reasonLabel: t('billing.overrideReasonLabel'),
          confirmLabel: t('billing.gstinCancelledApprove'),
        });
        if (!reason) throw err;
        confirmed.gstinCancelOverride = true;
        confirmed.gstinCancelReason = reason;
        continue;
      }
      const pending = codes.filter((code) => flagFor[code] && !confirmed[flagFor[code]]);
      if (askUser && pending.length > 0) {
        if (!(await askUser(pending.map((code) => t(prompts[code]))))) throw err;
        for (const code of pending) confirmed[flagFor[code]] = true;
        progressed = true;
      } else {
        for (const code of codes) {
          const flag = flagFor[code];
          if (!flag || confirmed[flag]) continue;
          if (!(await confirmAction(t(prompts[code])))) throw err;
          confirmed[flag] = true;
          progressed = true;
        }
      }
      if (!progressed) throw err;
    }
  }
  return complete(confirmed);
}
