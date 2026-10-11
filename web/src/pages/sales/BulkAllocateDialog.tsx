import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Chip from '@mui/material/Chip';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useMutation } from '@tanstack/react-query';
import { getErrorMessage, userGestureIdempotencyKey } from '@/api/client';
import { bulkAllocateReceipts } from '@/api/resources';
import { t } from '@/i18n';
import { ActionDialog } from '@/pages/sales/ActionDialog';
import type { BulkAllocateResult, CustomerReceipt } from '@/types/domain';
import { formatMoney } from '@/utils/money';

/**
 * Apply several advances to their customers' oldest open bills in one go. The server takes them
 * per customer in date order, so two advances of one customer never fight over the same bills,
 * and reports one row per receipt: one that cannot be applied never stops the others.
 */
export function BulkAllocateDialog({
  receipts,
  onClose,
  onDone,
}: {
  receipts: CustomerReceipt[];
  onClose: () => void;
  onDone: () => void;
}) {
  // One key for the whole gesture, so a double click or a retry cannot apply anything twice.
  const [key] = useState(() => userGestureIdempotencyKey());
  const [results, setResults] = useState<BulkAllocateResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [errorSource, setErrorSource] = useState<unknown>(null);
  const byId = new Map(receipts.map((r) => [r.id, r]));

  const mutation = useMutation({
    mutationFn: () => bulkAllocateReceipts(receipts.map((r) => r.id), { idempotencyKey: key }),
    onSuccess: (rows) => {
      setResults(rows);
      onDone();
    },
    onError: (err) => {
      setError(getErrorMessage(err));
      setErrorSource(err);
    },
  });

  const count = (status: BulkAllocateResult['status']) => (results ?? []).filter((r) => r.status === status).length;

  return (
    <ActionDialog
      open
      title={t('receipts.bulkTitle')}
      onClose={onClose}
      onConfirm={results ? undefined : () => mutation.mutate()}
      confirmLabel={t('receipts.bulkRun')}
      pending={mutation.isPending}
      error={error}
      errorSource={errorSource}
      maxWidth="sm"
    >
      <Typography variant="body2">{t('receipts.bulkIntro')}</Typography>
      {results ? (
        <Alert severity={count('failed') ? 'warning' : 'success'}>
          {t('receipts.bulkDone', { applied: count('applied'), skipped: count('skipped'), failed: count('failed') })}
        </Alert>
      ) : null}
      <Stack spacing={0.75}>
        {(results ?? receipts.map((r) => ({ id: r.id, number: r.number ?? undefined, status: 'pending' }))).map((row) => {
          const receipt = byId.get(row.id);
          const label = `${row.number || receipt?.number || row.id} · ${receipt?.customerName ?? ''}`;
          const result = 'allocated' in row ? (row as BulkAllocateResult) : null;
          return (
            <Stack key={row.id} direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
              <Typography variant="body2">
                {label}
                {result?.message ? (
                  <Typography component="span" variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                    {result.message}
                  </Typography>
                ) : null}
              </Typography>
              {result ? (
                <Chip
                  size="small"
                  variant="outlined"
                  color={result.status === 'applied' ? 'success' : result.status === 'failed' ? 'error' : 'default'}
                  label={
                    result.status === 'applied'
                      ? t('receipts.bulkApplied', { amount: formatMoney(result.allocated) })
                      : result.status === 'skipped'
                        ? t('receipts.bulkSkipped')
                        : t('receipts.bulkFailed')
                  }
                />
              ) : (
                <Typography variant="body2">{formatMoney(receipt?.allocatable ?? receipt?.unallocated ?? 0)}</Typography>
              )}
            </Stack>
          );
        })}
      </Stack>
    </ActionDialog>
  );
}
