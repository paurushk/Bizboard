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
import { useNavigate } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import {
  convertQuotation,
  createQuotation,
  listCustomers,
  listProducts,
  listQuotations,
  listSalesInvoicesPage,
} from '@/api/resources';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { StatusChip } from '@/components/StatusChip';
import { t } from '@/i18n';
import type { Customer, Product } from '@/types/domain';
import { formatMoney, toNumber } from '@/utils/money';
import { documentStatusTone, statusLabelKey } from '@/utils/status';

export function QuotationsPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const query = useQuery({ queryKey: ['quotations'], queryFn: listQuotations });
  const customers = useQuery({ queryKey: ['customers'], queryFn: () => listCustomers() });
  const products = useQuery({ queryKey: ['products'], queryFn: () => listProducts() });

  const [open, setOpen] = useState(false);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [product, setProduct] = useState<Product | null>(null);
  const [qty, setQty] = useState('1');
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: async () => {
      if (!product) throw new Error('Add at least one product');
      return createQuotation({
        customer: customer?.id,
        quotationDate: new Date().toISOString().slice(0, 10),
        invoiceType: 'GST',
        items: [
          {
            product: product.id,
            quantity: Number(qty),
            unitPrice: toNumber(product.sellingPrice),
            gstRate: toNumber(product.gstRate),
          },
        ],
      });
    },
    onSuccess: () => {
      setOpen(false);
      setMessage('Quotation created');
      void qc.invalidateQueries({ queryKey: ['quotations'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const convertMutation = useMutation({
    mutationFn: (id: number) => convertQuotation(id),
    onSuccess: async (invoice) => {
      const flash = `Converted to draft invoice #${invoice.id}`;
      setMessage(flash);
      void qc.invalidateQueries({ queryKey: ['quotations'] });
      try {
        await qc.fetchQuery({
          queryKey: ['sales-invoices'],
          queryFn: () => listSalesInvoicesPage(),
          staleTime: 0,
        });
      } catch {
        void qc.invalidateQueries({ queryKey: ['sales-invoices'] });
      }
      void navigate('/sales/history', { state: { message: flash } });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h4">{t('nav.quotations')}</Typography>
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
      {query.data?.length === 0 ? <EmptyState description={t('empty.invoices')} /> : null}
      {query.data && query.data.length > 0 ? (
        <Paper sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('common.number')}</TableCell>
                <TableCell>{t('common.date')}</TableCell>
                <TableCell>{t('billing.customer')}</TableCell>
                <TableCell>{t('common.status')}</TableCell>
                <TableCell align="right">{t('common.total')}</TableCell>
                <TableCell />
              </TableRow>
            </TableHead>
            <TableBody>
              {query.data.map((q) => (
                <TableRow key={q.id}>
                  <TableCell>{q.number ?? '—'}</TableCell>
                  <TableCell>{q.quotationDate}</TableCell>
                  <TableCell>{q.customerName ?? '—'}</TableCell>
                  <TableCell>
                    <StatusChip
                      tone={documentStatusTone(q.status)}
                      labelKey={statusLabelKey(q.status)}
                    />
                  </TableCell>
                  <TableCell align="right">{formatMoney(q.grandTotal)}</TableCell>
                  <TableCell align="right">
                    {q.status === 'DRAFT' ? (
                      <Button size="small" onClick={() => convertMutation.mutate(q.id)}>
                        {t('common.convert')}
                      </Button>
                    ) : null}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}

      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>New quotation</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Autocomplete
              options={customers.data ?? []}
              getOptionLabel={(o) => o.name}
              value={customer}
              onChange={(_, v) => setCustomer(v)}
              renderInput={(params) => <TextField {...params} label={t('billing.customer')} />}
            />
            <Autocomplete
              options={(products.data ?? []).filter((p) => p.status === 'ACTIVE')}
              getOptionLabel={(o) => `${o.name} · ${o.sku}`}
              value={product}
              onChange={(_, v) => setProduct(v)}
              renderInput={(params) => <TextField {...params} label={t('nav.products')} />}
            />
            <TextField
              type="number"
              label={t('billing.qty')}
              value={qty}
              onChange={(e) => setQty(e.target.value)}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!product || createMutation.isPending}
            onClick={() => createMutation.mutate()}
          >
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
