import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { t } from '@/i18n';

export interface SuspendInput {
  reason: string;
  companyName: string;
  password: string;
  code: string;
}

/**
 * SET-06: suspending a workspace stops billing and, once the paid period ends, blocks all changes.
 * So it asks for a reason, the company name typed out, and the owner's password (plus a two-step
 * code if they use one). The server checks all of it again; this dialog only makes it hard to do by
 * accident.
 */
export function SuspendWorkspaceDialog({
  open,
  companyName,
  periodEnd,
  busy,
  error,
  onClose,
  onConfirm,
}: {
  open: boolean;
  /** The company's name exactly as it must be typed. */
  companyName: string;
  /** End of the paid period (ISO date) when there is one still running. */
  periodEnd: string | null;
  busy: boolean;
  error: string;
  onClose: () => void;
  onConfirm: (input: SuspendInput) => void;
}) {
  const [reason, setReason] = useState('');
  const [typed, setTyped] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const close = () => {
    setReason('');
    setTyped('');
    setPassword('');
    setCode('');
    onClose();
  };
  const nameOk = companyName.trim() !== '' && typed.trim().toLowerCase() === companyName.trim().toLowerCase();
  // Read the clock once per mount, not on every render.
  const [now] = useState(() => Date.now());
  const stillPaid = periodEnd !== null && new Date(periodEnd).getTime() > now;

  return (
    <Dialog open={open} onClose={close} fullWidth maxWidth="sm" aria-labelledby="suspend-workspace-title">
      <DialogTitle id="suspend-workspace-title">{t('billingDanger.dialogTitle')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Alert severity="warning">
            {stillPaid
              ? t('billingDanger.effectUntil', { date: String(periodEnd).slice(0, 10) })
              : t('billingDanger.effectNow')}
          </Alert>
          <Typography variant="body2" color="text.secondary">
            {t('billingDanger.effectCharges')}
          </Typography>
          <TextField
            label={t('sweep.churnReason')}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            required
            inputProps={{ maxLength: 255 }}
          />
          <TextField
            label={t('billingDanger.typeName', { name: companyName })}
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            autoComplete="off"
            helperText={companyName ? undefined : t('billingDanger.noName')}
          />
          <TextField
            label={t('billingDanger.password')}
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
          <TextField
            label={t('billingDanger.code')}
            value={code}
            onChange={(e) => setCode(e.target.value)}
            autoComplete="one-time-code"
            slotProps={{ htmlInput: { inputMode: 'numeric' } }}
          />
          {error ? <Alert severity="error">{error}</Alert> : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={close}>{t('common.cancel')}</Button>
        <Button
          color="error"
          variant="contained"
          disabled={busy || !reason.trim() || !nameOk || !password}
          onClick={() => onConfirm({ reason: reason.trim(), companyName: typed.trim(), password, code: code.trim() })}
        >
          {t('billingDanger.confirm')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
