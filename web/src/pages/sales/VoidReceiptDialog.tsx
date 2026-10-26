import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Drawer from '@mui/material/Drawer';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { Link as RouterLink } from 'react-router-dom';
import { getErrorDetails } from '@/api/client';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { t } from '@/i18n';
import type { CustomerReceipt } from '@/types/domain';
import { formatMoney, toNumber } from '@/utils/money';
import { todayIso } from '@/components/billing';
import { MAX_VOID_REASON_LENGTH, MIN_VOID_REASON_LENGTH } from '@/pages/sales/receiptStatus';

const VOID_SHEET_TITLE_ID = 'void-receipt-sheet-title';

interface Props {
  target: CustomerReceipt | null;
  /** Bottom drawer on narrow screens, centred dialog otherwise. */
  narrow: boolean;
  pending: boolean;
  error: string | null;
  errorSource: unknown;
  onCancel: () => void;
  onConfirm: (reason: string) => void;
}

function VoidForm({
  target,
  pending,
  error,
  errorSource,
  onCancel,
  onConfirm,
  stacked,
}: Omit<Props, 'narrow'> & { target: CustomerReceipt; stacked: boolean }) {
  // The reason lives here, so it is cleared when the form unmounts and survives a refused void.
  const [reason, setReason] = useState('');
  const trimmed = reason.trim().replace(/\s+/g, ' ');
  const tooShort = trimmed.length < MIN_VOID_REASON_LENGTH;
  const applied = toNumber(target.allocated) > 0;
  // A receipt matched to a bank line cannot be voided until that match is undone.
  const matchedLine = Number(getErrorDetails(errorSource)?.lineId) || null;

  const submit = () => {
    if (!tooShort && !pending) onConfirm(trimmed);
  };

  const body = (
    <Stack spacing={1.5} sx={{ mt: 1 }}>
      <Typography>{t('billing.confirmVoidReceipt')}</Typography>
      <Typography variant="body2" color="text.secondary">
        {target.number ?? target.id} · {target.customerName} · {formatMoney(target.amount)}
      </Typography>
      <Alert severity="info" variant="outlined">
        {t('receipts.voidPostsToday', { today: todayIso(), original: target.receiptDate })}
        {applied ? ` ${t('receipts.voidAdvanceNotice')}` : ''}
      </Alert>
      {error ? (
        <HelpErrorAlert message={error} error={errorSource}>
          {matchedLine != null ? (
            <Button
              size="small"
              component={RouterLink}
              to={`/payments/reconciliation?line=${matchedLine}`}
              sx={{ display: 'block', mt: 0.5 }}
            >
              {t('receipts.openReconciliation')}
            </Button>
          ) : null}
        </HelpErrorAlert>
      ) : null}
      <TextField
        autoFocus
        required
        fullWidth
        size="small"
        label={t('receipts.voidReasonLabel')}
        placeholder={t('receipts.voidReasonPlaceholder')}
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            submit();
          }
        }}
        error={reason.length > 0 && tooShort}
        helperText={
          reason.length > 0 && tooShort
            ? t('receipts.voidReasonTooShort', { min: MIN_VOID_REASON_LENGTH })
            : t('receipts.voidReasonHelp')
        }
        slotProps={{ htmlInput: { maxLength: MAX_VOID_REASON_LENGTH } }}
      />
    </Stack>
  );

  const actions = (
    <>
      <Button onClick={onCancel} disabled={pending}>
        {t('common.cancel')}
      </Button>
      <Button color="warning" variant="contained" disabled={pending || tooShort} onClick={submit}>
        {t('billing.voidAction')}
      </Button>
    </>
  );

  if (stacked) {
    return (
      <Box sx={{ p: 2 }}>
        <Typography id={VOID_SHEET_TITLE_ID} variant="subtitle1" fontWeight={600} component="h2">
          {t('billing.voidAction')}
        </Typography>
        {body}
        <Stack direction="row" spacing={1} justifyContent="flex-end" sx={{ mt: 2 }}>
          {actions}
        </Stack>
      </Box>
    );
  }
  return (
    <>
      <DialogTitle>{t('billing.voidAction')}</DialogTitle>
      <DialogContent>{body}</DialogContent>
      <DialogActions>{actions}</DialogActions>
    </>
  );
}

/**
 * Void-a-receipt confirmation. The reason is required (the server enforces the same floor),
 * and the form stays open with the typed reason if the void is refused.
 */
export function VoidReceiptDialog({ target, narrow, onCancel, ...rest }: Props) {
  const open = target != null;
  const close = () => {
    if (!rest.pending) onCancel();
  };
  if (narrow) {
    return (
      // A bottom sheet is still a modal dialog: without these, screen readers do not announce it
      // and the reason field is not reachable as part of a dialog (found by the phone e2e run).
      <Drawer
        anchor="bottom"
        open={open}
        onClose={close}
        PaperProps={{ role: 'dialog', 'aria-modal': true, 'aria-labelledby': VOID_SHEET_TITLE_ID }}
      >
        {target ? <VoidForm key={target.id} target={target} onCancel={close} stacked {...rest} /> : null}
      </Drawer>
    );
  }
  return (
    <Dialog open={open} onClose={close} fullWidth maxWidth="xs">
      {target ? <VoidForm key={target.id} target={target} onCancel={close} stacked={false} {...rest} /> : null}
    </Dialog>
  );
}
