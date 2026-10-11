import Alert from '@mui/material/Alert';
import { t } from '@/i18n';
import { formatMoney } from '@/utils/money';

/** Advance tax is reported, not posted: say how far the books differ from the return because of it. */
export function AdvanceGstAlert({ data }: { data: Record<string, unknown> }) {
  const tie = (data.advanceGst ?? data.advance_gst) as Record<string, unknown> | undefined;
  if (!tie || tie.enabled !== true) return null;
  const difference = String(tie.differenceFromBooks ?? tie.difference_from_books ?? '0.00');
  return (
    <Alert severity="info">
      {t('gstHonesty.advanceGstNotPosted', { amount: formatMoney(difference) })}
    </Alert>
  );
}
