import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import List from '@mui/material/List';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemText from '@mui/material/ListItemText';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { linkDeliveryRouteReceipt, listReceiptsPage } from '@/api/resources';
import { t } from '@/i18n';
import { formatMoney, toNumber } from '@/utils/money';
import type { RouteStop } from './routeTypes';

interface Props {
  routeId: number;
  stop: RouteStop | null;
  onClose: () => void;
  onLinked: () => void;
}

/**
 * Point a stop at the receipt the cashier posted for its collection (DEC-R2). Only this customer's
 * posted receipts are offered; nothing is created here. If the receipt differs from what the driver
 * collected, the difference is shown and a reason is asked for.
 */
export function LinkReceiptDialog({ routeId, stop, onClose, onLinked }: Props) {
  const [receiptId, setReceiptId] = useState<number | null>(null);
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);
  const customerId = stop?.customer ?? 0;
  const collected = stop ? toNumber(stop.collectedCash) + toNumber(stop.collectedUpi) : 0;

  const receipts = useQuery({
    queryKey: ['route-link-receipts', customerId],
    queryFn: () => listReceiptsPage({ customer: customerId, status: 'POSTED', pageSize: 20 }),
    enabled: Boolean(stop && customerId),
  });
  const rows = receipts.data?.results ?? [];
  const chosen = rows.find((r) => r.id === receiptId) ?? null;
  const difference = chosen ? Math.round((toNumber(chosen.amount) - collected) * 100) / 100 : 0;

  const link = useMutation({
    mutationFn: () =>
      linkDeliveryRouteReceipt(routeId, {
        stopId: stop!.id,
        receiptId: receiptId!,
        reason: difference !== 0 ? reason.trim() : undefined,
      }),
    onSuccess: () => {
      setReceiptId(null);
      setReason('');
      setError(null);
      onLinked();
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  return (
    <Dialog open={stop !== null} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{t('routes.linkReceiptTitle')}</DialogTitle>
      <DialogContent>
        <Stack spacing={1.5} sx={{ mt: 1 }}>
          <Typography variant="body2">
            {t('routes.linkReceiptHelp', { amount: formatMoney(collected), customer: stop?.customerName ?? '' })}
          </Typography>
          {error ? <Alert severity="error">{error}</Alert> : null}
          {receipts.isLoading ? <Typography variant="body2">{t('common.loading')}</Typography> : null}
          {!receipts.isLoading && rows.length === 0 ? <Alert severity="info">{t('routes.noReceipts')}</Alert> : null}
          <List dense disablePadding>
            {rows.map((r) => (
              <ListItemButton key={r.id} selected={r.id === receiptId} onClick={() => setReceiptId(r.id)} sx={{ minHeight: 44 }}>
                <ListItemText
                  primary={`${r.number || `#${r.id}`} · ${formatMoney(toNumber(r.amount))}`}
                  secondary={`${r.receiptDate} · ${r.mode}${r.reference ? ` · ${r.reference}` : ''}`}
                />
              </ListItemButton>
            ))}
          </List>
          {chosen && difference !== 0 ? (
            <>
              <Alert severity="warning">
                {t(difference > 0 ? 'routes.receiptMore' : 'routes.receiptLess', { amount: formatMoney(Math.abs(difference)) })}
              </Alert>
              <TextField size="small" label={t('routes.reasonForDifference')} value={reason} onChange={(e) => setReason(e.target.value)} fullWidth />
            </>
          ) : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button
          variant="contained"
          disabled={!chosen || link.isPending || (difference !== 0 && reason.trim().length < 3)}
          onClick={() => link.mutate()}
        >
          {t('routes.linkReceipt')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
