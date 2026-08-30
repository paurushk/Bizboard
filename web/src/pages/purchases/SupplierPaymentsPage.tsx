import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import MenuItem from '@mui/material/MenuItem';
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
  createAllocation,
  createSupplierPayment,
  listPurchasesPage,
  listSupplierPaymentsPage,
  listSuppliers,
  voidSupplierPayment,
} from '@/api/resources';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { todayIso } from '@/components/billing';
import { t } from '@/i18n';
import type { PaymentMode, PurchaseInvoice, Supplier } from '@/types/domain';
import { formatMoney, toNumber } from '@/utils/money';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';

const PAGE_SIZE = 50;

export function SupplierPaymentsPage() {
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const query = useQuery({
    queryKey: ['supplier-payments', page],
    queryFn: () => listSupplierPaymentsPage({ page, pageSize: PAGE_SIZE }),
  });
  const suppliers = useQuery({ queryKey: ['suppliers'], queryFn: listSuppliers });
  const purchases = useQuery({
    queryKey: ['purchases'],
    queryFn: async () => {
      const res = await listPurchasesPage({ pageSize: PAGE_SIZE });
      return res.results;
    },
  });

  const payments = query.data?.results ?? [];

  const [open, setOpen] = useState(false);
  const [supplier, setSupplier] = useState<Supplier | null>(null);
  const [amount, setAmount] = useState('');
  const [mode, setMode] = useState<PaymentMode>('BANK');
  const [purchase, setPurchase] = useState<PurchaseInvoice | null>(null);
  const [allocAmount, setAllocAmount] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: async () => {
      if (!supplier) throw new Error('Supplier required');
      // BUG-528: reject non-positive amounts (a plain type="number" field
      // let "-500" through since it's a non-empty string).
      const paymentAmount = Number(amount);
      if (!(paymentAmount > 0)) throw new Error('Amount must be greater than zero');
      const payment = await createSupplierPayment({
        supplier: supplier.id,
        amount: paymentAmount,
        mode,
        paymentDate: todayIso(),
      });
      if (purchase && Number(allocAmount) > 0) {
        await createAllocation({
          supplierPayment: payment.id,
          purchaseInvoice: purchase.id,
          amount: Number(allocAmount),
        });
      }
      return payment;
    },
    onSuccess: () => {
      setOpen(false);
      setMessage('Supplier payment created');
      // BUG-530: reset the form so reopening doesn't show stale values —
      // ReceiptsPage already did this, this page didn't.
      setSupplier(null);
      setAmount('');
      setPurchase(null);
      setAllocAmount('');
      void qc.invalidateQueries({ queryKey: ['supplier-payments'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const voidMutation = useMutation({
    mutationFn: (id: number) => voidSupplierPayment(id),
    onSuccess: () => {
      setMessage('Payment voided');
      void qc.invalidateQueries({ queryKey: ['supplier-payments'] });
      void qc.invalidateQueries({ queryKey: ['purchases'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  // BUG-529: only offer purchases with an outstanding balance.
  const openPurchases = (purchases.data ?? []).filter(
    (p) =>
      p.status === 'COMPLETED' &&
      (!supplier || p.supplier === supplier.id) &&
      toNumber(p.balance ?? p.grandTotal) > 0,
  );

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h4">{t('nav.supplierPayments')}</Typography>
        <Button variant="contained" onClick={() => setOpen(true)}>
          {t('phase1.newSupplierPayment')}
        </Button>
      </Stack>
      {message ? <Alert severity="success">{message}</Alert> : null}
      {error ? <HelpErrorAlert message={error} /> : null}
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {payments.length === 0 && query.isSuccess ? (
        <EmptyState
          description="Record payments made to suppliers."
          action={
            <Button variant="contained" onClick={() => setOpen(true)}>
              {t('phase1.newSupplierPayment')}
            </Button>
          }
        />
      ) : null}
      {payments.length > 0 ? (
        <Paper sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('common.number')}</TableCell>
                <TableCell>{t('common.date')}</TableCell>
                <TableCell>{t('billing.supplier')}</TableCell>
                <TableCell>Mode</TableCell>
                <TableCell align="right">{t('common.amount')}</TableCell>
                <TableCell align="right">Allocated</TableCell>
                <TableCell align="right">{t('common.actions')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {payments.map((p) => (
                <TableRow key={p.id}>
                  <TableCell>{p.number ?? p.id}</TableCell>
                  <TableCell>{p.paymentDate}</TableCell>
                  <TableCell>{p.supplierName}</TableCell>
                  <TableCell>{p.mode}</TableCell>
                  <TableCell align="right">{formatMoney(p.amount)}</TableCell>
                  <TableCell align="right">{formatMoney(p.allocated)}</TableCell>
                  <TableCell align="right">
                    {p.status && p.status !== 'POSTED' ? (
                      <Chip size="small" label={p.status} />
                    ) : (
                      <Button
                        size="small"
                        color="warning"
                        disabled={voidMutation.isPending}
                        onClick={() => {
                          if (window.confirm(t('billing.confirmVoidPayment'))) {
                            voidMutation.mutate(p.id);
                          }
                        }}
                      >
                        Void
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}
      {query.data && (query.data.next || page > 1) ? (
        <Stack direction="row" spacing={1} justifyContent="flex-end" alignItems="center">
          <Typography variant="body2" color="text.secondary">
            {t('common.page')} {page}
          </Typography>
          <Button variant="outlined" size="small" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            {t('common.previous')}
          </Button>
          <Button
            variant="outlined"
            size="small"
            disabled={!query.data.next}
            onClick={() => setPage((p) => p + 1)}
          >
            {t('common.next')}
          </Button>
        </Stack>
      ) : null}

      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>New supplier payment</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Autocomplete
              options={suppliers.data ?? []}
              getOptionLabel={(o) => o.name}
              value={supplier}
              onChange={(_, v) => setSupplier(v)}
              renderInput={(params) => <TextField {...params} label={t('billing.supplier')} />}
            />
            <TextField
              type="number"
              label={t('common.amount')}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
            <TextField select label="Mode" value={mode} onChange={(e) => setMode(e.target.value as PaymentMode)}>
              {(['CASH', 'UPI', 'BANK', 'CARD', 'CREDIT'] as const).map((m) => (
                <MenuItem key={m} value={m}>
                  {m}
                </MenuItem>
              ))}
            </TextField>
            <Autocomplete
              options={openPurchases}
              getOptionLabel={(o) => `${o.number ?? o.id} · ${formatMoney(o.grandTotal)}`}
              value={purchase}
              onChange={(_, v) => {
                setPurchase(v);
                if (v) {
                  setAllocAmount(
                    String(Math.min(toNumber(amount), toNumber(v.balance ?? v.grandTotal))),
                  );
                }
              }}
              renderInput={(params) => (
                <TextField {...params} label="Allocate to purchase (optional)" />
              )}
            />
            {purchase ? (
              <TextField
                type="number"
                label={t('common.allocate')}
                value={allocAmount}
                onChange={(e) => setAllocAmount(e.target.value)}
              />
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!supplier || !amount || createMutation.isPending}
            onClick={() => createMutation.mutate()}
          >
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
