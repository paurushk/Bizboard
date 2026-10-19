import axios from 'axios';
import { getErrorCode, getErrorMessage, isNetworkError } from '@/api/client';
import { t } from '@/i18n';

/**
 * SET-14: the cause and the fix for an error from a Settings endpoint, in the person's language.
 * A coded error (see `backend/core/settings_codes.py`) gets its own entry; any other error is
 * explained by its HTTP status, so every failure on a Settings screen says what to do next.
 */
export const SETTINGS_ERROR_CODES = ['SETTINGS_STALE', 'series_invalid', 'PRICE_LIST_IN_USE', 'UNIT_IN_USE', 'GATEWAY_KEYS_REFUSED', 'GATEWAY_PROVIDER_DISABLED', 'GATEWAY_ADDRESS_UNSUPPORTED', 'GATEWAY_CHECK_TOO_SOON', 'ACCOUNTING_PERIOD_CLOSED', 'ACCOUNTING_BACKFILL_RUNNING', 'REASON_REQUIRED', 'ACKNOWLEDGE_REQUIRED', 'PASSWORD_NOT_SET', 'REAUTH_LOCKED', 'CHURN_REASON_REQUIRED', 'COMPANY_NAME_MISMATCH', 'ALREADY_SUSPENDED', 'RESTORE_LIVE_DISABLED', 'LICENCE_LOCKED', 'LICENCE_INACTIVE', 'LICENCE_UNCHANGED'] as const;

export type SettingsErrorAdvice = { cause: string; fix: string };

function entry(key: string): SettingsErrorAdvice {
  return { cause: t(`settingsErrors.${key}.cause`), fix: t(`settingsErrors.${key}.fix`) };
}

function statusKey(status: number | undefined): string {
  if (status === 401) return 'status_signedOut';
  if (status === 403) return 'status_forbidden';
  if (status === 404) return 'status_notFound';
  if (status === 409) return 'status_conflict';
  if (status === 413) return 'status_tooLarge';
  if (status === 429) return 'status_slowDown';
  if (status !== undefined && status >= 500) return 'status_server';
  return 'status_rejected';
}

export function settingsErrorAdvice(error: unknown): SettingsErrorAdvice | null {
  if (error == null) return null;
  const code = getErrorCode(error);
  if (code && (SETTINGS_ERROR_CODES as readonly string[]).includes(code)) return entry(`code_${code}`);
  if (isNetworkError(error)) return entry('status_offline');
  if (axios.isAxiosError(error)) return entry(statusKey(error.response?.status));
  return null;
}

/**
 * The server's message, then what to do next, as one sentence for screens that keep errors as text.
 * Cause is left to the message itself; the fix is what the catalogue adds.
 */
export function settingsErrorText(error: unknown): string {
  const advice = settingsErrorAdvice(error);
  // A signed-out answer is "Authentication credentials were not provided": say what happened instead.
  if (advice && axios.isAxiosError(error) && error.response?.status === 401) return `${advice.cause} ${t('settingsErrors.fix')}: ${advice.fix}`;
  const message = getErrorMessage(error);
  return advice ? `${message} ${t('settingsErrors.fix')}: ${advice.fix}` : message;
}
