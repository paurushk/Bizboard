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
  getPurchase,
  listPurchaseReturnsPage,
  listPurchasesPage,
} from '@/api/resources';
import {
  InvoiceReturnLineTable,
  activeSourceLines,
  invoiceItemsToSourceLines,
  todayIso,
  type InvoiceSourceLine,
} from '@/components/billing';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { StatusChip } from '@/components/StatusChip';
import { t } from '@/i18n';
import type { PurchaseInvoice } from '@/types/domain';
import { formatMoney } from '@/utils/money';
import { documentStatusTone, statusLabelKey } from '@/utils/status';

const PAGE_SIZE = 50;

export function PurchaseReturnsPage() {
  const qc = useQueryClient();
  const [page] = useState(1);
  const query = useQuery({
    queryKey: ['purchase-returns', page],
    queryFn: () => listPurchaseReturnsPage({ page, pageSize: PAGE_SIZE }),
  });
  const purchases = useQuery({
    queryKey: ['purchases'],
    queryFn: async () => {
      const res = await listPurchasesPage({ pageSize: PAGE_SIZE });
      return res.results;
    },
  });

  const returns = query.data?.results ?? [];

  const [open, setOpen] = useState(false);
  const [purchase, setPurchase] = useState<PurchaseInvoice | null>(null);
  const [lines, setLines] = useState<InvoiceSourceLine[]>([]);
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const onPurchasePick = async (pur: PurchaseInvoice | null) => {
    setPurchase(pur);
    if (!pur) {
      setLines([]);
      return;
    }
    const full = pur.items?.length ? pur : await getPurchase(pur.id);
    setPurchase(full);
    setLines(invoiceItemsToSourceLines(full.items));
  };

  const createMutation = useMutation({
    mutationFn: async () => {
      if (!purchase) throw new Error(t('phase1.selectPurchaseInvoice'));
      const selected = activeSourceLines(lines);
      if (selected.length === 0) throw new Error(t('phase1.selectInvoiceLines'));
      const draft = await createPurchaseReturn({
        supplier: purchase.supplier,
        purchaseInvoice: purchase.id,
        returnDate: todayIso(),
        reason,
        items: selected.map((l) => ({
          product: l.product,
          quantity: l.quantity,
          unitPrice: l.unitPrice,
          gstRate: l.gstRate,
        })),
      });
      return completePurchaseReturn(draft.id);
    },
    onSuccess: () => {
      setOpen(false);
      setMessage('Purchase return completed');
      setPurchase(null);
      setLines([]);
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
          {t('phase1.newPurchaseReturn')}
        </Button>
      </Stack>
      {message ? <Alert severity="success">{message}</Alert> : null}
      {error ? <Alert severity="error">{error}</Alert> : null}
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} onRetry={() => void query.refetch()} />
      ) : null}
      {returns.length === 0 && query.isSuccess ? <EmptyState /> : null}
      {returns.length > 0 ? (
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
              {returns.map((r) => (
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

      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="md">
        <DialogTitle>New purchase return</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Autocomplete
              options={completed}
              getOptionLabel={(o) => `${o.number ?? o.id} · ${o.supplierName ?? ''}`}
              value={purchase}
              onChange={(_, v) => void onPurchasePick(v)}
              renderInput={(params) => <TextField {...params} label="Original purchase" />}
            />
            {lines.length > 0 ? (
              <InvoiceReturnLineTable lines={lines} onChange={setLines} />
            ) : null}
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
            disabled={!purchase || activeSourceLines(lines).length === 0 || createMutation.isPending}
            onClick={() => createMutation.mutate()}
          >
            {t('common.complete')}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
