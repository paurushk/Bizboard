import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Stack from '@mui/material/Stack';
import useMediaQuery from '@mui/material/useMediaQuery';
import { useTheme } from '@mui/material/styles';
import type { ReactNode } from 'react';
import { t } from '@/i18n';

/**
 * A "New X" form that stays out of the way until asked for (UX-M07). Full screen on a phone so the
 * keyboard never covers the submit button; a normal dialog otherwise.
 */
export function CreateDialog({
  open,
  onClose,
  title,
  submitLabel,
  onSubmit,
  submitDisabled = false,
  dirty = false,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  submitLabel: string;
  onSubmit: () => void;
  submitDisabled?: boolean;
  dirty?: boolean;
  children: ReactNode;
}) {
  const theme = useTheme();
  const fullScreen = useMediaQuery(theme.breakpoints.down('sm'));
  const requestClose = () => {
    if (dirty && !window.confirm(t('billing.unsavedBody'))) return;
    onClose();
  };
  return (
    <Dialog open={open} onClose={requestClose} fullWidth maxWidth="sm" fullScreen={fullScreen} aria-labelledby="create-dialog-title">
      <DialogTitle id="create-dialog-title">{title}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          {children}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={requestClose}>{t('common.cancel')}</Button>
        <Button variant="contained" disabled={submitDisabled} onClick={onSubmit}>
          {submitLabel}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
