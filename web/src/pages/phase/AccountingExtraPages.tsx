import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import * as api from '@/api/resources';
import { t } from '@/i18n';
import { ConfirmDialog } from '@/components/ConfirmDialog';
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
  const flash = (text: string, severity: 'success' | 'error' = 'success') => {
    setMsg(text);
    setMsgSeverity(severity);
  };
  const m = useMutation({
    mutationFn: (enabled: boolean) => api.updateAccountingSettings({ accountingEnabled: enabled }),
    onSuccess: (data) => {
      const enabled = Boolean((data as Row)?.accountingEnabled ?? (data as Row)?.accounting_enabled);
      flash(enabled ? t('acctSettings.enabled') : t('acctSettings.disabled'));
      void qc.invalidateQueries();
    },
    onError: (e) => flash(getErrorMessage(e), 'error'),
  });
  return (
    <PageShell title={t('phase.accounting')} subtitle={t('phase.accountingSubtitle')}>
      <AccountingBackfillBanner />
      {msg ? <Alert severity={msgSeverity} onClose={() => setMsg('')}>{msg}</Alert> : null}
      <Paper variant="outlined" sx={{ p: 3 }}>
        <Stack spacing={2}>
          <Alert severity="info">{t('acctSettings.enableFirst')}</Alert>
          <Alert severity="warning">{t('acctSettings.backfillWarning')}</Alert>
          <Stack direction="row" spacing={1}>
            <Button variant="contained" disabled={writesBlocked || m.isPending} onClick={() => m.mutate(true)}>
              {t('sweep2.enableAccounting')}
            </Button>
            <Button variant="outlined" disabled={writesBlocked || m.isPending} onClick={() => setConfirmDisable(true)}>
              {t('sweep2.disable')}
            </Button>
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
      <ConfirmDialog
        open={confirmDisable}
        title={t('sweep2.disable')}
        body={t('phase.confirmDisableAccounting')}
        confirmLabel={t('sweep2.disable')}
        confirmColor="error"
        confirming={m.isPending}
        onClose={() => setConfirmDisable(false)}
        onConfirm={() => {
          setConfirmDisable(false);
          m.mutate(false);
        }}
      />
    </PageShell>
  );
}
