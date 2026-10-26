import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getCompany, updateCompany } from '@/api/resources';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { t } from '@/i18n';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';

const MIN_DAYS = 30;
const MAX_DAYS = 3650;

function formatDate(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? String(iso) : d.toLocaleDateString();
}

/**
 * D-13: how long a read-only account's data is kept before deletion (owner-set, default 90 days),
 * and, once the account is read-only, the date it will be deleted. Owners only (shown inside the
 * owner section of Backup / Export).
 */
export function DataRetentionPanel() {
  const qc = useQueryClient();
  const { writesBlocked } = useSubscriptionGate();
  const company = useQuery({ queryKey: ['company'], queryFn: getCompany });
  const [draft, setDraft] = useState<string | null>(null);
  const current = company.data?.dataRetentionDays ?? 90;
  const value = draft ?? String(current);
  const days = Number(value);
  const valid = Number.isInteger(days) && days >= MIN_DAYS && days <= MAX_DAYS;
  const save = useMutation({
    mutationFn: () =>
      updateCompany({
        dataRetentionDays: days,
        ...(company.data?.updatedAt ? { expected_updated_at: company.data.updatedAt } : {}),
      } as never),
    onSuccess: () => {
      setDraft(null);
      void qc.invalidateQueries({ queryKey: ['company'] });
    },
  });

  if (!company.data) return null;
  const due = company.data.dataDeletionDueAt;
  return (
    <Stack spacing={1.5}>
      <Typography variant="h6" sx={{ pt: 1 }}>{t('backupPage.retention.title')}</Typography>
      {due ? (
        <Alert severity="warning">
          {t('backupPage.retention.readOnly', {
            since: formatDate(company.data.readOnlySince),
            due: formatDate(due),
          })}
        </Alert>
      ) : null}
      <Typography variant="body2" color="text.secondary">{t('backupPage.retention.help')}</Typography>
      <Stack direction="row" spacing={1} alignItems="flex-start" flexWrap="wrap" useFlexGap>
        <TextField
          size="small"
          type="number"
          label={t('backupPage.retention.days')}
          value={value}
          onChange={(e) => setDraft(e.target.value)}
          disabled={writesBlocked}
          error={!valid}
          helperText={t('backupPage.retention.range')}
          inputProps={{ min: MIN_DAYS, max: MAX_DAYS, step: 1 }}
          sx={{ width: 200 }}
        />
        <Button
          variant="outlined"
          disabled={writesBlocked || !valid || days === current || save.isPending}
          onClick={() => save.mutate()}
        >
          {t('backupPage.retention.save')}
        </Button>
      </Stack>
      {writesBlocked ? (
        <Typography variant="caption" color="text.secondary">{t('backupPage.retention.blockedNote')}</Typography>
      ) : null}
      {save.isSuccess ? <Typography variant="caption" color="success.main">{t('backupPage.retention.saved')}</Typography> : null}
      {save.isError ? <HelpErrorAlert error={save.error} /> : null}
    </Stack>
  );
}
