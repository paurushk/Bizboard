import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import {
  completePurchaseReturn,
  createPurchaseReturn,
  listPurchaseReturns,
  listPurchases,
} from '@/api/resources';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { StatusChip } from '@/components/StatusChip';
import { t } from '@/i18n';
import type { LineItem, PurchaseInvoice } from '@/types/domain';
import { formatMoney, toNumber } from '@/utils/money';
import { documentStatusTone, statusLabelKey } from '@/utils/status';

function lineLabel(item: LineItem): string {
  const name = item.productName ?? item.description ?? `Product #${item.product}`;
  return `${name} — purchased ${toNumber(item.quantity)}`;
}

export function PurchaseReturnsPage() {
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ['purchase-returns'], queryFn: listPurchaseReturns });
  const purchases = useQuery({ queryKey: ['purchases'], queryFn: () => listPurchases() });

  const [open, setOpen] = useState(false);
  const [purchase, setPurchase] = useState<PurchaseInvoice | null>(null);
  // BUG-531: previously always returned purchase.items[0] with no way to
  // pick a different line for a multi-item purchase.
  const [item, setItem] = useState<LineItem | null>(null);
  const [qty, setQty] = useState('1');
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const maxQty = item ? toNumber(item.quantity) : 1;

  const createMutation = useMutation({
    mutationFn: async () => {
      if (!purchase || !item) throw new Error('Select a purchase line to return');
      // BUG-532: clamp to what was actually purchased on this line.
      const quantity = Math.min(Math.max(1, Math.floor(Number(qty)) || 1), maxQty);
      const draft = await createPurchaseReturn({
        supplier: purchase.supplier,
        purchaseInvoice: purchase.id,
        returnDate: new Date().toISOString().slice(0, 10),
        reason,
        items: [
          {
            product: item.product,
            quantity,
            unitPrice: toNumber(item.unitPrice),
            gstRate: toNumber(item.gstRate),
          },
        ],
      });
      return completePurchaseReturn(draft.id);
    },
    onSuccess: () => {
      setOpen(false);
      setMessage('Purchase return completed');
      setPurchase(null);
      setItem(null);
      setQty('1');
      setReason('');
      void qc.invalidateQueries({ queryKey: ['purchase-returns'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const completed = (purchases.data ?? []).filter((p) => p.status === 'COMPLETED');

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h4">{t('nav.purchaseReturns')}</Typography>
        <Button variant="contained" onClick={() => setOpen(true)}>
          {t('common.create')}
        </Button>
      </Stack>
      {message ? <Alert severity="success">{message}</Alert> : null}
      {error ? <Alert severity="error">{error}</Alert> : null}
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} onRetry={() => void query.refetch()} />
      ) : null}
      {query.data?.length === 0 ? <EmptyState /> : null}
      {query.data && query.data.length > 0 ? (
        <Paper sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('common.number')}</TableCell>
                <TableCell>{t('common.date')}</TableCell>
                <TableCell>{t('billing.supplier')}</TableCell>
                <TableCell>{t('common.status')}</TableCell>
                <TableCell align="right">{t('common.total')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {query.data.map((r) => (
                <TableRow key={r.id}>
                  <TableCell>{r.number ?? r.id}</TableCell>
                  <TableCell>{r.returnDate}</TableCell>
                  <TableCell>{r.supplierName}</TableCell>
                  <TableCell>
                    <StatusChip
                      tone={documentStatusTone(r.status)}
                      labelKey={statusLabelKey(r.status)}
                    />
                  </TableCell>
                  <TableCell align="right">{formatMoney(r.grandTotal)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}

      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>New purchase return</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Autocomplete
              options={completed}
              getOptionLabel={(o) => `${o.number ?? o.id} · ${o.supplierName ?? ''}`}
              value={purchase}
              onChange={(_, v) => {
                setPurchase(v);
                setItem(null);
              }}
              renderInput={(params) => <TextField {...params} label="Original purchase" />}
            />
            <Autocomplete
              options={purchase?.items ?? []}
              getOptionLabel={lineLabel}
              value={item}
              onChange={(_, v) => {
                setItem(v);
                setQty('1');
              }}
              disabled={!purchase}
              renderInput={(params) => <TextField {...params} label="Item to return" />}
            />
            <TextField
              type="number"
              label={t('billing.qty')}
              value={qty}
              onChange={(e) => setQty(e.target.value)}
              disabled={!item}
              inputProps={{ min: 1, max: maxQty }}
              helperText={item ? `Up to ${maxQty} (quantity purchased on this line)` : undefined}
            />
            <TextField
              label={t('common.reason')}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!purchase || !item || createMutation.isPending}
            onClick={() => createMutation.mutate()}
          >
            {t('common.complete')}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
