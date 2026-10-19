import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import Chip from '@mui/material/Chip';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import * as api from '@/api/resources';
import { t } from '@/i18n';
import { DisableAccountingDialog } from '@/components/accounting/DisableAccountingDialog';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { AccountingBackfillBanner } from '@/components/AccountingBackfillBanner';
import { ExpensePostingSettings } from '@/components/accounting/ExpensePostingSettings';
import {
  PageShell,
  type Row,
} from '@/pages/phase/phaseShared';


export function AccountingSettingsPage() {
  const { writesBlocked } = useSubscriptionGate();
  const qc = useQueryClient();
  const [msg, setMsg] = useState('');
  // F3-026: track severity so a mutation error isn't shown as a blue "info".
  const [msgSeverity, setMsgSeverity] = useState<'success' | 'error'>('success');
  const [confirmDisable, setConfirmDisable] = useState(false);
  const [disableError, setDisableError] = useState('');
  const state = useQuery({ queryKey: ['accounting-settings'], queryFn: api.getAccountingSettings });
  const booksOn = Boolean(
    (state.data as Row | undefined)?.accountingEnabled ?? (state.data as Row | undefined)?.accounting_enabled,
  );
  const flash = (text: string, severity: 'success' | 'error' = 'success') => {
    setMsg(text);
    setMsgSeverity(severity);
  };
  const m = useMutation({
    mutationFn: (input: { enabled: boolean; reason?: string; acknowledge?: boolean }) =>
      api.updateAccountingSettings({
        accountingEnabled: input.enabled,
        ...(input.enabled ? {} : { reason: input.reason, acknowledge: input.acknowledge }),
      }),
    onSuccess: (data) => {
      const enabled = Boolean((data as Row)?.accountingEnabled ?? (data as Row)?.accounting_enabled);
      flash(enabled ? t('acctSettings.enabled') : t('acctSettings.disabled'));
      setConfirmDisable(false);
      setDisableError('');
      void qc.invalidateQueries();
    },
    onError: (e) => {
      // Inside the switch-off dialog the reason is shown there; elsewhere it is the page banner.
      if (confirmDisable) setDisableError(getErrorMessage(e));
      else flash(getErrorMessage(e), 'error');
    },
  });
  return (
    <PageShell title={t('phase.accounting')} subtitle={t('phase.accountingSubtitle')}>
      <AccountingBackfillBanner />
      {msg ? <Alert severity={msgSeverity} onClose={() => setMsg('')}>{msg}</Alert> : null}
      <Paper variant="outlined" sx={{ p: 3 }}>
        <Stack spacing={2}>
          <Alert severity="info">{t('acctSettings.enableFirst')}</Alert>
          <Alert severity="warning">{t('acctSettings.backfillWarning')}</Alert>
          <Stack direction="row" spacing={1} alignItems="center">
            {state.data ? (
              <Chip
                color={booksOn ? 'success' : 'default'}
                label={booksOn ? t('acctSettings.statusOn') : t('acctSettings.statusOff')}
              />
            ) : null}
            {!booksOn ? (
              <Button
                variant="contained"
                disabled={writesBlocked || m.isPending || state.isLoading}
                onClick={() => m.mutate({ enabled: true })}
              >
                {t('sweep2.enableAccounting')}
              </Button>
            ) : (
              <Button
                variant="outlined"
                color="error"
                disabled={writesBlocked || m.isPending}
                onClick={() => {
                  setDisableError('');
                  setConfirmDisable(true);
                }}
              >
                {t('acctSettings.switchOffButton')}
              </Button>
            )}
          </Stack>
        </Stack>
      </Paper>
      <Stack sx={{ mt: 2 }}>
        <ExpensePostingSettings disabled={writesBlocked} />
      </Stack>
      <Paper variant="outlined" sx={{ p: 3, mt: 2 }}>
        <Stack spacing={2}>
          <Typography variant="h6">{t('sweep2.closeFy')}</Typography>
          <Typography variant="body2" color="text.secondary">{t('phase.fyCloseElsewhere')}</Typography>
          <Button component={RouterLink} to="/accounting/periods" variant="outlined" sx={{ alignSelf: 'flex-start' }}>
            {t('phase.openPeriods')}
          </Button>
        </Stack>
      </Paper>
      <DisableAccountingDialog
        open={confirmDisable}
        busy={m.isPending}
        error={disableError}
        onClose={() => setConfirmDisable(false)}
        onConfirm={({ reason, acknowledge }) => m.mutate({ enabled: false, reason, acknowledge })}
      />
    </PageShell>
  );
}
