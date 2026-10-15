import { useCallback, useRef, useState } from 'react';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { t } from '@/i18n';
import type { ReasonRequest } from '@/utils/confirmBridge';

/** In-app dialog that collects a written reason for an override. Render `dialog` once. */
export function useReasonPrompt() {
  const [request, setRequest] = useState<ReasonRequest | null>(null);
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState('');
  const resolver = useRef<((value: string | null) => void) | null>(null);

  const ask = useCallback(
    (next: ReasonRequest) =>
      new Promise<string | null>((resolve) => {
        resolver.current = resolve;
        setReason('');
        setRequest(next);
        setOpen(true);
      }),
    [],
  );

  const settle = (value: string | null) => {
    resolver.current?.(value);
    resolver.current = null;
    setOpen(false);
  };

  const dialog = (
    <Dialog open={open} onClose={() => settle(null)} aria-labelledby="reason-dialog-title" fullWidth maxWidth="sm">
      <DialogTitle id="reason-dialog-title">{request?.title ?? ''}</DialogTitle>
      <DialogContent>
        <Typography variant="body2" sx={{ whiteSpace: 'pre-line', mb: 2 }}>
          {request?.body ?? ''}
        </Typography>
        <TextField
          autoFocus
          fullWidth
          multiline
          minRows={2}
          label={request?.reasonLabel ?? ''}
          value={reason}
          onChange={(event) => setReason(event.target.value)}
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={() => settle(null)}>{t('common.cancel')}</Button>
        <Button variant="contained" color="warning" disabled={!reason.trim()} onClick={() => settle(reason.trim())}>
          {request?.confirmLabel ?? t('common.confirm')}
        </Button>
      </DialogActions>
    </Dialog>
  );
  return { ask, dialog };
}
