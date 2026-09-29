import { useEffect, useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import {
  getAccountingBackfillStatus,
  getAccountingSettings,
  postAccountingBackfill,
} from '@/api/resources';
import { t } from '@/i18n';

type BackfillPayload = Record<string, unknown>;

function pick(payload: BackfillPayload, camel: string, snake: string): unknown {
  return payload[camel] ?? payload[snake];
}

function describe(payload: BackfillPayload): string {
  const count = String(pick(payload, 'wouldPost', 'would_post') ?? pick(payload, 'posted', 'posted') ?? 0);
  const balanced = pick(payload, 'trialBalanceBalanced', 'trial_balance_balanced') ? 'ties' : 'does not tie';
  const variance = String(pick(payload, 'inventoryVariance', 'inventory_variance') ?? '0');
  return t('phase.accountingBackfillPreviewResult', { count, balanced, variance });
}

export function AccountingBackfillBanner() {
  const qc = useQueryClient();
  const [preview, setPreview] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const query = useQuery({
    queryKey: ['accounting-settings'],
    queryFn: getAccountingSettings,
    staleTime: 30_000,
  });
  const data = (query.data ?? {}) as Record<string, unknown>;
  const needed = Boolean(data.accountingBackfillNeeded ?? data.accounting_backfill_needed);

  // A confirmed back-fill runs as a background job. Poll its status until it
  // finishes, then refresh the settings so the banner reflects the real state.
  const status = useQuery({
    queryKey: ['accounting-backfill-status'],
    queryFn: getAccountingBackfillStatus,
    enabled: running,
    refetchInterval: running ? 2000 : false,
  });
  const jobStatus = String((status.data as BackfillPayload | undefined)?.status ?? '');
  useEffect(() => {
    if (!running) return;
    if (jobStatus === 'done') {
      setRunning(false);
      setError(null);
      setPreview(describe(status.data as BackfillPayload));
      void qc.invalidateQueries({ queryKey: ['accounting-settings'] });
    } else if (jobStatus === 'failed') {
      setRunning(false);
      setError(String((status.data as BackfillPayload).error ?? t('phase.accountingBackfillFailed')));
    }
  }, [running, jobStatus, status.data, qc]);

  const run = useMutation({
    mutationFn: (confirm: boolean) =>
      postAccountingBackfill(confirm ? { confirm: true } : { dry_run: true }),
    onSuccess: async (payload, confirm) => {
      setError(null);
      const state = String(payload.status ?? '');
      if (confirm && state === 'running') {
        setPreview(null);
        setRunning(true);
        return;
      }
      setPreview(describe(payload));
      if (confirm) {
        await qc.invalidateQueries({ queryKey: ['accounting-settings'] });
      }
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  if (!needed && !preview && !running && !error) return null;
  const busy = run.isPending || running;
  return (
    <Alert
      severity={error ? 'error' : needed ? 'warning' : 'success'}
      sx={{ mb: 2 }}
      action={
        needed ? (
          <Stack direction="row" spacing={1}>
            <Button color="inherit" size="small" disabled={busy} onClick={() => run.mutate(false)}>
              {t('phase.accountingBackfillPreview')}
            </Button>
            <Button color="inherit" size="small" disabled={busy} onClick={() => run.mutate(true)}>
              {t('phase.accountingBackfillPost')}
            </Button>
          </Stack>
        ) : undefined
      }
    >
      {needed ? t('phase.accountingBackfillNeeded') : null}
      {running ? ` ${t('phase.accountingBackfillRunning')}` : null}
      {preview ? ` ${preview}` : null}
      {error ? ` ${error}` : null}
    </Alert>
  );
}
