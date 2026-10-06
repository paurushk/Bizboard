import { useState } from 'react';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { t } from '@/i18n';

export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel,
  confirmColor = 'primary',
  confirming = false,
  requireTyped,
  onConfirm,
  onClose,
}: {
  open: boolean;
  title: string;
  body: string;
  confirmLabel?: string;
  confirmColor?: 'primary' | 'warning' | 'error';
  confirming?: boolean;
  /** When set, the user must type this text before confirm is enabled (BUG-UI-005). */
  requireTyped?: string;
  onConfirm: () => void;
  onClose: () => void;
}) {
  const [typed, setTyped] = useState('');
  if (!open && typed) setTyped('');
  // Typing is opt-in: only a destructive action that names what it destroys asks for it.
  // Falling back to the title would make every routine confirm (clear cart, move a deal) a typing task.
  const expected = (requireTyped ?? '').trim();
  const typedOk = !expected || typed.trim() === expected;
  return (
    <Dialog open={open} onClose={onClose} aria-labelledby="confirm-dialog-title">
      <DialogTitle id="confirm-dialog-title">{title}</DialogTitle>
      <DialogContent>
        <Typography variant="body2">{body}</Typography>
        {expected ? (
          <TextField
            autoFocus
            margin="dense"
            fullWidth
            label={expected}
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
            inputProps={{ 'aria-label': expected }}
          />
        ) : null}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={confirming}>{t('common.cancel')}</Button>
        <Button color={confirmColor} variant="contained" disabled={confirming || !typedOk} onClick={onConfirm}>
          {confirmLabel ?? t('common.confirm')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
