import Link from '@mui/material/Link';
import { Link as RouterLink } from 'react-router-dom';
import { t } from '@/i18n';
import { useFeatureFlagEpoch } from '@/config/featureFlags';
import { isHelpV2Enabled } from '@/config/features';
import { intentForErrorCode, leafForErrorCode } from './intents';

export function HelpWhyLink({
  code,
  invoiceId,
}: {
  code?: string | null;
  /** Ignored — unmapped errors must not put party/amount text in the URL. */
  message?: string | null;
  invoiceId?: string | number;
}) {
  useFeatureFlagEpoch();
  if (!isHelpV2Enabled()) return null;
  const intentId = intentForErrorCode(code ?? undefined);
  const leaf = leafForErrorCode(code ?? undefined);
  const params = new URLSearchParams();
  if (intentId) {
    params.set('intent', intentId);
    if (leaf) params.set('leaf', leaf);
  } else if (code) {
    params.set('q', code.slice(0, 64));
  }
  params.set('source', 'error');
  if (invoiceId != null && invoiceId !== '') params.set('invoiceId', String(invoiceId));
  if (code && intentId === 'edit-completed-invoice') params.set('from', 'cancel');
  return (
    <Link
      component={RouterLink}
      to={`/help?${params.toString()}`}
      variant="body2"
      sx={{ ml: 1, fontWeight: 600 }}
    >
      {t('help.why')}
    </Link>
  );
}
