import type { ReactNode } from 'react';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Stack from '@mui/material/Stack';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { t } from '@/i18n';

type Props = {
  open: boolean;
  title: string;
  onClose: () => void;
  /** Omit for a read-only dialog (Close only). */
  onConfirm?: () => void;
  confirmLabel?: string;
  confirmDisabled?: boolean;
  confirmColor?: 'primary' | 'warning' | 'error';
  pending?: boolean;
  error?: string | null;
  errorSource?: unknown;
  maxWidth?: 'xs' | 'sm' | 'md';
  children: ReactNode;
};

/**
 * The shell shared by the Money In dialogs that ask for a reason or a few fields: a title, a
 * body, the server's refusal shown inside the dialog (not on the page behind it), and Cancel and
 * confirm buttons that cannot be double-clicked while a request is running.
 */
export function ActionDialog({
  open,
  title,
  onClose,
  onConfirm,
  confirmLabel,
  confirmDisabled,
  confirmColor = 'primary',
  pending,
  error,
  errorSource,
  maxWidth = 'xs',
  children,
}: Props) {
  return (
    <Dialog open={open} onClose={() => (pending ? undefined : onClose())} fullWidth maxWidth={maxWidth}>
      <DialogTitle>{title}</DialogTitle>
      <DialogContent>
        <Stack spacing={1.5} sx={{ mt: 1 }}>
          {error ? <HelpErrorAlert message={error} error={errorSource} /> : null}
          {children}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={pending}>
          {onConfirm ? t('common.cancel') : t('common.close')}
        </Button>
        {onConfirm ? (
          <Button
            variant="contained"
            color={confirmColor}
            disabled={pending || confirmDisabled}
            onClick={onConfirm}
          >
            {confirmLabel ?? t('common.save')}
          </Button>
        ) : null}
      </DialogActions>
    </Dialog>
  );
}
