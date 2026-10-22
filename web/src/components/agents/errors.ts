import { getErrorCode, getErrorMessage } from '@/api/client';
import { t } from '@/i18n';

/** Map a failed agents call to one calm sentence in the user's language; fall back to the server message. */
export function agentErrorText(error: unknown): string {
  const code = getErrorCode(error);
  if (code && code.startsWith('AGT_E_')) {
    const key = `agents.errors.${code}`;
    const text = t(key);
    if (text !== key) return text;
  }
  const message = getErrorMessage(error);
  return message || t('agents.errors.generic');
}

export function isStaleOrExpired(error: unknown): boolean {
  const code = getErrorCode(error);
  return code === 'AGT_E_STALE' || code === 'AGT_E_EXPIRED' || code === 'AGT_E_ATTEMPTS';
}
