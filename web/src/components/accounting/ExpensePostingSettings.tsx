import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { getAccountingSettings, postPendingExpenses, updateAccountingSettings } from '@/api/resources';
import { todayIso } from '@/components/billing';
import { t } from '@/i18n';
import { formatMoney, toNumber } from '@/utils/money';

type Settings = {
  accountingEnabled?: boolean;
  expenseGlStartDate?: string | null;
  expenseGlPending?: { count?: number; total?: string | number };
};

/**
 * ACS-15: the owner picks the day expenses start posting to the ledger, previews what is
 * waiting, and posts it. Until a date is set, expenses stay a register only.
 */
export function ExpensePostingSettings({ disabled = false }: { disabled?: boolean }) {
  const qc = useQueryClient();
  const settings = useQuery({ queryKey: ['accounting-settings'], queryFn: getAccountingSettings, retry: false });
  const data = (settings.data ?? {}) as Settings;
  const startDate = data.expenseGlStartDate ?? null;
  const pending = data.expenseGlPending ?? {};
  const [date, setDate] = useState('');
  const [message, setMessage] = useState<{ severity: 'success' | 'error' | 'info'; text: string } | null>(null);

  const refresh = () => void qc.invalidateQueries({ queryKey: ['accounting-settings'] });
  const saveDate = useMutation({
    mutationFn: (value: string | null) => updateAccountingSettings({ expenseGlStartDate: value }),
    onSuccess: () => {
      setMessage(null);
      refresh();
    },
    onError: (err) => setMessage({ severity: 'error', text: getErrorMessage(err) }),
  });
  const post = useMutation({
    mutationFn: (dryRun: boolean) => postPendingExpenses(dryRun),
    onSuccess: (result) => {
      const values = { count: String(result.posted), total: formatMoney(toNumber(result.total)) };
      const lines = [t(result.dryRun ? 'expenses.glPreviewResult' : 'expenses.glPostedResult', values)];
      if (result.skipped.length) lines.push(t('expenses.glSkipped', { count: String(result.skipped.length) }));
      setMessage({ severity: result.skipped.length ? 'info' : 'success', text: lines.join(' ') });
      refresh();
      void qc.invalidateQueries({ queryKey: ['expenses'] });
    },
    onError: (err) => setMessage({ severity: 'error', text: getErrorMessage(err) }),
  });

  if (settings.isError || !data.accountingEnabled) return null;
  const pendingCount = Number(pending.count ?? 0);
  return (
    <Paper variant="outlined" sx={{ p: 3 }} data-testid="expense-posting-settings">
      <Stack spacing={2}>
        <Typography variant="h6">{t('expenses.glTitle')}</Typography>
        <Typography variant="body2" color="text.secondary">{t('expenses.glBody')}</Typography>
        {message ? <Alert severity={message.severity} onClose={() => setMessage(null)}>{message.text}</Alert> : null}
        <Typography variant="body2">
          {startDate ? t('expenses.glOn', { date: startDate }) : t('expenses.glOff')}
        </Typography>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ sm: 'center' }}>
          <TextField
            type="date"
            size="small"
            label={t('expenses.glStartDate')}
            InputLabelProps={{ shrink: true }}
            value={date || startDate || ''}
            onChange={(e) => setDate(e.target.value)}
            inputProps={{ max: todayIso() }}
          />
          <Button
            variant="contained"
            disabled={disabled || saveDate.isPending || !(date || startDate) || (date || startDate) === startDate}
            onClick={() => saveDate.mutate(date || null)}
          >
            {t('expenses.glSave')}
          </Button>
          {startDate ? (
            <Button disabled={disabled || saveDate.isPending} onClick={() => saveDate.mutate(null)}>
              {t('expenses.glTurnOff')}
            </Button>
          ) : null}
        </Stack>
        {startDate && pendingCount > 0 ? (
          <Stack spacing={1}>
            <Alert severity="warning">
              {t('expenses.glPending', { count: String(pendingCount), total: formatMoney(toNumber(pending.total)) })}
            </Alert>
            <Stack direction="row" spacing={1}>
              <Button disabled={post.isPending} onClick={() => post.mutate(true)}>{t('expenses.glPreview')}</Button>
              <Button variant="contained" disabled={disabled || post.isPending} onClick={() => post.mutate(false)}>
                {t('expenses.glPostPending')}
              </Button>
            </Stack>
          </Stack>
        ) : null}
      </Stack>
    </Paper>
  );
}
