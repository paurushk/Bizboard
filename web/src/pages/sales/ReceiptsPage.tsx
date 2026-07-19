import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
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
  createReceipt,
  listCustomers,
  listReceipts,
  listSalesInvoices,
} from '@/api/resources';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';
import type { Customer, PaymentMode, SalesInvoice } from '@/types/domain';
import { formatMoney, toNumber } from '@/utils/money';

export function ReceiptsPage() {
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ['receipts'], queryFn: listReceipts });
  const customers = useQuery({ queryKey: ['customers'], queryFn: () => listCustomers() });
  const invoices = useQuery({
    queryKey: ['sales-invoices-open'],
    queryFn: () => listSalesInvoices({ status: 'COMPLETED' }),
  });

  const [open, setOpen] = useState(false);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [amount, setAmount] = useState('');
  const [mode, setMode] = useState<PaymentMode>('CASH');
  const [invoice, setInvoice] = useState<SalesInvoice | null>(null);
  const [allocAmount, setAllocAmount] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: async () => {
      if (!customer) throw new Error('Customer required');
      const receipt = await createReceipt({
        customer: customer.id,
        amount: Number(amount),
        mode,
        receiptDate: new Date().toISOString().slice(0, 10),
      });
      if (invoice && Number(allocAmount) > 0) {
        await createAllocation({
          receipt: receipt.id,
          salesInvoice: invoice.id,
          amount: Number(allocAmount),
        });
      }
      return receipt;
    },
    onSuccess: () => {
      setOpen(false);
      setMessage('Receipt created');
      setCustomer(null);
      setAmount('');
      setInvoice(null);
      setAllocAmount('');
      void qc.invalidateQueries({ queryKey: ['receipts'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const openInvoices = (invoices.data ?? []).filter(
    (inv) => !customer || inv.customer === customer.id,
  );

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h4">{t('nav.receipts')}</Typography>
        <Button variant="contained" onClick={() => setOpen(true)}>
          {t('common.create')}
        </Button>
      </Stack>
      {message ? <Alert severity="success">{message}</Alert> : null}
      {error ? <Alert severity="error">{error}</Alert> : null}
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={query.error.message} onRetry={() => void query.refetch()} />
      ) : null}
      {query.data?.length === 0 ? <EmptyState /> : null}
      {query.data && query.data.length > 0 ? (
        <Paper sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('common.number')}</TableCell>
                <TableCell>{t('common.date')}</TableCell>
                <TableCell>{t('billing.customer')}</TableCell>
                <TableCell>Mode</TableCell>
                <TableCell align="right">{t('common.amount')}</TableCell>
                <TableCell align="right">Allocated</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {query.data.map((r) => (
                <TableRow key={r.id}>
                  <TableCell>{r.number ?? r.id}</TableCell>
                  <TableCell>{r.receiptDate}</TableCell>
                  <TableCell>{r.customerName}</TableCell>
                  <TableCell>{r.mode}</TableCell>
                  <TableCell align="right">{formatMoney(r.amount)}</TableCell>
                  <TableCell align="right">{formatMoney(r.allocated)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}

      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>New customer receipt</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Autocomplete
              options={customers.data ?? []}
              getOptionLabel={(o) => o.name}
              value={customer}
              onChange={(_, v) => setCustomer(v)}
              renderInput={(params) => <TextField {...params} label={t('billing.customer')} />}
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
              options={openInvoices}
              getOptionLabel={(o) =>
                `${o.number ?? o.id} · ${formatMoney(o.grandTotal)}`
              }
              value={invoice}
              onChange={(_, v) => {
                setInvoice(v);
                if (v) setAllocAmount(String(Math.min(toNumber(amount), toNumber(v.grandTotal))));
              }}
              renderInput={(params) => (
                <TextField {...params} label="Allocate to invoice (optional)" />
              )}
            />
            {invoice ? (
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
            disabled={!customer || !amount || createMutation.isPending}
            onClick={() => createMutation.mutate()}
          >
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
