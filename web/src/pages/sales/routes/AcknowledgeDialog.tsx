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
import type { PlanRisk } from './planningTypes';

interface Props {
  open: boolean;
  /** What is being accepted, e.g. an order number. */
  title: string;
  risks: PlanRisk[];
  onConfirm: (reason: string) => void;
  onCancel: () => void;
}

/**
 * Accepting a risk is a decision, not a click-through: the dispatcher reads what they are accepting and writes
 * why. The reason is kept on the route and shown on the manifest (hardening plan PL-06, DEC-P3).
 */
export function AcknowledgeDialog({ open, title, risks, onConfirm, onCancel }: Props) {
  const [reason, setReason] = useState('');
  const ok = reason.trim().length >= 3;
  return (
    <Dialog open={open} onClose={onCancel} fullWidth maxWidth="sm" aria-labelledby="ack-title">
      <DialogTitle id="ack-title">{t('routes.plan.acceptTitle', { order: title })}</DialogTitle>
      <DialogContent>
        <Stack spacing={1.5} sx={{ mt: 1 }}>
          <Typography variant="body2">{t('routes.plan.acceptHelp')}</Typography>
          {risks.map((r) => (
            <Alert key={r.code} severity={r.level === 'block' ? 'error' : 'warning'}>
              {r.message}
            </Alert>
          ))}
          <TextField
            autoFocus
            size="small"
            required
            label={t('routes.plan.acceptReason')}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            helperText={t('routes.plan.acceptReasonHelp')}
            fullWidth
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={() => { setReason(''); onCancel(); }}>{t('common.cancel')}</Button>
        <Button
          variant="contained"
          disabled={!ok}
          onClick={() => {
            const value = reason.trim();
            setReason('');
            onConfirm(value);
          }}
        >
          {t('routes.plan.acceptButton')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
