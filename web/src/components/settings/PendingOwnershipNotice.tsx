import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { cancelOwnershipTransfer, getPendingOwnership } from '@/api/ownership';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { t } from '@/i18n';

const KEY = ['ownership-pending'];

/**
 * WP-ID1 (owners): an ownership offer or a staff owner-recovery that is waiting, with a Cancel
 * button. The recovery email tells every owner they can cancel it here within 72 hours.
 */
export function PendingOwnershipNotice() {
  const qc = useQueryClient();
  const pending = useQuery({ queryKey: KEY, queryFn: getPendingOwnership, retry: false });
  const cancel = useMutation({
    mutationFn: cancelOwnershipTransfer,
    onSuccess: () => void qc.invalidateQueries({ queryKey: KEY }),
  });
  const row = pending.data?.pending;
  if (!row) return cancel.isError ? <HelpErrorAlert error={cancel.error} /> : null;
  const until = new Date(row.effectiveAt || row.expiresAt).toLocaleString();
  return (
    <>
      <Alert
        severity="warning"
        action={
          <Button color="inherit" size="small" disabled={cancel.isPending} onClick={() => cancel.mutate()}>
            {t('ownership.pendingCancel')}
          </Button>
        }
      >
        {row.kind === 'STAFF_RECOVERY'
          ? t('ownership.pendingRecovery', { email: row.toEmail, until })
          : t('ownership.pendingOffer', { email: row.toEmail, until })}
      </Alert>
      {cancel.isError ? <HelpErrorAlert error={cancel.error} /> : null}
    </>
  );
}
