import { getErrorCode } from '@/api/client';
import { t } from '@/i18n';

type CompleteExtra = { confirmBlankPos?: boolean; confirmGstinTotalChange?: boolean };

/**
 * F2-017 / F2-035: run a document "complete" call, and on a known confirm code
 * (`place_of_supply_unresolved`, `GSTIN_TOTAL_CHANGED`) prompt the user and
 * retry with the matching confirm flag. Loops so codes can arrive in any order
 * and each is only prompted once. Shared by every Complete entry point (editors
 * and the history-list menus) so they behave the same.
 */
export async function completeWithConfirms<T>(
  complete: (extra: CompleteExtra) => Promise<T>,
  base: CompleteExtra = {},
): Promise<T> {
  const confirmed: CompleteExtra = { ...base };
  const prompts: Record<string, string> = {
    place_of_supply_unresolved: 'billing.confirmBlankPos',
    GSTIN_TOTAL_CHANGED: 'billing.confirmGstinTotalChange',
  };
  const flagFor: Record<string, keyof CompleteExtra> = {
    place_of_supply_unresolved: 'confirmBlankPos',
    GSTIN_TOTAL_CHANGED: 'confirmGstinTotalChange',
  };
  // At most one prompt per known code, plus the initial attempt.
  for (let attempt = 0; attempt < Object.keys(prompts).length + 1; attempt += 1) {
    try {
      return await complete(confirmed);
    } catch (err) {
      const code = getErrorCode(err) ?? '';
      const flag = flagFor[code];
      if (!flag || confirmed[flag] || !window.confirm(t(prompts[code]))) {
        throw err;
      }
      confirmed[flag] = true;
    }
  }
  // Unreachable in practice — the loop either returns or throws.
  return complete(confirmed);
}
