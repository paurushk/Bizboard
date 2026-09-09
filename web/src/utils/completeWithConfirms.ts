import { getErrorCode } from '@/api/client';
import { t } from '@/i18n';

export type CompleteExtra = {
  confirmBlankPos?: boolean;
  confirmGstinTotalChange?: boolean;
  confirmNoRcm?: boolean;
  confirmDuplicateBill?: boolean;
  confirmAdditionalDebit?: boolean;
  confirmPaidInvoice?: boolean;
  confirmPriceOverride?: boolean;
};

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
export async function completeWithConfirms<T>(
  complete: (extra: CompleteExtra) => Promise<T>,
  base: CompleteExtra = {},
): Promise<T> {
  const confirmed: CompleteExtra = { ...base };
  const prompts: Record<string, string> = {
    place_of_supply_unresolved: 'billing.confirmBlankPos',
    GSTIN_TOTAL_CHANGED: 'billing.confirmGstinTotalChange',
    confirm_no_rcm: 'billing.confirmNoRcm',
    confirm_duplicate_bill: 'billing.confirmDuplicateBill',
    confirm_additional_debit: 'billing.confirmAdditionalDebit',
    confirm_cn_on_paid_invoice: 'billing.confirmCnOnPaidInvoice',
    confirm_cn_price_override: 'billing.confirmCnPriceOverride',
  };
  const flagFor: Record<string, keyof CompleteExtra> = {
    place_of_supply_unresolved: 'confirmBlankPos',
    GSTIN_TOTAL_CHANGED: 'confirmGstinTotalChange',
    confirm_no_rcm: 'confirmNoRcm',
    confirm_duplicate_bill: 'confirmDuplicateBill',
    confirm_additional_debit: 'confirmAdditionalDebit',
    confirm_cn_on_paid_invoice: 'confirmPaidInvoice',
    confirm_cn_price_override: 'confirmPriceOverride',
  };
  for (let attempt = 0; attempt < Object.keys(flagFor).length + 1; attempt += 1) {
    try {
      return await complete(confirmed);
    } catch (err) {
      const bundled = confirmCodesFromError(err);
      const codes = bundled.length ? bundled : [getErrorCode(err) ?? ''];
      let progressed = false;
      for (const code of codes) {
        const flag = flagFor[code];
        if (!flag || confirmed[flag]) continue;
        if (!window.confirm(t(prompts[code]))) throw err;
        confirmed[flag] = true;
        progressed = true;
      }
      if (!progressed) throw err;
    }
  }
  return complete(confirmed);
}
