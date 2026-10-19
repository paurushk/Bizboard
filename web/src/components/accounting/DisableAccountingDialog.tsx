import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import FormControlLabel from '@mui/material/FormControlLabel';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import * as api from '@/api/resources';
import { AsyncSection } from '@/components/settings/AsyncSection';
import { t } from '@/i18n';

/**
 * SET-07: switching the books off is not a one-click undo, so the owner first sees what it does
 * (entries already posted, closed periods, a back-fill in progress), is stopped where it would leave
 * a permanent gap, and has to say why. The server enforces the same rules.
 */
export function DisableAccountingDialog({
  open,
  busy,
  error,
  onClose,
  onConfirm,
}: {
  open: boolean;
  busy: boolean;
  error: string;
  onClose: () => void;
  onConfirm: (input: { reason: string; acknowledge: boolean }) => void;
}) {
  const [reason, setReason] = useState('');
  const [understood, setUnderstood] = useState(false);
  const query = useQuery({
    queryKey: ['accounting-disable-preflight'],
    queryFn: api.getAccountingDisablePreflight,
    enabled: open,
    gcTime: 0,
  });
  const close = () => {
    setReason('');
    setUnderstood(false);
    onClose();
  };

  return (
    <Dialog open={open} onClose={close} fullWidth maxWidth="sm" aria-labelledby="disable-accounting-title">
      <DialogTitle id="disable-accounting-title">{t('acctSettings.dialogTitle')}</DialogTitle>
      <DialogContent>
        <AsyncSection query={query}>
          {(info) => {
            const needsAck = info.postedJournals > 0;
            const blocked = !info.canDisable;
            return (
              <Stack spacing={2} sx={{ mt: 1 }}>
                <Typography variant="body2">{t('acctSettings.whatItDoes')}</Typography>
                <Typography variant="body2" color="text.secondary">
                  {info.postedJournals > 0
                    ? t('acctSettings.entriesPosted', {
                        count: String(info.postedJournals),
                        from: info.firstEntryDate ?? '',
                        to: info.lastEntryDate ?? '',
                      })
                    : t('acctSettings.noEntries')}
                </Typography>
                {info.softClosedPeriods > 0 ? (
                  <Alert severity="info">{t('acctSettings.softClosed', { count: String(info.softClosedPeriods) })}</Alert>
                ) : null}
                {info.blockers.includes('closed_period') ? (
                  <Alert severity="error">
                    {t('acctSettings.blockedClosed', { date: info.latestClosedPeriodEnd ?? '' })}
                  </Alert>
                ) : null}
                {info.blockers.includes('backfill_running') ? (
                  <Alert severity="error">{t('acctSettings.blockedBackfill')}</Alert>
                ) : null}
                {!blocked ? (
                  <>
                    <TextField
                      label={t('acctSettings.reasonLabel')}
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                      inputProps={{ maxLength: 200 }}
                      required
                    />
                    {needsAck ? (
                      <FormControlLabel
                        control={<Checkbox checked={understood} onChange={(e) => setUnderstood(e.target.checked)} />}
                        label={t('acctSettings.understand')}
                      />
                    ) : null}
                  </>
                ) : null}
                {error ? <Alert severity="error">{error}</Alert> : null}
              </Stack>
            );
          }}
        </AsyncSection>
      </DialogContent>
      <DialogActions>
        <Button onClick={close}>{t('common.cancel')}</Button>
        <Button
          color="error"
          variant="contained"
          disabled={
            busy ||
            !query.data ||
            !query.data.canDisable ||
            reason.trim() === '' ||
            (query.data.postedJournals > 0 && !understood)
          }
          onClick={() => onConfirm({ reason: reason.trim(), acknowledge: understood })}
        >
          {t('acctSettings.switchOff')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
